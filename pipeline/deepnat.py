"""Full research for the best starter spots NATIONWIDE (the test-region version is pipeline/deepspots.py).

Per 1-degree seed tile, the top TOP_PER_TILE starter spots by measured quality (birding hotspots, refuges, landmarks
and gardens excluded) get:
  * a 10 m terrain horizon (observer at the highest ground within 30 m, terrain closer than 40 m ignored), stored as a
    compact 1-degree profile; the app computes daily "sun clears the ridge" times from it (app/terrainsun.js)
  * which way it faces (east/west sectors open to the low sun)
  * the walk from the nearest parking (OpenStreetMap), distance, climb and effort
  * a short tip built from those
Output: feed/deep/<tile>.json {gen, v, spots: {id: card}} and feed/deep/index.json. Tiles are done most-photographed
first; each run has a time budget and queues the next (.more) until every tile is done. Re-done when VERSION changes.
"""
import json, math, time, glob, os
from .common import FEED, DATA, read_json, log, iso, utcnow
from .deepspots import _quality, _sector_open, SKIP

TOP_PER_TILE, VERSION = 15, 1
OD = FEED / "deep"


def _tiles_ranked():
    tiles = []
    for f in glob.glob(str(FEED / "seed" / "*_*.json")):
        k = os.path.basename(f)[:-5]
        tile = read_json(f, {}) or {}
        views = read_json(FEED / "seedviews" / f"{k}.json", {}) or {}
        pops = read_json(FEED / "seedpop" / f"{k}.json", {}) or {}
        stands = read_json(FEED / "stands" / f"{k}.json", {}) or {}
        cand = sorted(((_quality(x, views.get(x["id"]), pops.get(x["id"]), stands.get(x["id"])), x) for x in tile.get("spots", []) if x.get("kind") not in SKIP),
                      key=lambda t: -t[0])
        pick, out = [], []
        for q, x in cand:
            if any(abs(x["lat"] - y["lat"]) < 0.002 and abs(x["lon"] - y["lon"]) < 0.0025 for y in pick): continue
            pick.append(x); out.append((q, x))
            if len(pick) >= TOP_PER_TILE: break
        if out: tiles.append((sum(q for q, _ in out), k, [x for _, x in out]))
    tiles.sort(key=lambda t: -t[0])
    return tiles


def _card(s, h_alt, h0, trail):
    c, tip = {}, []
    alt2 = list(h_alt)
    e, w = _sector_open(alt2, 60, 125), _sector_open(alt2, 235, 300)
    c["light"] = "both" if e and w else "sunrise" if e else "sunset" if w else "blocked"
    if s.get("kind") in ("peak", "lookout") and c["light"] != "blocked": c["light"] = "both"
    c["hz"] = [int(round(max(alt2[2 * i], alt2[2 * i + 1]) * 10)) for i in range(360)]   # 1-degree profile, tenths of a degree
    c["el"] = round(h0 - 1.7)
    if trail and trail.get("kind") == "walk" and trail.get("m") is not None:
        mi = trail["m"] / 1609; up = trail.get("up_m") or 0
        c["eff"] = "short" if mi < 0.5 and up < 60 else "moderate" if mi < 2 and up < 250 else "hike"
        c["mi"], c["up"] = round(mi, 1), round(up * 3.281)
        park = (trail.get("park") or {}).get("name") or "the nearest parking"
        walk = "A short walk" if c["eff"] == "short" else f"{c['mi']} mi"
        tip.append(f"{walk} from {park}" + (f", {c['up']} ft of climb" if c["up"] >= 100 else "") + ".")
    elif trail and trail.get("kind") == "drive":
        c["eff"] = "short"; tip.append("You can shoot from the car or right beside it.")
    tip.append({"sunrise": "Open to the east: a sunrise spot.", "sunset": "Open to the west: a sunset spot.", "both": "Open to both sunrise and sunset.",
                "blocked": "Terrain hides the low sun: best for warm light on the scene, or in soft light."}[c["light"]])
    c["tip"] = " ".join(tip)
    return c


def run(budget_min=150):
    from . import terrain, trails
    OD.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); ranked = _tiles_ranked()
    done = {k for k in (read_json(OD / "index.json", []) or [])}
    todo = [(q, k, ss) for q, k, ss in ranked if k not in done or (read_json(OD / f"{k}.json", {}) or {}).get("v") != VERSION]
    nt = ns = 0
    for q, k, ss in todo:
        if time.time() - t0 > budget_min * 60:
            open(".more", "w").write("1"); break
        la, lo = map(int, k.split("_"))
        try:
            far = terrain.far_for(la + 0.5, lo + 0.5, f"tile_{k}", terrain.far_grid() if terrain.in_far(la + 0.5, lo + 0.5) else None)
        except Exception as e:
            log.warning("deepnat far %s: %s", k, e); far = None
        cards = {}
        for s in ss:
            try:
                near, mid = terrain.spot_grids(s["lat"], s["lon"], s["id"])
                alt, bd, h0 = terrain.horizon(s["lat"], s["lon"], [g for g in (near, mid, far) if g is not None], edge=True)
            except Exception as e:
                log.warning("deepnat terrain %s: %s", s["id"], e); continue
            tr = None
            try:
                els = trails.fetch(s["lat"], s["lon"]); time.sleep(1.5)
                tr = trails.route(s, els)
            except Exception as e:
                log.info("deepnat trail %s: %s", s["id"], e)
            cards[s["id"]] = _card(s, [float(x) for x in alt], h0, tr); ns += 1
        (OD / f"{k}.json").write_text(json.dumps({"gen": iso(utcnow()), "v": VERSION, "spots": cards}, separators=(",", ":")))
        done.add(k); nt += 1
        (OD / "index.json").write_text(json.dumps(sorted(done)))
        for f in glob.glob(str(terrain.CACHE / "dem" / "*.npy")):   # DEM cache would fill the runner's disk
            if "far_full" not in f: os.remove(f)
    left = len(todo) - nt
    return f"{nt} tiles ({ns} spots) researched this run; {len(done)} of {len(ranked)} tiles done, {left} left"
