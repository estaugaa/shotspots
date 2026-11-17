"""Ground truth for fog: airport weather reports (METARs) around the coverage area, from aviationweather.gov
(free, no key). Visibility, fog/mist and the lowest cloud base catch what the satellite can't see under a
higher cloud deck. Writes feed/obs.json; runs with every GOES scan."""
from .common import http, write_json, utcnow, iso, log

BBOX = "41.9,-124.8,49.1,-116.4"   # lat0,lon0,lat1,lon1: Washington and Oregon (the app shows the nearest few)


def run():
    j = http("https://aviationweather.gov/api/data/metar", params={"bbox": BBOX, "format": "json", "hours": 2},
             headers={"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots)"}, timeout=40).json()
    latest = {}
    for m in j:
        sid = m.get("icaoId")
        if sid and (sid not in latest or m.get("obsTime", 0) > latest[sid].get("obsTime", 0)):
            latest[sid] = m
    out = []
    for sid, m in latest.items():
        vis = m.get("visib")
        try:
            vis = 10.0 if str(vis).endswith("+") else float(vis)
        except (TypeError, ValueError):
            vis = None
        cl = [c for c in (m.get("clouds") or []) if c.get("cover") in ("BKN", "OVC", "VV") and c.get("base") is not None]
        base = min((c["base"] for c in cl), default=None)
        wx = m.get("wxString") or ""
        out.append({"id": sid, "name": (m.get("name") or sid).split(",")[0], "lat": m.get("lat"), "lon": m.get("lon"),
                    "t": m.get("reportTime") or m.get("obsTime"), "vis_mi": vis, "wx": wx, "base_ft": base,
                    "fog": bool(vis is not None and vis <= 1) or "FG" in wx, "mist": "BR" in wx or bool(vis is not None and 1 < vis <= 4 and not any(x in wx for x in ("RA", "SN", "DZ", "HZ", "FU")))})
    write_json("obs.json", {"gen": iso(utcnow()), "stations": out})
    try:
        _tiles()
    except Exception as e:
        log.warning("METAR tiles: %s", e)
    _keep_for_scoring(out)
    log.info("METAR: %d stations", len(out))
    return f"{len(out)} stations, {sum(o['fog'] for o in out)} with fog"


def _keep_for_scoring(out):
    """Keep reports taken within 45 min of local sunrise or sunset (data/obs_history.json, 60 days) for verify_obs."""
    import datetime as dt
    from .common import read_json, DATA
    from .sunlite import sun_times
    p = DATA / "obs_history.json"
    h = read_json(p, {"obs": []})
    have = {(o["id"], o["t"]) for o in h["obs"]}
    for o in out:
        if not o.get("lat") or not o.get("t") or (o["id"], o["t"]) in have:
            continue
        try:
            t = dt.datetime.fromtimestamp(o["t"], dt.timezone.utc) if isinstance(o["t"], (int, float)) else dt.datetime.fromisoformat(str(o["t"]).replace("Z", "+00:00").replace(" ", "T"))
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        r, s_ = sun_times(o["lat"], o["lon"], t.date())
        if r and min(abs((t - r).total_seconds()), abs((t - s_).total_seconds())) <= 45 * 60:
            rec = {k: o[k] for k in ("id", "name", "lat", "lon", "vis_mi", "wx", "base_ft", "fog")}
            rec["t"] = (t + dt.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:00")   # nearest hour, matches forecast times
            if (rec["id"], rec["t"]) not in have:
                h["obs"].append(rec); have.add((rec["id"], rec["t"]))
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=60)).strftime("%Y-%m-%dT%H:00")
    h["obs"] = [o for o in h["obs"] if o["t"] >= cut]
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(h, separators=(",", ":")))


COVER = {"FEW": 19, "SCT": 44, "BKN": 75, "OVC": 100, "VV": 100, "OVX": 100}


def _layers(m):
    """Low (< 6,500 ft) and mid (6,500-20,000 ft) cloud amount in %, from the reported layers. Automated stations only
    see to 12,000 ft, so 'clear' means clear below that; high cloud stays the forecast's."""
    low = mid = 0
    for c in m.get("clouds") or []:
        cov, base = COVER.get(c.get("cover")), c.get("base")
        if cov is None or base is None: continue
        if base < 6500: low = max(low, cov)
        elif base < 20000: mid = max(mid, cov)
    return low, mid


def _tiles():
    """Nowcast: cloud layers from every US airport report, in 5-degree tiles (feed/obsnow/<lat>_<lon>.json) so the app
    only loads stations near the user. Used for windows in the next 3 hours (app/nowcast.js)."""
    import math, json as _j
    from .common import FEED
    j = http("https://aviationweather.gov/api/data/metar", params={"bbox": "18,-170,72,-60", "format": "json", "hours": 1.5},
             headers={"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots)"}, timeout=90).json()
    latest = {}
    for m in j:
        sid = m.get("icaoId")
        if sid and m.get("lat") is not None and (sid not in latest or m.get("obsTime", 0) > latest[sid].get("obsTime", 0)):
            latest[sid] = m
    tiles = {}
    for sid, m in latest.items():
        if not m.get("clouds") and m.get("cover") not in ("CLR", "SKC", "CAVOK"): continue
        low, mid = _layers(m)
        k = f"{5 * math.floor(m['lat'] / 5)}_{5 * math.floor(m['lon'] / 5)}"
        tiles.setdefault(k, []).append([sid, round(m["lat"], 3), round(m["lon"], 3), m.get("obsTime"), low, mid, m.get("cover") or ""])
    od = FEED / "obsnow"; od.mkdir(exist_ok=True)
    for k, rows in tiles.items():
        (od / f"{k}.json").write_text(_j.dumps({"gen": iso(utcnow()), "s": rows}, separators=(",", ":")))
    log.info("METAR nowcast tiles: %d stations in %d tiles", sum(map(len, tiles.values())), len(tiles))
