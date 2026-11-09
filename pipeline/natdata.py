"""National datasets that work anywhere in the US.

tide_stations  NOAA CO-OPS tide-prediction stations -> feed/tidestations.json (the app picks the nearest one for coast spots)
nws_fog        active NWS Dense Fog / Freezing Fog advisories with zone outlines -> feed/nwsfog.json, plus a 60-day history
               in data/nwsfog_history.json used as a second fog "truth" when scoring forecasts
"""
import datetime as dt
from .common import write_json, read_json, DATA, http, log, utcnow, iso

NWS = "https://api.weather.gov"
HDR = {"Accept": "application/geo+json"}
FOG_EVENTS = ["Dense Fog Advisory", "Freezing Fog Advisory"]


def tide_stations():
    j = http("https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json", params={"type": "tidepredictions"}).json()
    rows = [[s["id"], s["name"], round(float(s["lat"]), 4), round(float(s["lng"]), 4)] for s in j.get("stations", []) if s.get("lat") and s.get("lng")]
    write_json("tidestations.json", {"gen": iso(utcnow()), "cols": ["id", "name", "lat", "lon"], "rows": rows})
    return f"{len(rows)} stations"


def _outline(geom):
    """Bounding box + a thinned ring (every Nth point) so the app can test 'is this spot inside the advisory'."""
    if not geom:
        return None
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    rings = []
    for poly in polys:
        ring = poly[0]
        step = max(1, len(ring) // 60)
        rings.append([[round(x, 3), round(y, 3)] for x, y in ring[::step]])
    xs = [p[0] for r in rings for p in r]; ys = [p[1] for r in rings for p in r]
    return {"b": [min(xs), min(ys), max(xs), max(ys)], "r": rings}


def nws_fog():
    zc = read_json(DATA / "nwszones.json", {}) or {}
    items, fetched = [], 0
    for ev in FOG_EVENTS:
        j = http(f"{NWS}/alerts/active", params={"event": ev}, headers=HDR).json()
        for f in j.get("features", []):
            p = f["properties"]
            shapes = []
            o = _outline(f.get("geometry"))
            if o:
                shapes.append(o)
            else:
                for z in p.get("affectedZones", []):
                    zid = z.rsplit("/", 1)[-1]
                    if zid not in zc and fetched < 120:
                        try:
                            zc[zid] = _outline(http(z, headers=HDR, tries=2).json().get("geometry"))
                        except Exception as e:
                            log.warning("zone %s: %s", zid, e); zc[zid] = None
                        fetched += 1
                    if zc.get(zid):
                        shapes.append(zc[zid])
            items.append({"event": p["event"], "start": p.get("onset") or p.get("effective"), "ends": p.get("ends") or p.get("expires"),
                          "area": p.get("areaDesc", ""), "shapes": shapes})
    write_json(DATA / "nwszones.json", zc)
    write_json("nwsfog.json", {"gen": iso(utcnow()), "items": items})
    # history for scoring: one row per advisory, de-duplicated by area + start
    hist = read_json(DATA / "nwsfog_history.json", []) or []
    seen = {(h["area"], h["start"]) for h in hist}
    for it in items:
        if (it["area"], it["start"]) not in seen:
            hist.append({k: it[k] for k in ("event", "start", "ends", "area")} | {"b": [s["b"] for s in it["shapes"]]})
    cut = iso(utcnow() - dt.timedelta(days=60))
    hist = [h for h in hist if (h.get("ends") or h["start"] or "") >= cut]
    write_json(DATA / "nwsfog_history.json", hist)
    return f"{len(items)} fog advisories active"
