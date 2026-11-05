"""Getting to the spot on foot (MEASURED geometry, MODELED elevation).

For each spot: pull the walkable network and parking within 4 km from OpenStreetMap (Overpass), route from the spot
to the nearest-by-walking parking area or trailhead, and measure the route's length, the trails it uses, and its
climb from the Copernicus 90 m DEM (Open-Meteo elevation API). Resumable with a time budget; results kept in
data/trails.json and published as feed/trails.json. Refreshed every ~120 days.
"""
import heapq, json, math, time
from .common import spots, write_json, read_json, http, log, utcnow, iso, DATA

OVERPASS = "https://overpass-api.de/api/interpreter"
WALK = "path|footway|track|steps|bridleway|pedestrian|living_street|service|unclassified|residential|tertiary|secondary|primary|cycleway"
TRAILISH = {"path", "footway", "track", "steps", "bridleway", "cycleway", "pedestrian"}


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def fetch(lat, lon, r=4000):
    q = f"""[out:json][timeout:90];
(way(around:{r},{lat},{lon})[highway~"^({WALK})$"][access!~"^(private|no)$"];)->.w;
.w out geom tags;
(node(around:{r},{lat},{lon})[amenity=parking];way(around:{r},{lat},{lon})[amenity=parking];node(around:{r},{lat},{lon})[highway=trailhead];);
out center tags;"""
    return http(OVERPASS, method="POST", data={"data": q}, timeout=120, tries=3).json()["elements"]


def route(spot, els):
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
    sp = (spot["lat"], spot["lon"])
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


def run(budget_min=40):
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
            r = route(s, fetch(s["lat"], s["lon"]))
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
    json.dump(store, open(DATA / "trails.json", "w"), separators=(",", ":"))
    pub = {k: {x: v[x] for x in v if x not in ("key", "ts")} for k, v in store.items()}
    write_json("trails.json", {"gen": iso(utcnow()), "spots": pub,
                               "note": "Route from the nearest parking or trailhead on OpenStreetMap paths; climb from the Copernicus 90 m DEM (smooths short steep bits)."})
    left = len(todo) - done - fail
    return f"{done} spots routed, {fail} failed, {left} left for next run; {len(store)} total"
