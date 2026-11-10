"""Breadth-first spot seed, state by state, at zero research cost.

Pulls photo-worthy places from OpenStreetMap (viewpoints, waterfalls, notable peaks, lighthouses, arches,
hot springs, refuges, notable beaches, bridges and landmarks) for a whole state, ranks them by how notable they
are (Wikidata sitelinks, a Wikipedia article, a photo on Wikidata, useful OSM detail), drops anything already in
the researched list, and writes 1° tiles to feed/seed/<lat>_<lon>.json plus feed/seed/index.json.

The app loads only the tiles around where you're planning from. Seed spots are marked "Starter" with general
tips; nightly research (RESEARCH.md, reach mode) then promotes the highest-ranked ones to full researched spots.

    python -m pipeline seed WA OR
"""
import json, math, re, time
from collections import defaultdict
from .common import http, spots, write_json, FEED, log, utcnow, iso, km, read_json

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
STATES = {k: "US-" + k for k in "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()}
PER_TILE = 120

# [key, test, cats, light, effort, base score, tip]
TYPES = [
    ("arch", lambda t: t.get("natural") == "arch" or t.get("natural") == "rock" and "arch" in t.get("name", "").lower(), ["geology"], "both", "short", 6,
     "A natural arch. Low side light at either end of the day brings out the rock texture; at night it can frame the Milky Way."),
    ("lighthouse", lambda t: t.get("man_made") == "lighthouse", ["coast", "historic"], "sunset", "short", 5,
     "Lighthouses make strong silhouettes at dusk and pair well with blue hour once the light is on."),
    ("waterfall", lambda t: t.get("waterway") == "waterfall" or t.get("natural") == "waterfall", ["waterfall"], "overcast", "short", 4,
     "Best under soft overcast or in shade so the highlights don't blow out. A slow shutter (1/4–1 s on a tripod) smooths the water; flow peaks after rain and snowmelt."),
    ("viewpoint", lambda t: t.get("tourism") == "viewpoint", ["vista"], "both", "road", 3,
     "A mapped viewpoint. Check which way it faces: east for sunrise, west for sunset. Arrive 30 minutes early to scout foreground."),
    ("hotspring", lambda t: t.get("natural") == "hot_spring", ["night"], "night", "hike", 3,
     "Steam reads best in cold air at first light. Check access rules; many springs are on private or tribal land."),
    ("refuge", lambda t: t.get("leisure") in ("nature_reserve", "bird_hide") or re.search(r"wildlife|refuge|bird", t.get("protection_title", ""), re.I) or t.get("protect_class") in ("4",) or "wildlife" in t.get("name", "").lower() and t.get("boundary") == "protected_area",
     ["wildlife", "birds"], "sunrise", "short", 3, "Wildlife is most active in the first two hours after sunrise. Stay on trails, use your car as a blind on auto routes and give animals space."),
    ("peak", lambda t: t.get("natural") == "peak", ["mountain", "vista"], "sunset", "hike", 2,
     "A notable summit. Check the road and trail first; first and last light on high ground is the reason to go, and it's often the subject from below."),
    ("beach", lambda t: t.get("natural") == "beach", ["coast", "reflection"], "sunset", "short", 2,
     "Low tide and wet sand give reflections at sunset. Check the tide table and never turn your back on the waves."),
    ("bridge", lambda t: t.get("man_made") == "bridge" or t.get("bridge:name"), ["historic", "city"], "both", "road", 2,
     "A landmark bridge: try blue hour when the lights come on, or low side light that shows the structure."),
    ("landmark", lambda t: t.get("historic") in ("castle", "fort", "monument", "ruins", "lighthouse", "mine", "ship") or t.get("tourism") == "attraction" and t.get("wikidata"),
     ["historic"], "both", "short", 2, "A landmark with history. Low light brings out texture; check opening hours if it's fenced."),
]


def _overpass(q, rounds=2):
    for i, u in enumerate(OVERPASS * rounds):
        try:
            r = http(u, method="POST", data={"data": q}, timeout=600, tries=1)
            j = r.json()
            if "runtime error" in (j.get("remark") or ""):   # Overpass answers 200 with no data when a query times out
                raise RuntimeError(j["remark"][:160])
            return j["elements"]
        except Exception as e:
            log.warning("overpass %s: %s", u, e)
            time.sleep(20 * (i + 1))
    raise RuntimeError("Overpass unavailable")


def _query_box(state, box=None, q_only=False):
    iso2 = STATES[state]
    a = "(area.s)" + (f"({box[0]},{box[1]},{box[2]},{box[3]})" if box else "")
    q = f"""[out:json][timeout:300];area["ISO3166-2"="{iso2}"][admin_level=4]->.s;(
      node{a}[tourism=viewpoint];
      node{a}[waterway=waterfall][name]; node{a}[natural=waterfall][name];
      node{a}[natural=peak][name][wikidata]; node{a}[natural=peak][name][prominence];
      nwr{a}[man_made=lighthouse];
      nwr{a}[natural=arch]; node{a}[natural=hot_spring][name];
      nwr{a}[leisure=nature_reserve][name][wikidata];
      nwr{a}[boundary=protected_area][protection_title~"Wildlife|Refuge|Bird",i][name];
      nwr{a}[leisure=bird_hide][name];
      nwr{a}[natural=beach][name][wikidata];
      way{a}[man_made=bridge][name][wikidata]; way{a}[bridge][wikidata][name];
      nwr{a}[historic~"^(castle|fort|monument|ruins|ship|mine)$"][name][wikidata];
      nwr{a}[tourism=attraction][name][wikidata];
    );out center tags;"""
    return q if q_only else _overpass(q)


def query(state):
    """Whole state in one go; big states (TX, CA...) time out, so fall back to 2° x 2° pieces of the state's bounding box."""
    try:
        els = _overpass(_query_box(state, q_only=True), rounds=1)
        if els:
            return els
    except RuntimeError:
        log.warning("%s: whole-state query failed, splitting into pieces", state)
    bb = _overpass(f'[out:json][timeout:120];rel["ISO3166-2"="{STATES[state]}"][admin_level=4];out bb;')[0]["bounds"]
    if bb["maxlon"] - bb["minlon"] > 60:   # Alaska's Aleutians cross the date line: keep the mainland
        bb = {**bb, "minlon": -170.0, "maxlon": -129.0}
    out, seen = [], set()
    la = math.floor(bb["minlat"])
    while la < bb["maxlat"]:
        lo = math.floor(bb["minlon"])
        while lo < bb["maxlon"]:
            try:
                for e in _query_box(state, (la, lo, la + 2, lo + 2)):
                    k = (e["type"], e["id"])
                    if k not in seen:
                        seen.add(k); out.append(e)
            except RuntimeError:
                log.warning("%s: piece %s,%s failed", state, la, lo)
            lo += 2
        la += 2
    return out


def wikidata(ids):
    """sitelinks count and whether there's an image, for notability."""
    out = {}
    ids = sorted(set(i for i in ids if i and i.startswith("Q")))
    for k in range(0, len(ids), 250):
        chunk = ids[k:k + 250]
        sparql = "SELECT ?i ?n ?img WHERE { VALUES ?i { " + " ".join("wd:" + i for i in chunk) + " } ?i wikibase:sitelinks ?n . OPTIONAL { ?i wdt:P18 ?img } }"
        for attempt in range(3):
            try:
                j = http("https://query.wikidata.org/sparql", params={"query": sparql, "format": "json"},
                         headers={"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots)", "Accept": "application/sparql-results+json"}, timeout=90, tries=1).json()
                for b in j["results"]["bindings"]:
                    q = b["i"]["value"].rsplit("/", 1)[1]
                    out[q] = {"n": int(b["n"]["value"]), "img": "img" in b}
                break
            except Exception as e:
                log.warning("wikidata: %s", e)
                time.sleep(10 * (attempt + 1))
        time.sleep(1)
    return out


def _tip(kind, t, base):
    bits = [base]
    if t.get("direction") and kind == "viewpoint":
        d = t["direction"]
        try:
            deg = float(d)
            d = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"][round(deg / 45) % 8]
        except ValueError:
            d = {"N": "north", "NE": "northeast", "E": "east", "SE": "southeast", "S": "south", "SW": "southwest", "W": "west", "NW": "northwest"}.get(d.upper(), d)
        bits[0] = f"A mapped viewpoint facing {d}. " + ("Good for sunrise." if "east" in d else "Good for sunset." if "west" in d else "Side light at either end of the day.") + " Arrive 30 minutes early to scout foreground."
    if t.get("height") and kind == "waterfall":
        try:
            h = float(str(t["height"]).split()[0])
            bits.append(f"About {round(h)} m ({round(h * 3.281)} ft) tall.")
        except ValueError:
            pass
    if t.get("ele") and kind == "peak":
        try:
            e = float(str(t["ele"]).split()[0])
            bits.append(f"Summit {round(e):,} m ({round(e * 3.281):,} ft).")
        except ValueError:
            pass
    if t.get("access") in ("private", "no"):
        bits.append("Mapped as private or no access: check before you go.")
    return " ".join(bits)


def build(state):
    els = query(state)
    log.info("%s: %d OSM elements", state, len(els))
    wd = wikidata([e.get("tags", {}).get("wikidata") for e in els])
    known = spots()
    kgrid = defaultdict(list)
    for s in known:
        kgrid[(round(s["lat"], 1), round(s["lon"], 1))].append(s)

    def dup(lat, lon, name):
        for dl in (-0.1, 0, 0.1):
            for dn in (-0.1, 0, 0.1):
                for s in kgrid.get((round(lat + dl, 1), round(lon + dn, 1)), []):
                    d = km(lat, lon, s["lat"], s["lon"])
                    if d < 0.3 or (d < 3 and name and name.lower() in s["name"].lower()):
                        return True
        return False

    out, seen = [], set()
    for e in els:
        t = e.get("tags", {})
        ty = next((x for x in TYPES if x[1](t)), None)
        if not ty:
            continue
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if lat is None:
            continue
        kind, _, cats, light, effort, base, tip = ty
        name = t.get("name") or t.get("name:en")
        if not name and kind != "viewpoint":
            continue
        if not name:
            name = f"Viewpoint ({round(float(str(t['ele']).split()[0]))} m)" if t.get("ele", "").replace(".", "").isdigit() else None
            if not name:
                continue  # unnamed viewpoints with no detail aren't worth a pin at state scale
        key = (name.lower(), round(lat, 2), round(lon, 2))
        if key in seen or dup(lat, lon, t.get("name")):
            continue
        seen.add(key)
        w = wd.get(t.get("wikidata"), {})
        score = base + 3 * math.log2(1 + w.get("n", 0)) + (2 if w.get("img") else 0) + (2 if t.get("wikipedia") else 0) \
            + (1 if t.get("direction") or t.get("height") or t.get("prominence") else 0) + (1 if t.get("tourism") == "viewpoint" and t.get("name") else 0)
        if kind == "peak":
            try:
                score += min(4, float(str(t.get("prominence", "0")).split()[0]) / 400)
            except ValueError:
                pass
        if t.get("access") in ("private", "no"):
            score -= 4
        out.append({"id": f"seed-{e['type'][0]}{e['id']}", "name": name, "lat": round(lat, 5), "lon": round(lon, 5), "cats": cats, "light": light, "effort": effort,
                    "tip": _tip(kind, t, tip), "kind": kind, "score": round(score, 1), "osm": f"{e['type']}/{e['id']}", "wd": t.get("wikidata"), "state": state})
    tiles = defaultdict(list)
    for s in out:
        tiles[f"{math.floor(s['lat'])}_{math.floor(s['lon'])}"].append(s)
    return tiles


def run(states):
    sdir = FEED / "seed"
    sdir.mkdir(parents=True, exist_ok=True)
    idx = read_json(sdir / "index.json", {"tiles": {}, "states": {}})
    for st in states:
        st = st.upper()
        try:
            tiles = build(st)
        except Exception as e:   # one state failing shouldn't lose the rest of the batch
            log.warning("%s failed: %s", st, e); continue
        # a tile can straddle a state line: merge with what other states already wrote there
        n = 0
        for k, lst in tiles.items():
            p = sdir / f"{k}.json"
            prev = [x for x in read_json(p, {"spots": []})["spots"] if x.get("state") != st]
            allx = sorted(prev + lst, key=lambda x: -x["score"])[:PER_TILE]
            p.write_text(json.dumps({"tile": k, "spots": allx}, separators=(",", ":")))
            idx["tiles"][k] = len(allx)
            n += sum(1 for x in allx if x["state"] == st)
        idx["states"][st] = {"at": iso(utcnow()), "spots": n, "tiles": len(tiles)}
        log.info("%s: %d seed spots in %d tiles", st, n, len(tiles))
        idx["gen"] = iso(utcnow())   # write after every state so a cancelled run still publishes what it finished
        (sdir / "index.json").write_text(json.dumps(idx, separators=(",", ":")))
    idx["gen"] = iso(utcnow())
    (sdir / "index.json").write_text(json.dumps(idx, separators=(",", ":")))
    return ", ".join(f"{k}: {v['spots']} spots" for k, v in idx["states"].items())


def candidates(lat, lon, radius_km, limit=15):
    """Top seed spots near a research target, for reach mode (promote the best, verify cheaply)."""
    sdir = FEED / "seed"
    out = []
    for la in range(math.floor(lat - 1), math.floor(lat + 1) + 1):
        for lo in range(math.floor(lon - 1.5), math.floor(lon + 1.5) + 1):
            for s in read_json(sdir / f"{la}_{lo}.json", {"spots": []})["spots"]:
                if km(lat, lon, s["lat"], s["lon"]) <= radius_km:
                    out.append({k: s[k] for k in ("id", "name", "lat", "lon", "kind", "score", "osm", "wd")})
    return sorted(out, key=lambda x: -x["score"])[:limit]
