"""Getting to the spot on foot (MEASURED geometry, MODELED elevation).

For each spot: pull the walkable network and parking within 3 km from OpenStreetMap (Overpass), route from the spot
to the nearest-by-walking parking area or trailhead, and measure the route's length, the trails it uses, and its
climb from the Copernicus 90 m DEM (Open-Meteo elevation API). Resumable with a time budget; results kept in
data/trails.json and published as feed/trails.json. Refreshed every ~120 days.
"""
import heapq, json, math, time
from .common import spots, write_json, read_json, http, log, utcnow, iso, DATA

OVERPASS = "https://overpass-api.de/api/interpreter"
WALK = "path|footway|track|steps|bridleway|pedestrian|service|unclassified|cycleway"   # minor roads + paths only: keeps Overpass fast
TRAILISH = {"path", "footway", "track", "steps", "bridleway", "cycleway", "pedestrian"}


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
STOP = {"the", "and", "of", "at", "to", "from", "via", "park", "state", "viewpoint", "view", "point", "area", "trail", "lake", "mt", "mount", "national", "&", "-", "(", ")"}


def fetch(lat, lon, r=2500):
    q = f"""[out:json][timeout:90];
(way(around:{r},{lat},{lon})[highway~"^({WALK})$"][access!~"^(private|no)$"];)->.w;
.w out body geom;
(node(around:{r},{lat},{lon})[amenity=parking];way(around:{r},{lat},{lon})[amenity=parking];node(around:{r},{lat},{lon})[highway=trailhead];
 node(around:3000,{lat},{lon})[tourism=viewpoint][name];node(around:3000,{lat},{lon})[natural~"^(peak|cliff|saddle|arch|rock)$"][name];
 node(around:3000,{lat},{lon})[waterway=waterfall][name];node(around:3000,{lat},{lon})[natural=water][name];way(around:3000,{lat},{lon})[natural=water][name];);
out center tags;"""
    last = None
    for u in MIRRORS:
        try:
            return http(u, method="POST", data={"data": q}, timeout=120, tries=2).json()["elements"]
        except Exception as e:
            last = e
    raise last


def words(s):
    import re
    ws = {w for w in re.findall(r"[a-z0-9]+", s.lower().replace("'s", "").replace("’s", "").replace("'", "")) if w not in STOP and len(w) > 2}
    return {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in ws}


def pin_check(spot, els):
    """A named OSM feature (viewpoint, peak, waterfall, lake...) that matches the spot's name, if the pin is >150 m from it."""
    sw = words(spot["name"].split("(")[0]) or words(spot["name"])
    best = None
    for e in els:
        t = e.get("tags", {})
        if not t.get("name") or not (t.get("tourism") == "viewpoint" or t.get("natural") or t.get("waterway") == "waterfall"):
            continue
        ow = words(t["name"])
        if not ow:
            continue
        overlap = len(sw & ow) / max(1, len(sw))   # share of the spot's own name the OSM feature covers
        if overlap < 0.67:
            continue
        c = (e["lat"], e["lon"]) if "lat" in e else (e["center"]["lat"], e["center"]["lon"])
        d = hav((spot["lat"], spot["lon"]), c)
        kind = t.get("tourism") or t.get("natural") or t.get("waterway")
        if not best or (overlap, -d) > (best[0], -best[1]):
            best = (overlap, d, c, t["name"], kind)
    if best and best[1] > 150:
        return {"name": best[3], "kind": best[4], "lat": round(best[2][0], 5), "lon": round(best[2][1], 5), "off_m": round(best[1]), "match": round(best[0], 2)}
    return None


def route(spot, els, target=None):
    coord, adj, wayname = {}, {}, {}
    parks = []
    for e in els:
        if e["type"] == "way" and "geometry" in e and "highway" in e.get("tags", {}):
            hw = e["tags"]["highway"]
            ids = e.get("nodes") or []
            for k, g in enumerate(e["geometry"]):
                coord[ids[k]] = (g["lat"], g["lon"])
            for a, b in zip(ids, ids[1:]):
                d = hav(coord[a], coord[b])
                adj.setdefault(a, []).append((b, d, e["id"]))
                adj.setdefault(b, []).append((a, d, e["id"]))
            wayname[e["id"]] = (e["tags"].get("name") or e["tags"].get("ref") or "", hw)
        elif e.get("tags", {}).get("amenity") == "parking" or e.get("tags", {}).get("highway") == "trailhead":
            c = (e["lat"], e["lon"]) if "lat" in e else (e["center"]["lat"], e["center"]["lon"])
            parks.append({"lat": c[0], "lon": c[1], "name": e["tags"].get("name") or ("Trailhead" if e["tags"].get("highway") == "trailhead" else "Parking"),
                          "fee": e["tags"].get("fee"), "th": e["tags"].get("highway") == "trailhead"})
    if not coord:
        return {"kind": "none"}
    if spot.get("park"):
        parks.append({"lat": spot["park"][0], "lon": spot["park"][1], "name": "Trailhead parking", "fee": None, "th": True})
    sp = target or (spot["lat"], spot["lon"])
    start = min(coord, key=lambda n: hav(sp, coord[n]))
    off = hav(sp, coord[start])
    if off > 400:
        return {"kind": "none", "note": f"no mapped path within 400 m (nearest {round(off)} m)"}
    # snap parking areas to the network
    snap = {}
    for p in parks:
        n = min(coord, key=lambda m: hav((p["lat"], p["lon"]), coord[m]))
        if hav((p["lat"], p["lon"]), coord[n]) <= 150:
            snap.setdefault(n, p)
    dist, prev = {start: 0.0}, {}
    pq = [(0.0, start)]
    found = None
    while pq:
        d, n = heapq.heappop(pq)
        if d > dist.get(n, 1e18):
            continue
        if n in snap:
            found = n
            break
        if d > 15000:
            break
        for m, w, wid in adj.get(n, []):
            nd = d + w
            if nd < dist.get(m, 1e18):
                dist[m], prev[m] = nd, (n, wid)
                heapq.heappush(pq, (nd, m))
    if found is None:
        return {"kind": "none", "note": "no parking reachable on mapped paths within 15 km"}
    path, ways, n = [found], [], found
    while n != start:
        n, wid = prev[n]
        path.append(n)
        ways.append(wid)
    pts = [coord[k] for k in path]            # parking -> spot
    trail_names = []
    for wid in ways:
        nm, hw = wayname[wid]
        if hw in TRAILISH and nm and nm not in trail_names:
            trail_names.append(nm)
    on_trail = sum(hav(coord[a], coord[b]) for a, b in zip(path, path[1:]) if any(wayname[w][1] in TRAILISH for m, _, w in adj[a] if m == b))
    p = snap[found]
    return {"kind": "roadside" if dist[found] + off < 250 else "walk", "m": round(dist[found] + off), "trail_m": round(on_trail),
            "park": {"name": p["name"], "lat": round(p["lat"], 5), "lon": round(p["lon"], 5), "fee": p["fee"], "trailhead": p["th"]},
            "trails": trail_names[:4], "pts": pts}


def profile(pts):
    """Climb and descent from parking to the spot, sampling every ~60 m on the route."""
    samp, acc = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:]):
        acc += hav(a, b)
        if acc >= 60:
            samp.append(b)
            acc = 0.0
    if samp[-1] != pts[-1]:
        samp.append(pts[-1])
    samp = samp[:: max(1, len(samp) // 99 + (1 if len(samp) > 99 else 0))][:100]
    j = http("https://api.open-meteo.com/v1/elevation", params={"latitude": ",".join(f"{p[0]:.5f}" for p in samp),
                                                               "longitude": ",".join(f"{p[1]:.5f}" for p in samp)}, timeout=60, tries=3).json()
    z = j["elevation"]
    up = sum(max(0, b - a) for a, b in zip(z, z[1:]))
    down = sum(max(0, a - b) for a, b in zip(z, z[1:]))
    return round(up), round(down), round(z[0]), round(z[-1])


FIXABLE = {"waterfall": {"waterfall"}, "peak": {"vista", "mountain"}, "viewpoint": {"vista", "mountain", "city", "reflection"}, "cliff": {"vista"}, "rock": {"vista", "geology"}, "arch": {"geology", "coast"}}


def apply_pins(store):
    """Move pins to the matching OSM feature when the evidence is strong; the old pin becomes the parking point.
    Every change is logged in data/pin_fixes.json (with the old position) so it can be reviewed or undone."""
    from .common import CONFIG
    log_ = read_json(DATA / "pin_fixes.json", [])
    done = {x["id"] for x in log_}
    files = [CONFIG / "spots.json"] + sorted((DATA / "research" / "spots").glob("*.json"))
    n = 0
    for f in files:
        arr = json.load(open(f))
        changed = False
        for sp in arr:
            r = store.get(sp["id"]) or {}
            ps = r.get("pin_suggest")
            if not ps or sp["id"] in done or ps["match"] < 1.0 or not (300 < ps["off_m"] <= 3000):
                continue
            if not (FIXABLE.get(ps["kind"], set()) & set(sp["cats"])):
                continue
            old = [sp["lat"], sp["lon"]]
            sp["lat"], sp["lon"] = ps["lat"], ps["lon"]
            if not sp.get("park"):
                sp["park"] = old
            log_.append({"id": sp["id"], "name": sp["name"], "old": old, "new": [ps["lat"], ps["lon"]], "osm": ps["name"], "kind": ps["kind"], "off_m": ps["off_m"], "at": iso(utcnow())})
            store.pop(sp["id"], None)          # re-route from the new pin next run
            changed = True
            n += 1
        if changed:
            json.dump(arr, open(f, "w"), indent=1 if f.name == "spots.json" else None, ensure_ascii=False)
    json.dump(log_, open(DATA / "pin_fixes.json", "w"), indent=1)
    return n


def run(budget_min=75):
    t0 = time.time()
    store = read_json(DATA / "trails.json", {})
    todo = []
    for s in spots():
        old = store.get(s["id"])
        if old and old.get("key") == f"{s['lat']:.5f},{s['lon']:.5f}" and (utcnow().timestamp() - old.get("ts", 0)) < 120 * 86400:
            continue
        todo.append(s)
    done = fail = 0
    for s in todo:
        if time.time() - t0 > budget_min * 60:
            break
        try:
            els = fetch(s["lat"], s["lon"])
            pin = pin_check(s, els)
            r = route(s, els, (pin["lat"], pin["lon"]) if pin and pin["off_m"] < 2500 else None)
            if pin:
                r["pin_suggest"] = pin
            if r.get("pts") and len(r["pts"]) > 1 and r["kind"] == "walk":
                r["up_m"], r["down_m"], r["z_park"], r["z_spot"] = profile(r["pts"])
            r.pop("pts", None)
            r["key"], r["ts"] = f"{s['lat']:.5f},{s['lon']:.5f}", int(utcnow().timestamp())
            store[s["id"]] = r
            done += 1
        except Exception as e:
            log.warning("trail %s: %s", s["id"], e)
            fail += 1
        time.sleep(1.5)   # be polite to Overpass
        if done % 20 == 0:
            json.dump(store, open(DATA / "trails.json", "w"), separators=(",", ":"))
    moved = apply_pins(store)
    json.dump(store, open(DATA / "trails.json", "w"), separators=(",", ":"))
    pub = {k: {x: v[x] for x in v if x not in ("key", "ts")} for k, v in store.items()}
    write_json("trails.json", {"gen": iso(utcnow()), "spots": pub,
                               "note": "Route from the nearest parking or trailhead on OpenStreetMap paths; climb from the Copernicus 90 m DEM (smooths short steep bits)."})
    left = len(todo) - done - fail
    return f"{done} spots routed, {fail} failed, {left} left for next run; {len(store)} total; {moved} pins moved to OSM features (data/pin_fixes.json)"
