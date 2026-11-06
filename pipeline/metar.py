"""Ground truth for fog: airport weather reports (METARs) around the coverage area, from aviationweather.gov
(free, no key). Visibility, fog/mist and the lowest cloud base catch what the satellite can't see under a
higher cloud deck. Writes feed/obs.json; runs with every GOES scan."""
from .common import http, write_json, utcnow, iso, log

BBOX = "44.8,-123.4,46.6,-120.6"   # lat0,lon0,lat1,lon1: Portland/Vancouver, the Gorge, Hood River, The Dalles


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
    log.info("METAR: %d stations", len(out))
    return f"{len(out)} stations, {sum(o['fog'] for o in out)} with fog"
