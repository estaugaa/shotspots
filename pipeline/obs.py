"""Observations and climatology: ASOS (IEM), soundings (IEM RAOB), USGS flow percentiles, USA-NPN phenology.

ASOS climatology (MEASURED history): P(fog), P(clear below 12,000 ft) and P(low overcast) by month and local
hour from 10 years of METARs. ASOS ceilometers can't see cloud above 12,000 ft, so "clear" overstates
truly clear skies; the app says so. Used by the shot list beyond the 48-hour HRRR horizon.
"""
import csv, io, datetime as dt, json, math
import numpy as np
from zoneinfo import ZoneInfo
from .common import http, write_json, read_json, links, spots, CACHE, FEED, log, utcnow, iso, r, km

LA = ZoneInfo("America/Los_Angeles")
STATIONS = {"PDX": (45.588, -122.597), "TTD": (45.549, -122.401), "VUO": (45.621, -122.656), "DLS": (45.619, -121.166),
            "KLS": (46.118, -122.898), "SPB": (45.773, -122.862), "HIO": (45.540, -122.950)}
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"


def asos_rows(st, start, end, report_type=3):
    params = [("station", st), ("data", "vsby"), ("data", "skyc1"), ("data", "skyl1"), ("data", "skyc2"), ("data", "skyl2"),
              ("data", "skyc3"), ("data", "skyl3"), ("data", "wxcodes"), ("year1", start.year), ("month1", start.month), ("day1", start.day),
              ("year2", end.year), ("month2", end.month), ("day2", end.day), ("tz", "Etc/UTC"), ("format", "onlycomma"),
              ("latlon", "no"), ("missing", "M"), ("trace", "T"), ("direct", "no"), ("report_type", report_type)]
    txt = http(IEM, params=params, timeout=300).text
    return list(csv.DictReader(io.StringIO(txt)))


def classify(row):
    def f(x):
        try:
            return float(x)
        except Exception:
            return None
    v = f(row.get("vsby"))
    wx = row.get("wxcodes") or ""
    layers = [(row.get(f"skyc{i}"), f(row.get(f"skyl{i}"))) for i in (1, 2, 3)]
    fog = (v is not None and v <= 0.62) or ("FG" in wx and "BCFG" not in wx and "MIFG" not in wx)
    cover = [c for c, _ in layers if c and c != "M"]
    clear = bool(cover) and all(c in ("CLR", "SKC", "FEW", "NSC") for c in cover)
    low_ovc = any(c in ("BKN", "OVC", "VV") and h is not None and h <= 1000 for c, h in layers)
    return fog, clear, low_ovc


def climatology():
    end = utcnow().date()
    start = end.replace(year=end.year - 10)
    out = {}
    for st in STATIONS:
        try:
            rows = asos_rows(st, start, end)
        except Exception as e:
            log.warning("ASOS %s failed: %s", st, e)
            continue
        n = np.zeros((12, 24))
        k = np.zeros((3, 12, 24))
        for row in rows:
            try:
                t = dt.datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).astimezone(LA)
            except Exception:
                continue
            fog, clear, low = classify(row)
            n[t.month - 1, t.hour] += 1
            k[0, t.month - 1, t.hour] += fog
            k[1, t.month - 1, t.hour] += clear
            k[2, t.month - 1, t.hour] += low
        with np.errstate(invalid="ignore", divide="ignore"):
            p = np.where(n > 0, k / n, np.nan)
        out[st] = {"lat": STATIONS[st][0], "lon": STATIONS[st][1], "n": int(n.sum()),
                   "fog": np.round(p[0] * 100).tolist(), "clear12k": np.round(p[1] * 100).tolist(), "lowovc": np.round(p[2] * 100).tolist()}
    write_json("climo.json", {"gen": iso(utcnow()), "years": 10, "note": "ASOS sees cloud only below 12,000 ft", "stations": out})
    return f"{len(out)} stations, 10 years"


def asos_recent(st, t0, t1):
    rows = asos_rows(st, t0.date(), (t1 + dt.timedelta(days=1)).date(), report_type=3)
    res = []
    for row in rows:
        try:
            t = dt.datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
        if t0 <= t <= t1:
            fog, clear, low = classify(row)
            res.append({"t": iso(t), "fog": fog, "clear12k": clear, "lowovc": low, "vsby": row.get("vsby"), "sky": row.get("skyc1")})
    return res


def nearest_station(lat, lon):
    return min(STATIONS, key=lambda s: km(lat, lon, *STATIONS[s]))


# ---------- soundings (Salem, OR: SLE) ----------
def sounding():
    now = utcnow()
    res = []
    for back in range(0, 4):
        t = now - dt.timedelta(hours=12 * back)
        t = t.replace(hour=0 if t.hour < 12 else 12, minute=0, second=0, microsecond=0)
        try:
            j = http("https://mesonet.agron.iastate.edu/json/raob.py", params={"station": "KSLE", "ts": t.strftime("%Y%m%d%H00")}).json()
        except Exception as e:
            log.warning("raob %s: %s", t, e)
            continue
        prof = (j.get("profiles") or [{}])[0].get("profile") or []
        lv = [(p.get("hght"), p.get("tmpc")) for p in prof if p.get("hght") is not None and p.get("tmpc") is not None]
        if len(lv) < 5:
            continue
        lv.sort()
        z0, t0 = lv[0]
        base = top = None
        best = 0.0
        for i in range(1, len(lv)):
            z, tc = lv[i]
            if z - z0 > 2000:
                break
            if tc - t0 > best:
                best, top = tc - t0, z
        res.append({"t": iso(t), "surface_m": z0, "inv_c": round(best, 1), "top_m": top})
        if len(res) >= 2:
            break
    write_json("sounding.json", {"gen": iso(now), "station": "Salem, OR (SLE)", "obs": res,
                                 "note": "Inversion = warmest temperature above the surface within 2 km minus surface temperature; spots above top_m tend to sit above valley fog."})
    return f"{len(res)} soundings"


# ---------- USGS flow percentiles ----------
def flow():
    sites = sorted(set(links()["gauges"].values()))
    iv = http("https://waterservices.usgs.gov/nwis/iv/", params={"format": "json", "sites": ",".join(sites), "parameterCd": "00060,00065", "period": "P2D", "siteStatus": "all"}).json()
    now = {}
    for ts in iv["value"]["timeSeries"]:
        sid = ts["sourceInfo"]["siteCode"][0]["value"]
        pc = ts["variable"]["variableCode"][0]["value"]
        vals = [float(v["value"]) for v in ts["values"][0]["value"] if float(v["value"]) > -999]
        if vals:
            now.setdefault(sid, {})[pc] = vals[-1]
    st = http("https://waterservices.usgs.gov/nwis/stat/", params={"format": "rdb", "sites": ",".join(sites), "statReportType": "daily", "statTypeCd": "all", "parameterCd": "00060"}).text
    lines = [l for l in st.splitlines() if l and not l.startswith("#")]
    hdr, rows = lines[0].split("\t"), [l.split("\t") for l in lines[2:]]
    today = dt.datetime.now(LA)
    pct = {}
    keys = ["p05_va", "p10_va", "p20_va", "p25_va", "p50_va", "p75_va", "p80_va", "p90_va", "p95_va"]
    qs = [5, 10, 20, 25, 50, 75, 80, 90, 95]
    for row in rows:
        d = dict(zip(hdr, row))
        if int(d["month_nu"]) == today.month and int(d["day_nu"]) == today.day:
            vals = [float(d[k]) if d.get(k) else None for k in keys]
            pct[d["site_no"]] = dict(zip(qs, vals))
    out = {}
    for sid in sites:
        q = now.get(sid, {}).get("00060")
        p = pct.get(sid)
        perc = None
        if q is not None and p:
            pts = [(k, v) for k, v in p.items() if v is not None]
            if pts:
                if q <= pts[0][1]:
                    perc = "<5"
                elif q >= pts[-1][1]:
                    perc = ">95"
                else:
                    for (k0, v0), (k1, v1) in zip(pts, pts[1:]):
                        if v0 <= q <= v1:
                            perc = round(k0 + (k1 - k0) * (q - v0) / max(1e-9, v1 - v0))
                            break
        out[sid] = {"cfs": q, "stage_ft": now.get(sid, {}).get("00065"), "pct": perc, "median_today": p.get(50) if p else None}
    write_json("flow.json", {"gen": iso(utcnow()), "gauges": out, "note": "Percentile of today's discharge among all past years for this calendar day (USGS daily statistics)."})
    return f"{len(out)} gauges"


# ---------- USA National Phenology Network ----------
NPN_SPECIES = {"Acer macrophyllum": "bigleaf maple", "Acer circinatum": "vine maple", "Cornus nuttallii": "Pacific dogwood",
               "Balsamorhiza sagittata": "arrowleaf balsamroot", "Camassia quamash": "common camas", "Erythronium grandiflorum": "glacier lily",
               "Rhododendron macrophyllum": "Pacific rhododendron", "Populus trichocarpa": "black cottonwood", "Larix occidentalis": "western larch"}
NPN = "https://services.usanpn.org/npn_portal"


def phenology():
    sp = http(f"{NPN}/species/getSpecies.json").json()
    ids = {f'{x["genus"]} {x["species"]}': x["species_id"] for x in sp if f'{x["genus"]} {x["species"]}' in NPN_SPECIES}
    params = [("request_src", "shotspots"), ("start_date", f"{utcnow().year - 12}-01-01"), ("end_date", utcnow().date().isoformat()),
              ("bottom_left_x1", 44.6), ("bottom_left_y1", -123.6), ("upper_right_x2", 46.6), ("upper_right_y2", -120.0)]
    for i, v in enumerate(ids.values()):
        params.append((f"species_id[{i}]", v))
    obs = http(f"{NPN}/observations/getObservations.json", params=params, timeout=300).json()
    year = utcnow().year
    agg = {}
    for o in obs:
        name = f'{o.get("genus")} {o.get("species")}'
        ph = o.get("phenophase_description") or ""
        if not any(k in ph for k in ("Open flowers", "Colored leaves", "Falling leaves", "Flowers or flower buds", "Breaking leaf buds")):
            continue
        k = (name, ph)
        a = agg.setdefault(k, {"yes": [], "cur": []})
        doy = o.get("day_of_year")
        if o.get("phenophase_status") == 1 and doy:
            a["yes"].append(int(doy))
            if str(o.get("observation_date", "")).startswith(str(year)):
                a["cur"].append(int(doy))
    out = []
    for (name, ph), a in agg.items():
        if len(a["yes"]) < 5:
            continue
        y = np.array(a["yes"])
        out.append({"species": NPN_SPECIES.get(name, name), "sci": name, "phase": ph, "n": len(y),
                    "p10": int(np.percentile(y, 10)), "p50": int(np.percentile(y, 50)), "p90": int(np.percentile(y, 90)),
                    "this_year_last": max(a["cur"]) if a["cur"] else None})
    write_json("phenology.json", {"gen": iso(utcnow()), "region": "Portland–Gorge (44.6–46.6 N)", "rows": out,
                                  "note": "Day-of-year spread of 'yes' observations from USA-NPN volunteers; elevation not adjusted."})
    return f"{len(out)} species/phase curves"
