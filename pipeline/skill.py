"""Forecast vs reality, every day, nationwide: did the sky at sunrise and sunset look like the forecast said?

For every US airport (ASOS, Iowa Environmental Mesonet archive) and each sunrise/sunset in the last day:
  observed  = low cloud (< 6,500 ft) and mid cloud (6,500-12,000 ft) from the report nearest the event (within 30 min)
  forecast  = the same hour's cloud cover as forecast the DAY BEFORE (saved by this job a day earlier, best_match and HRRR;
              Open-Meteo's previous-runs archive keeps no low/mid cloud)
Pairs are kept indefinitely (data/archive/skill/<month>.csv.gz); the last 60 days are used. From them:
  * skill: mean absolute error and bias of low cloud, raw vs calibrated (calibration fitted on even days, scored on odd)
  * calibration: forecast low cloud in 10%-bins -> what was actually observed on average, by region (west/east of -100)
    and model -> feed/calib.json, which the app applies to forecast low cloud (app/nowcast.js).
Automated stations see only up to 12,000 ft, so only LOW cloud is calibrated; mid is reported for information.
MEASURED (observations) against MODELED (forecasts).
"""
import csv, io, math, time, datetime as dt, glob, os
import requests
from .common import soft_fail, DATA, log, write_json, iso, utcnow
from .sunlite import sun_times

STATES = ("AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
COVER = {"FEW": 19, "SCT": 44, "BKN": 75, "OVC": 100, "VV": 100, "CLR": 0, "SKC": 0, "NSC": 0}
SKD = DATA / "skill"
MODELS = ("best_match", "gfs_hrrr")
MAX_ST = 700


def _obs(sts, ets):
    rows = []
    for st in STATES:
        url = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
        p = {"network": f"{st}_ASOS", "data": "skyc1,skyc2,skyc3,skyc4,skyl1,skyl2,skyl3,skyl4", "tz": "Etc/UTC", "format": "onlycomma",
             "latlon": "yes", "missing": "M", "trace": "T", "report_type": "3", "sts": sts.strftime("%Y-%m-%dT%H:%MZ"), "ets": ets.strftime("%Y-%m-%dT%H:%MZ")}
        for i in range(3):
            try:
                r = requests.get(url, params=p, timeout=120, headers={"User-Agent": "ShotSpots/1.0 (github.com/estaugaa/shotspots)"})
                if r.ok: rows += list(csv.DictReader(io.StringIO(r.text))); break
            except Exception as e:
                log.warning("skill obs %s: %s", st, e)
            time.sleep(5 * (i + 1))
        time.sleep(1)
    return rows


def _layers(r):
    low = mid = None; any_ = False
    for k in "1234":
        c, h = r.get("skyc" + k, "M"), r.get("skyl" + k, "M")
        if c in ("M", "", None): continue
        cov = COVER.get(c.strip())
        if cov is None: continue
        any_ = True
        if cov == 0: low = low or 0; mid = mid or 0; continue
        try: base = float(h)
        except Exception as e: soft_fail("skill: forecast hour: non-numeric", e); continue
        if base < 6500: low = max(low or 0, cov)
        elif base < 12000: mid = max(mid or 0, cov)
    if not any_: return None
    return (low or 0, mid or 0)


def _capture(stations):
    """Save today's forecast for the next sunrises/sunsets (18-42 h ahead) at a stable sample of stations:
    data/skill/fc_<date>.json {sid|hourISO: {model: [low, mid]}}. The previous-runs archive has no low/mid cloud, so the
    day-ahead forecasts are kept here and checked against the airport reports the next day."""
    import zlib, json
    now = utcnow(); ids = sorted(stations, key=lambda x: zlib.crc32(x.encode()))[:MAX_ST]
    want = {}
    for sid in ids:
        lat, lon = stations[sid]
        for d in (now.date() + dt.timedelta(days=1), now.date() + dt.timedelta(days=2)):
            st = sun_times(lat, lon, d)
            for ev in (st or []):
                if ev and 18 <= (ev - now).total_seconds() / 3600 <= 42:
                    hr = ev.replace(minute=0, second=0, microsecond=0) + (dt.timedelta(hours=1) if ev.minute >= 30 else dt.timedelta(0))
                    want.setdefault(sid, set()).add(hr.strftime("%Y-%m-%dT%H"))
    out = {}; sids = list(want)
    for m in MODELS:
        for i in range(0, len(sids), 50):
            chunk = sids[i:i + 50]
            p = {"latitude": ",".join(str(stations[x][0]) for x in chunk), "longitude": ",".join(str(stations[x][1]) for x in chunk),
                 "hourly": "cloud_cover_low,cloud_cover_mid", "forecast_days": 3, "timezone": "UTC"}
            if m != "best_match": p["models"] = m
            j = None
            for k in range(3):
                try:
                    r = requests.get("https://api.open-meteo.com/v1/forecast", params=p, timeout=60)
                    if r.ok: j = r.json(); break
                    if r.status_code == 429: time.sleep(61)
                except Exception as e:
                    log.warning("skill capture %s: %s", m, e); time.sleep(5)
            if not j: continue
            if isinstance(j, dict): j = [j]
            for sid, loc in zip(chunk, j):
                h = loc.get("hourly") or {}
                for t, lo, mi in zip(h.get("time", []), h.get("cloud_cover_low", []), h.get("cloud_cover_mid", [])):
                    if t[:13] in want[sid] and lo is not None: out.setdefault(f"{sid}|{t[:13]}", {})[m] = [lo, mi]
            time.sleep(2)
    SKD.mkdir(parents=True, exist_ok=True)
    (SKD / f"fc_{now.date().isoformat()}.json").write_text(json.dumps(out, separators=(",", ":")))
    for p_ in sorted(SKD.glob("fc_*.json"))[:-4]: p_.unlink()
    return len(out)


def _stored():
    import json
    out = {}
    for p_ in sorted(SKD.glob("fc_*.json")):
        try: out.update(json.loads(p_.read_text()))
        except Exception as e: soft_fail("skill: stored forecast file unreadable", e)
    return out


def collect():
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    sts, ets = now - dt.timedelta(hours=27), now - dt.timedelta(hours=1)
    raw = _obs(sts, ets)
    by = {}
    for r in raw:
        try:
            t = dt.datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
            lat, lon = float(r["lat"]), float(r["lon"])
        except Exception as e:
            soft_fail("skill: station with bad coordinates", e)
            continue
        lay = _layers(r)
        if lay is None: continue
        by.setdefault(r["station"], {"pos": (round(lat, 3), round(lon, 3)), "obs": []})["obs"].append((t, lay))
    events = []   # (sid, kind, event time, observed)
    for sid, d in by.items():
        lat, lon = d["pos"]
        for day in {sts.date(), ets.date()}:
            st = sun_times(lat, lon, day)
            if not st: continue
            for kind, ev in zip(("sunrise", "sunset"), st):
                if not ev or not (sts <= ev <= ets): continue
                best = min(d["obs"], key=lambda o: abs((o[0] - ev).total_seconds()))
                if abs((best[0] - ev).total_seconds()) <= 1800: events.append((sid, kind, ev, best[1]))
    pts = {sid: by[sid]["pos"] for sid, _, _, _ in events}
    stored = _stored()
    fc = {(k.split("|")[0], k.split("|")[1]): v for k, v in stored.items()}
    n_cap = _capture({sid: d["pos"] for sid, d in by.items()})
    log.info("skill: %d stored day-ahead forecasts, %d captured for tomorrow", len(stored), n_cap)
    SKD.mkdir(parents=True, exist_ok=True)
    rows = []
    for sid, kind, ev, (ol, om) in events:
        hr = ev.replace(minute=0) + (dt.timedelta(hours=1) if ev.minute >= 30 else dt.timedelta(0))
        f = fc.get((sid, hr.strftime("%Y-%m-%dT%H")))
        if not f: continue
        lat, lon = pts[sid]
        for m, (fl, fm) in f.items():
            rows.append([ev.date().isoformat(), sid, lat, lon, kind, m, fl, fm if fm is not None else "", ol, om])
    _archive([dict(zip(FIELDS, r)) for r in rows])
    return len(by), len(events), len(rows)


FIELDS = ["date", "sid", "lat", "lon", "kind", "model", "f_low", "f_mid", "o_low", "o_mid"]


def _archive(rows):
    """Pairs go to data/archive/skill/<month>.csv.gz, kept indefinitely; the daily data/skill/<date>.csv files this
    replaced are moved in once, then removed."""
    from . import archive
    old = sorted(SKD.glob("20*.csv"))
    for p in old:
        with open(p) as fh: rows = list(csv.DictReader(fh)) + rows
    archive.append("skill", FIELDS, rows, lambda r: r["date"], lambda r: (r["date"], r["sid"], r["kind"], r["model"]))
    for p in old: p.unlink()


def recent(days=60):
    from . import archive
    _archive([])
    return archive.read("skill", str(utcnow().date() - dt.timedelta(days=days)), "date")


def _bins(pairs):
    b = [[0, 0] for _ in range(11)]
    for f, o in pairs:
        k = min(10, int(f // 10)); b[k][0] += o; b[k][1] += 1
    return [[k * 10 + (5 if k < 10 else 0), round(s / n, 1) if n else None, n] for k, (s, n) in enumerate(b)]


def _apply(bins, f):
    pts = [(c, v) for c, v, n in bins if v is not None and n >= 30]
    if len(pts) < 3: return f
    if f <= pts[0][0]: return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if f <= x1: return y0 + (y1 - y0) * (f - x0) / (x1 - x0)
    return pts[-1][1]


def fit():
    rows = recent(60)
    out = {"gen": iso(utcnow()), "days": len({r["date"] for r in rows}), "note": "forecast low cloud (day ahead) -> observed at airports at sunrise/sunset", "cal": {}, "skill": {}}
    for m in MODELS:
        for reg in ("west", "east"):
            rs = [r for r in rows if r["model"] == m and ((float(r["lon"]) < -100) == (reg == "west"))]
            if len(rs) < 200: continue
            pairs = [(float(r["f_low"]), float(r["o_low"])) for r in rs]
            even = [(f, o) for (f, o), r in zip(pairs, rs) if int(r["date"][-2:]) % 2 == 0]
            odd = [(f, o) for (f, o), r in zip(pairs, rs) if int(r["date"][-2:]) % 2 == 1]
            tr, te = (even, odd) if len(even) >= len(odd) else (odd, even)
            cal = _bins(tr)
            mae = lambda ps, g: round(sum(abs(g(f) - o) for f, o in ps) / max(1, len(ps)), 1)
            out["skill"][f"{m}/{reg}"] = {"n": len(pairs), "bias": round(sum(f - o for f, o in pairs) / len(pairs), 1),
                                         "mae_raw": mae(te, lambda f: f), "mae_cal": mae(te, lambda f: _apply(cal, f)), "n_test": len(te)}
            out["cal"][f"{m}/{reg}"] = _bins(pairs)
    write_json("calib.json", out)
    return out


def run():
    n_st, n_ev, n_rows = collect()
    out = fit()
    s = "; ".join(f"{k}: n={v['n']} bias {v['bias']:+} MAE {v['mae_raw']} -> {v['mae_cal']} calibrated" for k, v in out["skill"].items())
    return f"{n_st} stations, {n_ev} sunrise/sunset reports, {n_rows} forecast pairs today; {out['days']} days kept. {s or 'not enough data yet'}"
