"""Full research for the best starter spots, so they get what the hand-researched spots get.

select(): in each region, the top starter spots by quality (Wikipedia links and views, photo counts, photographer
          stands; birding hotspots and refuges excluded) -> data/deep_spots.json. The terrain, light and trails jobs
          then include them (common.spots(deep=True)): a 10 m terrain horizon, daily "sun clears the ridge" times,
          and the walk from the nearest parking.
cards():  from those results plus learned photo light/months and stands, a research card per spot ->
          feed/deep.json {id: {light, eff, mi, up, months, tip}}; the app merges it into the starter spot.
Regions: the test regions first (REGIONS); widen later.
"""
import json, math, glob, time
from .common import FEED, DATA, read_json, write_json, log, km, iso, utcnow

REGIONS = {  # name: (lat, lon)
    "Moab": (38.573, -109.55), "Acadia": (44.35, -68.24), "Bend": (44.058, -121.315), "Zion": (37.2, -112.99),
    "San Diego": (32.8, -117.25), "Cannon Beach": (45.892, -123.961), "Sedona": (34.87, -111.76), "Grand Canyon": (36.06, -112.14),
    "Smokies": (35.65, -83.5), "Seattle": (47.61, -122.33),
}
RADIUS_KM, PER_REGION = 70, 30
SKIP = {"hotspot", "refuge", "landmark", "bridge", "cave", "garden"}


def _tiles_near(lat, lon):
    return [f"{a}_{b}" for a in range(math.floor(lat) - 1, math.floor(lat) + 2) for b in range(math.floor(lon) - 1, math.floor(lon) + 2)]


def _quality(x, views, pop, stand):
    q = math.log10(max(1, x.get("score") or 1)) * 2
    if views: q += max(0, math.log10(views) - 3.3) * 1.2
    if pop: q += math.log10(1 + (pop[1] or 0) + (pop[3] or 0)) * 1.5
    if stand: q += min(3, (stand.get("u") or 0) * 0.5)
    return q


def select():
    out, seen = [], set()
    icons = read_json(FEED / "icons.json", {}).get("spots", [])
    for reg, (lat, lon) in REGIONS.items():
        cand = []
        for t in _tiles_near(lat, lon):
            tile = read_json(FEED / "seed" / f"{t}.json", None)
            if not tile: continue
            views = read_json(FEED / "seedviews" / f"{t}.json", {}) or {}
            pops = read_json(FEED / "seedpop" / f"{t}.json", {}) or {}
            stands = read_json(FEED / "stands" / f"{t}.json", {}) or {}
            for x in tile.get("spots", []):
                if x.get("kind") in SKIP or km(lat, lon, x["lat"], x["lon"]) > RADIUS_KM: continue
                cand.append((_quality(x, views.get(x["id"]), pops.get(x["id"]), stands.get(x["id"])), x))
        for c in icons:
            if km(lat, lon, c["lat"], c["lon"]) <= RADIUS_KM: cand.append((6 + math.log10(max(1, c.get("views", 1))), c))
        cand.sort(key=lambda t: -t[0]); n = 0
        for q, x in cand:
            if x["id"] in seen: continue
            if any(abs(x["lat"] - y["lat"]) < 0.002 and abs(x["lon"] - y["lon"]) < 0.0025 for y in out): continue   # same place
            out.append({"id": x["id"], "name": x["name"], "lat": x["lat"], "lon": x["lon"], "cats": x.get("cats") or ["vista"], "kind": x.get("kind"), "region": reg, "q": round(q, 2), "deep": True})
            seen.add(x["id"]); n += 1
            if n >= PER_REGION: break
    (DATA / "deep_spots.json").write_text(json.dumps(out, separators=(",", ":")))
    return out


def _sector_open(alt, a0, a1):
    """alt: horizon altitude every 0.5 deg of azimuth. Median over the sector < 2 deg = open to the low sun."""
    v = sorted(alt[int(a0 * 2):int(a1 * 2)])
    return v[len(v) // 2] < 2 if v else None


def cards():
    deep = read_json(DATA / "deep_spots.json", [])
    H = read_json(DATA / "horizons.json", {}); T = read_json(DATA / "trails.json", {}); P = read_json(DATA / "photostats.json", {})
    L = read_json(FEED / "light.json", {}); MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    out = {}
    for s in deep:
        c, tip = {}, []
        h = H.get(s["id"])
        if h:
            e, w = _sector_open(h["alt"], 60, 125), _sector_open(h["alt"], 235, 300)
            c["light"] = "both" if e and w else "sunrise" if e else "sunset" if w else "blocked"
            if s.get("kind") in ("peak", "lookout") and c["light"] != "blocked": c["light"] = "both"
        t = T.get(s["id"])
        if t and t.get("kind") == "walk" and t.get("m") is not None:
            mi = t["m"] / 1609; up = t.get("up_m") or 0
            c["eff"] = "short" if mi < 0.5 and up < 60 else "moderate" if mi < 2 and up < 250 else "hike"
            c["mi"], c["up"] = round(mi, 1), round(up * 3.281)
            park = (t.get("park") or {}).get("name") or "the nearest parking"
            walk = "A short walk" if c["eff"] == "short" else f"{c['mi']} mi"
            tip.append(f"{walk} from {park}" + (f", {c['up']} ft of climb" if c["up"] >= 100 else "") + ".")
        elif t and t.get("kind") == "drive":
            c["eff"] = "short"; tip.append("You can shoot from the car or right beside it.")
        ps = P.get(s["id"]) or {}
        if ps.get("months"): c["months"] = ps["months"]
        if ps.get("light") in ("sunrise", "sunset", "night") and ps.get("n", 0) >= 8:
            tip.append(f"Most photos here are taken at {ps['light'] if ps['light'] != 'night' else 'night'} ({ps['n']} dated photos).")
        rows = (L.get("spots") or {}).get(s["id"])
        if rows and rows[0]:
            d = rows[0]
            if d.get("tr") and d.get("or") and d["tr"] - d["or"] >= 15: tip.append(f"Terrain delays sunrise here by about {d['tr'] - d['or']} minutes.")
            if d.get("ts") and d.get("os") and d["os"] - d["ts"] >= 15: tip.append(f"The sun leaves this spot about {d['os'] - d['ts']} minutes before sunset.")
        if c.get("light") == "sunrise": tip.append("Open to the east: a sunrise spot.")
        elif c.get("light") == "sunset": tip.append("Open to the west: a sunset spot.")
        elif c.get("light") == "blocked": tip.append("Terrain hides the low sun: best for warm light on the scene, or in soft light.")
        if tip: c["tip"] = " ".join(tip)
        if c: out[s["id"]] = c
    write_json("deep.json", {"gen": iso(utcnow()), "spots": out, "regions": list(REGIONS)})
    return out


def run():
    sel = select()
    from . import terrain, trails, light
    ids = {s["id"] for s in sel}
    a = terrain.run(only=ids, budget_min=150)
    b = trails.run(budget_min=60)
    c = light.daily()
    cs = cards()
    return f"{len(sel)} spots selected in {len(REGIONS)} regions; terrain: {a}; trails: {b}; light: {c}; {len(cs)} research cards"
