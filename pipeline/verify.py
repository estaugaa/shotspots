"""Verification: does any of this match an independent source?

positions(): JPL Horizons (truth) vs this pipeline (Skyfield DE440) vs the phone app's own math (run in Node),
             and USNO rise/set/twilight vs the app.  -> feed/verify_positions.json
outcomes():  outing logs submitted from the app (Netlify Forms) checked against GOES-18 history, the nearest
             ASOS station, same-day Flickr photos, your eBird checklist and your SQM reading.
             Brier scores + reliability tables per event; Platt calibration of score -> chance of a keeper.
             -> feed/report.json, feed/reliability.png, feed/calibration.json, config/sqm_readings.json
astrometry(): plate-solve night frames dropped in inbox/frames/ with nova.astrometry.net, then compare where
             the frame pointed with where the planned target was predicted to be. -> feed/solves.json
"""
import json, math, subprocess, datetime as dt, time, re, os
from pathlib import Path
import numpy as np
from .common import http, spots, write_json, read_json, ROOT, FEED, DATA, CONFIG, CACHE, log, utcnow, iso, r, secret, km
from . import ephem, obs

HOME = (45.582, -122.353)
HZ_IDS = {"sun": "10", "moon": "301", "mars": "499", "jupiter": "599", "saturn": "699", "venus": "299"}


def horizons(body, t0, t1, step="3 h", lat=HOME[0], lon=HOME[1]):
    p = {"format": "json", "COMMAND": f"'{HZ_IDS[body]}'", "OBJ_DATA": "'NO'", "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'OBSERVER'",
         "CENTER": "'coord@399'", "COORD_TYPE": "'GEODETIC'", "SITE_COORD": f"'{lon},{lat},0.01'", "START_TIME": f"'{t0:%Y-%m-%d %H:%M}'",
         "STOP_TIME": f"'{t1:%Y-%m-%d %H:%M}'", "STEP_SIZE": f"'{step}'", "QUANTITIES": "'4'", "ANG_FORMAT": "'DEG'", "EXTRA_PREC": "'YES'", "TIME_DIGITS": "'MINUTES'"}
    txt = http("https://ssd.jpl.nasa.gov/api/horizons.api", params=p).json()["result"]
    body_ = txt.split("$$SOE")[1].split("$$EOE")[0]
    rows = []
    for line in body_.strip().splitlines():
        m = re.match(r"\s*(\d{4}-\w{3}-\d\d \d\d:\d\d)\s+\S*\s*\S*\s+([-\d.]+)\s+([-\d.]+)", line)
        if m:
            t = dt.datetime.strptime(m.group(1), "%Y-%b-%d %H:%M").replace(tzinfo=dt.timezone.utc)
            rows.append((t, float(m.group(2)), float(m.group(3))))  # az, el (airless apparent)
    return rows


def app_positions(times, bodies):
    """Ask the phone app's JavaScript for alt/az (geometric) at given times. Returns {body: [(alt, az)]}."""
    js = ROOT / "tools" / "app_positions.js"
    res = subprocess.run(["node", str(js), json.dumps({"times": [t.timestamp() * 1000 for t in times], "bodies": bodies, "lat": HOME[0], "lon": HOME[1]})],
                         capture_output=True, text=True, timeout=120, cwd=ROOT)
    if res.returncode:
        raise RuntimeError(res.stderr[-400:])
    return json.loads(res.stdout)


def sep(az1, el1, az2, el2):
    a1, e1, a2, e2 = map(math.radians, (az1, el1, az2, el2))
    c = math.sin(e1) * math.sin(e2) + math.cos(e1) * math.cos(e2) * math.cos(a1 - a2)
    return math.degrees(math.acos(max(-1, min(1, c)))) * 60  # arcmin


def positions():
    t0 = utcnow().replace(minute=0, second=0, microsecond=0)
    t1 = t0 + dt.timedelta(days=2)
    out = {"gen": iso(utcnow()), "site": "Washougal", "bodies": {}}
    for b in HZ_IDS:
        try:
            hz = horizons(b, t0, t1)
        except Exception as e:
            out["bodies"][b] = {"error": str(e)[:120]}
            continue
        hz = [x for x in hz if x[2] > -5]
        if not hz:
            continue
        times = [x[0] for x in hz]
        u = np.array([t.timestamp() for t in times])
        ts, _ = ephem.load()
        tt = ts.utc(1970, 1, 1, 0, 0, u)
        ra, dec, dist = ephem.radec(b, tt)
        alt, az = ephem.altaz(ra, dec, ephem.gast_deg(tt), HOME[0], HOME[1], dist if b == "moon" else None)
        e_pipe = [sep(h[1], h[2], float(z), float(a)) for h, a, z in zip(hz, alt, az)]
        # diagnostic: Skyfield's own topocentric alt/az (no fast-formula shortcuts)
        try:
            from skyfield.api import wgs84
            _, eph = ephem.load()
            key = {"sun": "sun", "moon": "moon", "venus": "venus", "mars": "mars barycenter", "jupiter": "jupiter barycenter", "saturn": "saturn barycenter"}[b]
            topo = (eph["earth"] + wgs84.latlon(HOME[0], HOME[1], 3)).at(tt).observe(eph[key]).apparent()
            a2, z2, _ = topo.altaz()
            e_sky = [sep(h[1], h[2], float(zz), float(aa)) for h, aa, zz in zip(hz, a2.degrees, z2.degrees)]
            fast_vs_sky = [sep(float(z), float(a), float(zz), float(aa)) for a, z, aa, zz in zip(alt, az, a2.degrees, z2.degrees)]
        except Exception as e:
            e_sky, fast_vs_sky = None, None
            log.warning("skyfield topo diag: %s", e)
        try:
            app = app_positions(times, [b])[b]
            e_app = [sep(h[1], h[2], z, a) for h, (a, z) in zip(hz, app)]
        except Exception as e:
            e_app = None
            log.warning("app positions: %s", e)
        out["bodies"][b] = {"n": len(hz), "pipeline_max_arcmin": r(max(e_pipe), 2), "pipeline_mean_arcmin": r(np.mean(e_pipe), 2),
                            "skyfield_topo_max_arcmin": r(max(e_sky), 2) if e_sky else None, "fast_vs_skyfield_arcmin": r(max(fast_vs_sky), 2) if fast_vs_sky else None,
                            "sample": {"t": iso(times[0]), "horizons_az_el": [hz[0][1], hz[0][2]], "pipeline": [r(float(az[0]), 4), r(float(alt[0]), 4)]},
                            "app_max_arcmin": r(max(e_app), 1) if e_app else None, "app_mean_arcmin": r(np.mean(e_app), 1) if e_app else None}
    # USNO rise/set vs the app
    try:
        d = dt.datetime.now(obs.LA).date()
        j = http("https://aa.usno.navy.mil/api/rstt/oneday", params={"date": d.isoformat(), "coords": f"{HOME[0]},{HOME[1]}", "tz": -8 if not _dst(d) else -7, "dst": "false"}).json()
        sd = {x["phen"]: x["time"] for x in j["properties"]["data"]["sundata"]}
        md = {x["phen"]: x["time"] for x in j["properties"]["data"]["moondata"]}
        app = app_day_events(d)
        diffs = {}
        for k_usno, k_app in (("Rise", "sunrise"), ("Set", "sunset"), ("Begin Civil Twilight", "civilDawn"), ("End Civil Twilight", "civilDusk")):
            if k_usno in sd and app.get(k_app):
                diffs["sun " + k_usno] = _mindiff(sd[k_usno], app[k_app])
        for k_usno, k_app in (("Rise", "moonrise"), ("Set", "moonset")):
            if k_usno in md and app.get(k_app):
                diffs["moon " + k_usno] = _mindiff(md[k_usno], app[k_app])
        out["usno_vs_app_minutes"] = diffs
    except Exception as e:
        out["usno_vs_app_minutes"] = {"error": str(e)[:160]}
    write_json("verify_positions.json", out)
    worst = max((v.get("app_max_arcmin") or 0) for v in out["bodies"].values() if isinstance(v, dict))
    return f"app worst {worst} arcmin vs JPL Horizons"


def _dst(d):
    import zoneinfo
    return bool(dt.datetime(d.year, d.month, d.day, 12, tzinfo=zoneinfo.ZoneInfo("America/Los_Angeles")).dst())


def _mindiff(hhmm, app_local):
    h, m = map(int, hhmm.split(":")[:2])
    ah, am = map(int, app_local.split(":")[:2])
    return (ah * 60 + am) - (h * 60 + m)


def app_day_events(d):
    js = ROOT / "tools" / "app_positions.js"
    res = subprocess.run(["node", str(js), json.dumps({"dayEvents": d.isoformat(), "lat": HOME[0], "lon": HOME[1]})], capture_output=True, text=True, timeout=60, cwd=ROOT)
    if res.returncode:
        raise RuntimeError(res.stderr[-300:])
    return json.loads(res.stdout)


# ---------------- outcomes ----------------
def submissions():
    tok, site = secret("NETLIFY_TOKEN"), secret("NETLIFY_SITE_ID")
    if not tok or not site:
        return []
    out, page = [], 1
    while True:
        j = http(f"https://api.netlify.com/api/v1/sites/{site}/submissions", params={"per_page": 100, "page": page}, headers={"Authorization": f"Bearer {tok}"}).json()
        if not j:
            break
        out += [x for x in j if (x.get("form_name") or "") == "outcome"]
        page += 1
        if page > 20:
            break
    return out


def goes_at(spot_id, t):
    p = DATA / "goes_history.txt"
    if not p.exists():
        return None
    lines = p.read_text().splitlines()
    ids = lines[0][5:].split(",")
    if spot_id not in ids:
        return None
    k = ids.index(spot_id)
    best = None
    for l in lines[1:]:
        ts, code = l.split(" ", 1)
        try:
            tt = dt.datetime.fromisoformat(ts.replace("Z", "+00:00").split(".")[0] + ("+00:00" if "+" not in ts else ""))
        except Exception:
            continue
        dtm = abs((tt - t).total_seconds())
        if dtm <= 3600 and (best is None or dtm < best[0]):
            best = (dtm, int(code[2 * k]) * 11, int(code[2 * k + 1]) * 11)
    return None if best is None else {"cloud_pct": best[1], "lowcloud_pct": best[2], "dt_min": round(best[0] / 60)}


def ebird_checklist(sub_id):
    key = secret("EBIRD_KEY")
    if not key or not sub_id:
        return None
    j = http(f"https://api.ebird.org/v2/product/checklist/view/{sub_id}", headers={"X-eBirdApiToken": key}).json()
    codes = {o["speciesCode"] for o in j.get("obs", [])}
    tax = read_json(CACHE / "ebird_tax.json")
    if tax is None:
        tax = {x["speciesCode"]: x["comName"] for x in http("https://api.ebird.org/v2/ref/taxonomy/ebird", params={"fmt": "json"}, headers={"X-eBirdApiToken": key}).json()}
        json.dump(tax, open(CACHE / "ebird_tax.json", "w"))
    return sorted(tax.get(c, c) for c in codes)


def brier(pairs):
    if not pairs:
        return None
    p = np.array([a for a, _ in pairs], float)
    o = np.array([b for _, b in pairs], float)
    bins = []
    for lo in np.arange(0, 1, 0.1):
        m = (p >= lo) & (p < lo + 0.1 if lo < 0.9 else p <= 1.0)
        if m.sum():
            bins.append({"p": r(p[m].mean(), 2), "obs": r(o[m].mean(), 2), "n": int(m.sum())})
    clim = o.mean()
    bs = float(np.mean((p - o) ** 2))
    bs_ref = float(np.mean((clim - o) ** 2)) or 1e-9
    return {"n": len(pairs), "brier": r(bs, 3), "skill_vs_climatology": r(1 - bs / bs_ref, 2), "reliability": bins}


def platt(scores, y):
    x = np.array(scores, float) / 100.0
    y = np.array(y, float)
    a, b = 4.0, -2.0
    for _ in range(200):
        p = 1 / (1 + np.exp(-(a * x + b)))
        g = np.array([np.sum((p - y) * x), np.sum(p - y)])
        w = p * (1 - p)
        H = np.array([[np.sum(w * x * x), np.sum(w * x)], [np.sum(w * x), np.sum(w)]]) + 1e-6 * np.eye(2)
        a, b = np.array([a, b]) - np.linalg.solve(H, g)
    return float(a), float(b)


def outcomes():
    subs = submissions()
    by_id = {s["id"]: s for s in spots()}
    fk = secret("FLICKR_KEY")
    rows = read_json(DATA / "outcomes.json", {})
    for sub in subs:
        sid = sub["id"]
        if sid in rows:
            continue
        d = sub.get("data", {})
        try:
            pred = json.loads(d.get("pred") or "{}")
        except Exception:
            pred = {}
        spot = by_id.get(d.get("spot"))
        try:
            t = dt.datetime.fromtimestamp(int(d.get("t", "0")) / 1000, dt.timezone.utc)
        except Exception:
            continue
        rec = {"spot": d.get("spot"), "t": iso(t), "kind": d.get("kind"), "rating": _num(d.get("rating")), "keepers": _num(d.get("keepers")),
               "sky": d.get("sky"), "fog": d.get("fog"), "color": d.get("color"), "species": d.get("species"), "sqm": _num(d.get("sqm")), "pred": pred}
        if spot:
            rec["goes"] = goes_at(spot["id"], t)
            try:
                st = obs.nearest_station(spot["lat"], spot["lon"])
                rec["asos"] = {"station": st, "obs": obs.asos_recent(st, t - dt.timedelta(minutes=90), t + dt.timedelta(minutes=90))}
            except Exception as e:
                rec["asos"] = {"error": str(e)[:100]}
            if fk:
                try:
                    from .flickr import same_day
                    rec["flickr_same_day"] = same_day(fk, spot["lat"], spot["lon"], t.astimezone(obs.LA).date().isoformat())
                except Exception as e:
                    rec["flickr_same_day"] = {"error": str(e)[:100]}
        if d.get("ebird"):
            try:
                rec["ebird_species"] = ebird_checklist(d["ebird"].strip())
            except Exception as e:
                rec["ebird_species"] = {"error": str(e)[:100]}
        rows[sid] = rec
    json.dump(rows, open(DATA / "outcomes.json", "w"), indent=0)
    # SQM readings feed the VIIRS calibration
    sqm = [{"lat": by_id[o["spot"]]["lat"], "lon": by_id[o["spot"]]["lon"], "sqm": o["sqm"], "t": o["t"]} for o in rows.values() if o.get("sqm") and o.get("spot") in by_id]
    json.dump(sqm, open(CONFIG / "sqm_readings.json", "w"), indent=0)
    # event pairs (predicted probability, observed 0/1)
    ev = {"clear": [], "fog": [], "color": [], "keeper": [], "species": [], "sqm_error": []}
    for o in rows.values():
        p = o.get("pred") or {}
        g = o.get("goes") or {}
        obs_clear = (g.get("cloud_pct") is not None and g["cloud_pct"] < 30) if g else (o.get("sky") == "clear" if o.get("sky") else None)
        obs_fog = (g.get("lowcloud_pct", 0) >= 50) if g else (o.get("fog") == "yes" if o.get("fog") else None)
        if p.get("p_clear") is not None and obs_clear is not None:
            ev["clear"].append((p["p_clear"] / 100, int(obs_clear)))
        if p.get("p_fog") is not None and obs_fog is not None:
            ev["fog"].append((p["p_fog"] / 100, int(obs_fog)))
        if p.get("p_color") is not None and o.get("color"):
            ev["color"].append((p["p_color"] / 100, int(o["color"] in ("some", "strong"))))
        if p.get("score") is not None and (o.get("keepers") is not None or o.get("rating") is not None):
            ev["keeper"].append((p["score"] / 100, int((o.get("keepers") or 0) >= 1 or (o.get("rating") or 0) >= 4)))
        seen = set(x.lower() for x in (o.get("ebird_species") or [] if isinstance(o.get("ebird_species"), list) else [])) | set(x.strip().lower() for x in (o.get("species") or "").split(",") if x.strip())
        for sp, pp in (p.get("p_species") or {}).items():
            if seen:
                ev["species"].append((pp / 100, int(sp.lower() in seen)))
        if o.get("sqm") and p.get("sqm_pred"):
            ev["sqm_error"].append(o["sqm"] - p["sqm_pred"])
    report = {"gen": iso(utcnow()), "outings": len(rows), "events": {k: brier(v) for k, v in ev.items() if k != "sqm_error"},
              "sqm": {"n": len(ev["sqm_error"]), "bias": r(np.mean(ev["sqm_error"]), 2) if ev["sqm_error"] else None,
                      "rmse": r(math.sqrt(np.mean(np.square(ev["sqm_error"]))), 2) if ev["sqm_error"] else None}}
    cal = {"gen": iso(utcnow()), "n_keeper": len(ev["keeper"])}
    if len(ev["keeper"]) >= 20 and 0 < np.mean([y for _, y in ev["keeper"]]) < 1:
        a, b = platt([s * 100 for s, _ in ev["keeper"]], [y for _, y in ev["keeper"]])
        cal["keeper_platt"] = {"a": round(a, 3), "b": round(b, 3)}
    write_json("report.json", report, compact=False)
    write_json("calibration.json", cal)
    _plot(report)
    write_json("outcomes_public.json", {"rows": sorted(rows.values(), key=lambda o: o["t"], reverse=True)[:60]})
    return f"{len(rows)} outings, keeper pairs {len(ev['keeper'])}"


def _num(x):
    try:
        return float(x)
    except Exception:
        return None


def _plot(report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=150)
    ax.plot([0, 1], [0, 1], color="#999", lw=1, ls="--")
    colors = {"clear": "#2E6580", "fog": "#7B8A8C", "color": "#C98A1E", "keeper": "#3D6A49", "species": "#A4502A"}
    for k, v in (report.get("events") or {}).items():
        if v and v["reliability"]:
            ax.plot([b["p"] for b in v["reliability"]], [b["obs"] for b in v["reliability"]], marker="o", ms=3 + 0, lw=1.5, color=colors.get(k), label=f'{k} (n={v["n"]})')
    ax.set_xlabel("Forecast probability"); ax.set_ylabel("Observed frequency"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_title("Reliability: on the diagonal = honest odds", fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(FEED / "reliability.png")


# ---------------- astrometry ----------------
def astrometry():
    key = secret("ASTROMETRY_KEY")
    inbox = ROOT / "inbox" / "frames"
    files = [p for p in inbox.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff")]
    if not files:
        return "no frames"
    if not key:
        raise RuntimeError("ASTROMETRY_KEY not set")
    api = "https://nova.astrometry.net/api"
    sess = http(f"{api}/login", method="POST", data={"request-json": json.dumps({"apikey": key})}).json()["session"]
    results = read_json(FEED / "solves.json", {"rows": []})
    import requests
    for f in files:
        meta = _exif(f)
        with open(f, "rb") as fh:
            sub = requests.post(f"{api}/upload", data={"request-json": json.dumps({"session": sess, "publicly_visible": "n", "allow_commercial_use": "n", "allow_modifications": "n"})},
                                files={"file": fh}, timeout=300).json()
        subid = sub["subid"]
        job, cal = None, None
        for _ in range(60):
            time.sleep(10)
            s = http(f"{api}/submissions/{subid}").json()
            jobs = [j for j in s.get("jobs", []) if j]
            if jobs:
                job = jobs[0]
                st = http(f"{api}/jobs/{job}").json().get("status")
                if st == "success":
                    cal = http(f"{api}/jobs/{job}/calibration/").json()
                    break
                if st == "failure":
                    break
        row = {"file": f.name, "exif": meta, "job": job, "solved": bool(cal)}
        if cal:
            row.update({"ra": cal["ra"], "dec": cal["dec"], "radius_deg": cal["radius"], "orientation": cal["orientation"], "pixscale": cal["pixscale"]})
            spot = _spot_for(f.name, meta)
            if spot and meta.get("t"):
                tt_unix = dt.datetime.fromisoformat(meta["t"]).timestamp()
                ts, _ = ephem.load()
                tt = ts.utc(1970, 1, 1, 0, 0, np.array([tt_unix]))
                # frame centre RA/Dec (J2000) -> alt/az at the spot (precession ignored: <0.4 deg; fine for a pointing check)
                alt, az = ephem.altaz(np.array([cal["ra"]]), np.array([cal["dec"]]), ephem.gast_deg(tt), spot["lat"], spot["lon"])
                row.update({"spot": spot["id"], "center_alt": r(float(alt[0]), 2), "center_az": r(float(az[0]), 2)})
                # where was the Milky Way core / moon predicted to be at that moment?
                for b in ("mwcore", "moon"):
                    ra, dec, dist = ephem.radec(b, tt)
                    a2, z2 = ephem.altaz(ra, dec, ephem.gast_deg(tt), spot["lat"], spot["lon"], dist if b == "moon" else None)
                    row[f"{b}_pred"] = {"alt": r(float(a2[0]), 2), "az": r(float(z2[0]), 2), "in_frame": sep(float(z2[0]), float(a2[0]), float(az[0]), float(alt[0])) / 60 <= cal["radius"]}
        results["rows"].insert(0, row)
        done = ROOT / "inbox" / "solved"
        done.mkdir(exist_ok=True)
        f.rename(done / f.name)
    write_json("solves.json", results)
    return f"{len(files)} frames"


def _exif(p):
    try:
        from PIL import Image, ExifTags
        im = Image.open(p)
        ex = im.getexif()
        tags = {ExifTags.TAGS.get(k, k): v for k, v in ex.items()}
        sub = ex.get_ifd(0x8769)
        tags.update({ExifTags.TAGS.get(k, k): v for k, v in sub.items()})
        gps = ex.get_ifd(0x8825)
        t = tags.get("DateTimeOriginal")
        off = tags.get("OffsetTimeOriginal") or "-08:00"
        out = {"t": None, "model": tags.get("Model"), "focal": str(tags.get("FocalLength")), "exposure": str(tags.get("ExposureTime")), "iso": tags.get("ISOSpeedRatings")}
        if t:
            out["t"] = dt.datetime.strptime(t, "%Y:%m:%d %H:%M:%S").replace(tzinfo=dt.timezone(dt.timedelta(hours=int(off[:3]), minutes=int(off[0] + off[4:6])))).isoformat()
        if gps and 2 in gps and 4 in gps:
            dms = lambda v: float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            lat = dms(gps[2]) * (-1 if gps.get(1) == "S" else 1)
            lon = dms(gps[4]) * (-1 if gps.get(3) == "W" else 1)
            out["gps"] = [lat, lon]
        return out
    except Exception as e:
        return {"error": str(e)[:80]}


def _spot_for(name, meta):
    ss = spots()
    for s in ss:
        if name.lower().startswith(s["id"].lower()):
            return s
    if meta.get("gps"):
        la, lo = meta["gps"]
        return min(ss, key=lambda s: km(la, lo, s["lat"], s["lon"]))
    return None
