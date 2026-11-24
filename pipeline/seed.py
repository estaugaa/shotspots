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
from pathlib import Path
from collections import defaultdict
from .common import secret, http, spots, write_json, FEED, DATA, log, utcnow, iso, km, read_json, soft_fail

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
STATES = {k: "US-" + k for k in "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()}
PER_TILE = 200
TIMEOUT = 600     # per request; pieces use a shorter one
FAILED = set()    # (state, tile) pieces that failed this run: keep what those tiles had before
KIND_FLOOR = 20   # every kind keeps its best few per tile, so peaks can't crowd out viewpoints, lakes and birding spots

# Air-traffic control towers are often mapped tower:type=observation (Denver's old Stapleton tower led sunset lists, Nov 16-23):
# a working or closed building, not a lookout. "Fire control towers" (coastal artillery spotting towers) are real lookouts.
# Fire-department training and drill towers are tagged the same way (Greeley's was #6 for Denver sunset, Nov 24; 10 nationally).
NOT_LOOKOUT = re.compile(r"(?<!fire )control tower|air traffic|\bATCT\b|\btraining (tower|cent(er|re)|facility)\b|\bdrill tower\b", re.I)

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
    ("lookout", lambda t: t.get("man_made") == "tower" and re.search(r"observation|fire", t.get("tower:type", "") + " " + t.get("name", ""), re.I) and not NOT_LOOKOUT.search(t.get("name", "")),["vista", "mountain"], "both", "hike", 4,
     "A lookout tower or fire lookout: a full-circle view, so it works at sunrise and sunset. Many are staffed in summer and some can be rented."),
    ("pass", lambda t: t.get("mountain_pass") == "yes", ["mountain", "vista"], "both", "road", 2,
     "A mountain pass: easy high ground by car. Fog often fills the valleys on either side at sunrise; check winter road conditions."),
    ("cave", lambda t: t.get("natural") == "cave_entrance", ["geology"], "both", "short", 2,
     "A cave entrance. Bring a headlamp and a tripod; light from the opening makes the picture. Check whether it's closed for bats or ice."),
    ("lake", lambda t: t.get("natural") == "water" and t.get("water", "lake") in ("lake", "reservoir", "pond", "oxbow"), ["reflection", "vista"], "both", "road", 2,
     "A lake: calm air at dawn gives mirror reflections, and mist often sits on the water on cold mornings."),
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
            r = http(u, method="POST", data={"data": q}, timeout=TIMEOUT, tries=1)
            j = r.json()
            if "runtime error" in (j.get("remark") or ""):   # Overpass answers 200 with no data when a query times out
                raise RuntimeError(j["remark"][:160])
            return j["elements"]
        except Exception as e:
            log.warning("overpass %s: %s", u, e)
            time.sleep(10 * (i + 1))
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
      nwr{a}[natural=beach][name];
      nwr{a}[natural=water][name][wikidata];
      node{a}[mountain_pass=yes][name];
      nwr{a}[man_made=tower]["tower:type"~"observation|fire"][name];
      node{a}[natural=cave_entrance][name];
      way{a}[man_made=bridge][name][wikidata]; way{a}[bridge][wikidata][name];
      nwr{a}[historic~"^(castle|fort|monument|ruins|ship|mine)$"][name][wikidata];
      nwr{a}[tourism=attraction][name][wikidata];
    );out center tags;"""
    return q if q_only else _overpass(q)


GEOFABRIK = {"AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
             "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas", "KY": "kentucky",
             "LA": "louisiana", "ME": "maine", "MD": "maryland", "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi", "MO": "missouri",
             "MT": "montana", "NE": "nebraska", "NV": "nevada", "NH": "new-hampshire", "NJ": "new-jersey", "NM": "new-mexico", "NY": "new-york", "NC": "north-carolina",
             "ND": "north-dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania", "RI": "rhode-island", "SC": "south-carolina", "SD": "south-dakota",
             "TN": "tennessee", "TX": "texas", "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west-virginia", "WI": "wisconsin", "WY": "wyoming"}


def _wanted(typ, t):
    """The same selection as the Overpass query, applied to tags from the state extract."""
    has = lambda *k: all(t.get(x) for x in k)
    if typ == "n" and t.get("tourism") == "viewpoint": return True
    if typ == "n" and (t.get("waterway") == "waterfall" or t.get("natural") == "waterfall") and has("name"): return True
    if typ == "n" and t.get("natural") == "peak" and has("name") and (t.get("wikidata") or t.get("prominence")): return True
    if t.get("man_made") == "lighthouse" or t.get("natural") == "arch": return True
    if typ == "n" and t.get("natural") in ("hot_spring", "cave_entrance") and has("name"): return True
    if t.get("leisure") == "nature_reserve" and has("name", "wikidata"): return True
    if t.get("boundary") == "protected_area" and has("name") and re.search(r"wildlife|refuge|bird", t.get("protection_title", ""), re.I): return True
    if t.get("leisure") == "bird_hide" and has("name"): return True
    if t.get("natural") == "beach" and has("name"): return True
    if t.get("natural") == "water" and has("name", "wikidata"): return True
    if typ == "n" and t.get("mountain_pass") == "yes" and has("name"): return True
    if t.get("man_made") == "tower" and re.search(r"observation|fire", t.get("tower:type", ""), re.I) and has("name") and not NOT_LOOKOUT.search(t["name"]): return True
    if typ == "w" and (t.get("man_made") == "bridge" or t.get("bridge")) and has("name", "wikidata"): return True
    if re.match(r"^(castle|fort|monument|ruins|ship|mine)$", t.get("historic", "")) and has("name", "wikidata"): return True
    if t.get("tourism") == "attraction" and has("name", "wikidata"): return True
    return False


def _from_extract(state):
    """Download the state's OpenStreetMap extract (Geofabrik) and filter it locally with osmium - no busy public servers."""
    import subprocess, tempfile, shutil
    if not shutil.which("osmium") or state not in GEOFABRIK:
        return None
    d = Path(tempfile.mkdtemp())
    pbf, sub, js = d / "s.osm.pbf", d / "f.osm.pbf", d / "f.geojsonseq"
    url = f"https://download.geofabrik.de/north-america/us/{GEOFABRIK[state]}-latest.osm.pbf"
    subprocess.run(["curl", "-sfL", "--retry", "3", "-o", str(pbf), url], check=True, timeout=1800)
    flt = ["n/tourism=viewpoint", "n/waterway=waterfall", "n/natural=waterfall,peak,hot_spring,cave_entrance", "nwr/man_made=lighthouse,tower", "nwr/natural=arch,beach,water",
           "nwr/leisure=nature_reserve,bird_hide", "nwr/boundary=protected_area", "n/mountain_pass=yes", "w/man_made=bridge", "w/bridge", "nwr/historic", "nwr/tourism=attraction"]
    subprocess.run(["osmium", "tags-filter", "-O", "-o", str(sub), str(pbf), *flt], check=True, timeout=1800)
    subprocess.run(["osmium", "export", "-O", "-f", "geojsonseq", "--add-unique-id=type_id", "-o", str(js), str(sub)], check=True, timeout=1800)
    els = []
    with open(js) as fh:
        for line in fh:
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            f = json.loads(line); t = f.get("properties") or {}; uid = str(f.get("id") or t.pop("@id", ""))
            typ = uid[:1]
            if typ not in "nwr" or not _wanted(typ, t):
                continue
            g = f.get("geometry") or {}; c = g.get("coordinates")
            if g.get("type") == "Point": lon, lat = c
            else:
                flat = []
                def walk(x):
                    if x and isinstance(x[0], (int, float)): flat.append(x)
                    else:
                        for y in x: walk(y)
                walk(c)
                if not flat: continue
                lon = sum(p[0] for p in flat) / len(flat); lat = sum(p[1] for p in flat) / len(flat)
            els.append({"type": {"n": "node", "w": "way", "r": "relation"}[typ], "id": int(uid[1:]) if uid[1:].isdigit() else uid[1:], "lat": lat, "lon": lon, "tags": t})
    shutil.rmtree(d, ignore_errors=True)
    # several features can come from one OSM object (e.g. a relation as area and lines): keep one
    uniq = {}
    for e in els: uniq.setdefault((e["type"], e["id"]), e)
    log.info("%s: %d elements from the Geofabrik extract", state, len(uniq))
    return list(uniq.values())


def query(state):
    try:
        els = _from_extract(state)
        if els is not None:
            return els
    except Exception as e:
        log.warning("%s: extract route failed (%s); trying Overpass", state, e)
    """Whole state in one go; big states (TX, CA...) time out, so fall back to 1° pieces of the state's bounding box."""
    global TIMEOUT
    try:
        TIMEOUT = 400
        els = _overpass(_query_box(state, q_only=True), rounds=1)
        if els:
            return els
    except RuntimeError:
        log.warning("%s: whole-state query failed, splitting into pieces", state)
    TIMEOUT = 170
    bb = _overpass(f'[out:json][timeout:120];rel["ISO3166-2"="{STATES[state]}"][admin_level=4];out bb;')[0]["bounds"]
    if bb["maxlon"] - bb["minlon"] > 60:   # Alaska's Aleutians cross the date line: keep the mainland
        bb = {**bb, "minlon": -170.0, "maxlon": -129.0}
    out, seen = [], set()
    la = math.floor(bb["minlat"])
    while la < bb["maxlat"]:
        lo = math.floor(bb["minlon"])
        while lo < bb["maxlon"]:
            try:
                for e in _overpass(_query_box(state, (la, lo, la + 1, lo + 1), q_only=True).replace("[timeout:300]", "[timeout:150]"), rounds=1):
                    k = (e["type"], e["id"])
                    if k not in seen:
                        seen.add(k); out.append(e)
            except RuntimeError:
                log.warning("%s: piece %s,%s failed", state, la, lo); FAILED.add((state, f"{la}_{lo}"))
            lo += 1
        la += 1
    return out


def wikidata(ids):
    """sitelinks count and whether there's an image, for notability; plus where the item is (P625) and what it is (P31),
    so fame borrowed from another item can be told apart (_borrowed)."""
    out = {}
    ids = sorted(set(i for i in ids if i and i.startswith("Q")))
    for k in range(0, len(ids), 250):
        chunk = ids[k:k + 250]
        sparql = "SELECT ?i ?n ?img ?c ?cl ?lab WHERE { VALUES ?i { " + " ".join("wd:" + i for i in chunk) + " } ?i wikibase:sitelinks ?n . OPTIONAL { ?i wdt:P18 ?img } OPTIONAL { ?i wdt:P625 ?c } OPTIONAL { ?i wdt:P31 ?cl } OPTIONAL { ?i rdfs:label ?lab FILTER(lang(?lab) = 'en') } }"
        for attempt in range(3):
            try:
                j = http("https://query.wikidata.org/sparql", method="POST", data={"query": sparql, "format": "json"},
                         headers={"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots)", "Accept": "application/sparql-results+json"}, timeout=90, tries=1).json()
                for b in j["results"]["bindings"]:
                    q = b["i"]["value"].rsplit("/", 1)[1]
                    o = out.setdefault(q, {"n": int(b["n"]["value"]), "img": False, "c": None, "cl": [], "lab": None})
                    if "lab" in b: o["lab"] = b["lab"]["value"]
                    o["img"] = o["img"] or "img" in b
                    m = "c" in b and re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", b["c"]["value"])
                    if m and not o["c"]: o["c"] = (float(m.group(2)), float(m.group(1)))
                    cl = "cl" in b and b["cl"]["value"].rsplit("/", 1)[1]
                    if cl and cl not in o["cl"]: o["cl"].append(cl)
                break
            except Exception as e:
                log.warning("wikidata: %s", e)
                time.sleep(10 * (attempt + 1))
        time.sleep(1)
    return out


def _score(kind, base, t, w):
    """How notable a starter spot is. w: its Wikidata record, or None when that fame belongs to something else (_borrowed)."""
    w = w or {}
    score = base + 3 * math.log2(1 + w.get("n", 0)) + (2 if w.get("img") else 0) + (2 if t.get("wikipedia") and w else 0) \
        + (1 if t.get("direction") or t.get("height") or t.get("prominence") else 0) + (1 if t.get("tourism") == "viewpoint" and t.get("name") else 0)
    if kind == "peak":
        try:
            score += min(4, float(str(t.get("prominence", "0")).split()[0]) / 400)
        except ValueError:
            pass
    if t.get("access") in ("private", "no"):
        score -= 4
    return score


# Borrowed fame: an OSM object tagged with the Wikidata item of something else. Denver's old Stapleton control tower carried
# the whole airport's item (110k Wikipedia views a year) and led Denver sunsets; memorial tanks carry the tank model's item.
# The spot stays; only the fame (sitelinks, image, Wikipedia views) goes. Measured on every seed spot: docs/DECISIONS.md.
# Natural features (lakes, peaks, falls, refuges...) are what their item is about even when the item has no point or a far one
# (a big park's point is its middle): the location rules apply to man-made kinds only, and not to mapped areas (relations).
MADE_KINDS = {"landmark", "bridge", "lookout", "viewpoint", "lighthouse"}
FAR_KM = 50   # under ~30 km it is the same thing with a rough point (covered bridges, Badwater); past 50 km always another (the other Disney park's ride)
# Wikidata classes (P31, direct) that are no place to photograph a view from, picked from every class the seed items use (Nov 23).
# Museum ships, mines, memorials, museums and plain "power station" (Crystal Mill) stay: often photographed. Subclasses are listed, not inferred.
NOT_A_VIEW = {
    **dict.fromkeys(["Q1144661", "Q208322", "Q1934961", "Q1139917", "Q2870166", "Q512504", "Q50348261", "Q1412219", "Q177002", "Q1454206"], "amusement ride"),
    **dict.fromkeys(["Q204832", "Q2389789", "Q973560", "Q1640829", "Q627421", "Q7465804", "Q517842", "Q3080599", "Q112769012", "Q42178109", "Q689709",
                     "Q1265865", "Q358738", "Q1414671", "Q2516297", "Q1476801", "Q1130875", "Q3322352", "Q2791298", "Q923991"], "roller coaster"),
    **dict.fromkeys(["Q132241", "Q868557", "Q2699757", "Q11483816", "Q18608583", "Q40244", "Q51404"], "event"),
    **dict.fromkeys(["Q43229", "Q163740", "Q1899015", "Q4830453", "Q18325436", "Q5341295", "Q742421", "Q134884827", "Q18534542"], "organisation"),
    **dict.fromkeys(["Q5"], "person"), **dict.fromkeys(["Q16521", "Q113828342"], "species"),
    **dict.fromkeys(["Q100709275", "Q100710213", "Q137188255", "Q15056993", "Q15056995", "Q3231690", "Q42889", "Q20650761", "Q753779", "Q917028", "Q2070019"], "vehicle model"),
    **dict.fromkeys(["Q1248784", "Q644371", "Q695850", "Q6981985"], "airport"),
    **dict.fromkeys(["Q16917", "Q64578911", "Q2387974"], "hospital"), **dict.fromkeys(["Q3914", "Q1244442"], "school"), **dict.fromkeys(["Q40357", "Q683992"], "prison"),
    **dict.fromkeys(["Q27686", "Q63099748", "Q133215", "Q7338100"], "hotel or casino"), **dict.fromkeys(["Q1021645"], "office building"),
    **dict.fromkeys(["Q11315", "Q213441", "Q11707", "Q205495", "Q1426795", "Q97495053"], "shop or restaurant"),
    **dict.fromkeys(["Q134447", "Q15911738", "Q2298412"], "power station"), **dict.fromkeys(["Q12366139"], "fish hatchery"),
}


def _words(x):
    return set(re.findall(r"[a-z0-9]{3,}", (x or "").lower())) - {"the", "and", "former", "historic", "old"}


def _owners(items, wd):
    """{item: spot id} for items several spots carry: the spot whose name matches the item's label best keeps the fame,
    then the one nearest the item's own point (the airport's item stays with the airport, not its control tower)."""
    by = defaultdict(list)
    for sid, lat, lon, name, q in items:
        w = wd.get(q) or {}
        if q and lat is not None and "cl" in w:
            lw, nw = _words(w.get("lab")), _words(name)
            match = len(lw & nw) / max(1, len(lw | nw))
            by[q].append((-round(match, 2), km(lat, lon, *w["c"]) if w.get("c") else 0, sid))
    return {q: min(v)[2] for q, v in by.items() if len(v) > 1}


def _borrowed(sid, kind, lat, lon, w, owner):
    """Why this spot's Wikidata fame is another item's, or None."""
    if not w or "cl" not in w:
        return None
    if kind in MADE_KINDS and not sid.startswith("seed-r"):
        if not w.get("c"):
            if kind != "lookout":   # lookouts without a point were all real towers with their own item
                return "Wikidata item has no location (a model, animal, person or organisation)"
        elif (d := km(lat, lon, *w["c"])) > FAR_KM:
            return f"Wikidata item is {d:.0f} km away"
    bad = [NOT_A_VIEW[c] for c in w["cl"] if c in NOT_A_VIEW and (NOT_A_VIEW[c] != "organisation" or kind in MADE_KINDS - {"lookout"})]   # parks and lookouts are often filed as organisations
    if bad:
        return f"Wikidata item is a{'n' if bad[0][0] in 'aeiou' else ''} {bad[0]}"
    if owner and owner != sid:
        return "Wikidata item belongs to another spot"
    return None


RIDE_KM = 0.6   # a tower this close to an operating amusement park's point is one of its rides (Elitch Gardens' led Denver sunsets, Nov 23)


def _parks():
    """Points of US amusement and theme parks still open (Wikidata: no dissolved date), for _rides."""
    sparql = ("SELECT DISTINCT ?c WHERE { VALUES ?k { wd:Q194195 wd:Q2416723 wd:Q60990 } ?p wdt:P31 ?k ; wdt:P17 wd:Q30 ; wdt:P625 ?c . "
              "FILTER NOT EXISTS { ?p wdt:P576 ?x } }")
    try:
        j = http("https://query.wikidata.org/sparql", method="POST", data={"query": sparql, "format": "json"},
                 headers={"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots)", "Accept": "application/sparql-results+json"}, timeout=120).json()
    except Exception as e:
        soft_fail("seed theme parks", e); return []
    out = []
    for b in j["results"]["bindings"]:
        m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", b["c"]["value"])
        if m: out.append((float(m.group(2)), float(m.group(1))))
    return out


def _rides(spots, parks):
    """Ids of lookouts that are amusement-park rides."""
    return {s["id"] for s in spots if s.get("kind") == "lookout" and any(km(s["lat"], s["lon"], a, b) < RIDE_KM for a, b in parks)}


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

    owners = _owners([(f"seed-{e['type'][0]}{e['id']}", e.get("lat", (e.get("center") or {}).get("lat")), e.get("lon", (e.get("center") or {}).get("lon")),
                       e.get("tags", {}).get("name"), e.get("tags", {}).get("wikidata")) for e in els], wd)
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
        sid = f"seed-{e['type'][0]}{e['id']}"
        why = _borrowed(sid, kind, lat, lon, wd.get(t.get("wikidata")), owners.get(t.get("wikidata")))
        score = _score(kind, base, t, None if why else wd.get(t.get("wikidata"), {}))
        extra = {"wdx": t.get("wikidata"), "nofame": why} if why else {}
        out.append({**extra, "id": sid, "name": name, "lat": round(lat, 5), "lon": round(lon, 5), "cats": cats, "light": light, "effort": effort,
                    "tip": _tip(kind, t, tip), "kind": kind, "score": round(score, 1), "osm": f"{e['type']}/{e['id']}", "wd": None if why else t.get("wikidata"), "state": state})
    rides = _rides(out, _parks())
    out = [s for s in out if s["id"] not in rides]
    out = _hotspots(state, out, dup)
    _shore_pins(out)
    tiles = defaultdict(list)
    for s in out:
        tiles[f"{math.floor(s['lat'])}_{math.floor(s['lon'])}"].append(s)
    return tiles


def _shore_pins(out):
    """Lake pins come from the middle of the water. Use a viewpoint/beach/park on the same lake when OSM or eBird has one."""
    shore = [s for s in out if s["kind"] in ("viewpoint", "beach", "hotspot", "lighthouse", "refuge")]
    for s in out:
        if s["kind"] != "lake":
            continue
        word = next((w for w in re.findall(r"[A-Za-z']{3,}", s["name"]) if w.lower() not in ("lake", "the", "reservoir", "pond")), "").lower()
        best = min((x for x in shore if word and word in x["name"].lower() and km(s["lat"], s["lon"], x["lat"], x["lon"]) < 6),
                   key=lambda x: km(s["lat"], s["lon"], x["lat"], x["lon"]), default=None)
        if best:
            s["lat"], s["lon"] = best["lat"], best["lon"]
            s["tip"] += f" Pin moved to {best['name']} on the shore."
        else:
            s["tip"] += " The pin marks the middle of the lake: pick a shore spot facing the light."


_KNOWN = None
def _near_known(lat, lon, name):
    """A hotspot sub-unit of a place we already have ("Ridgefield NWR: Carty Unit" next to Ridgefield NWR)."""
    global _KNOWN
    if _KNOWN is None:
        _KNOWN = [(s["lat"], s["lon"], s["name"].lower()) for s in spots()]
    w = next((x for x in re.findall(r"[A-Za-z']{4,}", name) if x.lower() not in ("park", "lake", "river", "creek", "wildlife", "area", "national", "refuge", "trail", "regional", "county", "state")), "").lower()
    return bool(w) and any(km(lat, lon, a, b) < 4 and w in n for a, b, n in _KNOWN)


def _hotspots(state, out, dup):
    """eBird hotspots with a real species list. Next to an OSM refuge: enrich it. Otherwise: a new birding spot."""
    key = secret("EBIRD_KEY")
    if not key:
        return out
    try:
        hs = http(f"https://api.ebird.org/v2/ref/hotspot/US-{state}", params={"fmt": "json"}, headers={"X-eBirdApiToken": key}, timeout=120).json()
    except Exception as e:
        log.warning("%s eBird hotspots: %s", state, e); return out
    refs = [s for s in out if s["kind"] == "refuge"]
    added = 0
    for h in hs:
        n = h.get("numSpeciesAllTime") or 0
        if n < 110:
            continue
        lat, lon, name = h["lat"], h["lng"], h["locName"]
        near = next((s for s in refs if km(lat, lon, s["lat"], s["lon"]) < 0.6), None)
        if near:
            near["ebird"] = h["locId"]; near["species"] = max(n, near.get("species", 0)); near["score"] = round(near["score"] + 2 * math.log2(n / 50), 1); continue
        base = re.split(r"--|:|\(", name)[0].strip()
        if dup(lat, lon, base) or _near_known(lat, lon, base):
            continue
        name = re.sub(r"\s*\(.*?\)\s*$", "", name).replace("--", ": ")
        out.append({"id": f"seed-e{h['locId']}", "name": name, "lat": round(lat, 5), "lon": round(lon, 5), "cats": ["wildlife", "birds"], "light": "sunrise", "effort": "short",
                    "tip": f"eBird birding hotspot with {n} species recorded. Birds are most active in the first two hours after sunrise; recent sightings at ebird.org/hotspot/{h['locId']}.",
                    "kind": "hotspot", "score": round(2 + 3 * math.log2(n / 50), 1), "ebird": h["locId"], "species": n, "state": state})
        added += 1
    log.info("%s: %d eBird hotspots added, %d refuges enriched", state, added, sum(1 for s in refs if s.get("ebird")))
    return out


def _cap(lst):
    """Best PER_TILE by score, but each kind keeps its top KIND_FLOOR first."""
    lst = sorted(lst, key=lambda x: -x["score"]); keep, per = [], defaultdict(int)
    for x in lst:
        if per[x["kind"]] < KIND_FLOOR:
            keep.append(x); per[x["kind"]] += 1
    ids = {id(x) for x in keep}
    for x in lst:
        if len(keep) >= PER_TILE:
            break
        if id(x) in ids or (x["kind"] == "hotspot" and per["hotspot"] >= 35):   # birding hotspots: at most 35 per tile
            continue
        keep.append(x); per[x["kind"]] += 1
    return sorted(keep, key=lambda x: -x["score"])


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
        for k in [k for st2, k in FAILED if st2 == st and k not in tiles]:
            tiles[k] = []    # failed squares with nothing new still keep their old spots
        for k, lst in tiles.items():
            p = sdir / f"{k}.json"
            old = read_json(p, {"spots": []})["spots"]
            prev = [x for x in old if x.get("state") != st]
            if (st, k) in FAILED:   # this square's query failed: keep what we had for it, add what's new
                ids = {x["id"] for x in lst}; prev += [x for x in old if x.get("state") == st and x["id"] not in ids]
            allx = _cap(prev + lst)
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


def _osm_tags(refs):
    """{"node/123": tags} from the OSM API, 100 at a time per element type."""
    out, by = {}, defaultdict(list)
    for r in refs:
        typ, _, i = (r or "").partition("/")
        if typ in ("node", "way", "relation") and i.isdigit(): by[typ].append(i)
    for typ, ids in by.items():
        for k in range(0, len(ids), 100):
            try:
                j = http(f"https://api.openstreetmap.org/api/0.6/{typ}s.json", params={typ + "s": ",".join(ids[k:k + 100])},
                         headers={"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots)"}, timeout=90).json()
                for e in j.get("elements", []): out[f"{typ}/{e['id']}"] = e.get("tags", {})
            except Exception as e:
                soft_fail("seedclean osm tags", e)   # those spots fall back to subtracting the Wikidata terms
            time.sleep(1)
    return out


def clean():
    """Apply the current rules to the starter spots already in feed/seed, in place, keeping what later jobs added
    (terrain horizons, facing): lookouts that are control towers or amusement-park rides go; fame borrowed from another Wikidata item goes
    (score recomputed from the OSM tags, Wikipedia views dropped). Run monthly by the scheduler, so newly seeded
    states get it too; a full re-seed applies the same rules in build(). Report: data/seedclean.json."""
    sdir = FEED / "seed"
    tiles = {f: read_json(f, {"spots": []}) for f in sorted(sdir.glob("*_*.json"))}
    allsp = [s for j in tiles.values() for s in j.get("spots", [])]
    wd = wikidata([s.get("wd") for s in allsp])
    owners = _owners([(s["id"], s["lat"], s["lon"], s["name"], s.get("wd")) for s in allsp], wd)
    hit = {}
    for s in allsp:
        if s.get("wd"):
            why = _borrowed(s["id"], s.get("kind"), s["lat"], s["lon"], wd.get(s["wd"]), owners.get(s["wd"]))
            if why: hit[s["id"]] = why
    rides = _rides(allsp, _parks())
    tags = _osm_tags([s.get("osm") for s in allsp if s["id"] in hit])
    base = {x[0]: x[5] for x in TYPES}
    rep, dropped = [], []
    for f, j in tiles.items():
        keep, dirty = [], False
        for s in j.get("spots", []):
            if s.get("kind") == "lookout" and (NOT_LOOKOUT.search(s.get("name", "")) or s["id"] in rides):
                dropped.append({"id": s["id"], "name": s["name"], "state": s.get("state"), "score": s.get("score")}); dirty = True; continue
            if s["id"] in hit:
                t, w, old = tags.get(s.get("osm")), wd.get(s["wd"]) or {}, s["score"]
                if t is not None and s.get("kind") in base:
                    s["score"] = round(_score(s["kind"], base[s["kind"]], t, None), 1)
                else:   # no tags: take the Wikidata terms off (the +2 for a Wikipedia tag assumed, as almost all of them have one)
                    s["score"] = round(old - 3 * math.log2(1 + w.get("n", 0)) - (2 if w.get("img") else 0) - 2, 1)
                s["wdx"], s["wd"], s["nofame"] = s["wd"], None, hit[s["id"]]; dirty = True
                rep.append({"id": s["id"], "name": s["name"], "kind": s.get("kind"), "state": s.get("state"), "score": old, "now": s["score"], "why": hit[s["id"]]})
            keep.append(s)
        if dirty:
            keep.sort(key=lambda x: -x["score"])
            j["spots"] = keep; f.write_text(json.dumps(j, separators=(",", ":")))
    gone = set(hit) | {d["id"] for d in dropped}
    vdir = FEED / "seedviews"
    for f in vdir.glob("*_*.json"):   # Wikipedia views belong to the item, so they go with it
        v = read_json(f, {}) or {}
        if gone & set(v):
            f.write_text(json.dumps({k: x for k, x in v.items() if k not in gone}, separators=(",", ":")))
    idx = read_json(sdir / "index.json", {"tiles": {}})
    for f, j in tiles.items():
        if f.stem in idx.get("tiles", {}): idx["tiles"][f.stem] = len(j.get("spots", []))
    (sdir / "index.json").write_text(json.dumps(idx, separators=(",", ":")))
    why = defaultdict(int)
    for r in rep: why[re.sub(r"\d+ km", "N km", r["why"])] += 1
    DATA.mkdir(exist_ok=True); (DATA / "seedclean.json").write_text(json.dumps({"at": iso(utcnow()), "spots": len(allsp), "with_wikidata": sum(1 for s in allsp if s.get("wd")),
                                          "fame_removed": len(rep), "by_reason": dict(why), "dropped_lookouts": dropped, "rides": len(rides),
                                          "fame_removed_top": sorted(rep, key=lambda r: -(r["score"] - r["now"]))[:300]}, indent=0))
    return f"{len(allsp)} spots: Wikidata fame removed from {len(rep)} ({', '.join(f'{k}: {v}' for k, v in why.items())}); {len(dropped)} control towers and park rides dropped"


def candidates(lat, lon, radius_km, limit=15):
    """Top seed spots near a research target, for reach mode (promote the best, verify cheaply)."""
    sdir = FEED / "seed"
    out = []
    for la in range(math.floor(lat - 1), math.floor(lat + 1) + 1):
        for lo in range(math.floor(lon - 1.5), math.floor(lon + 1.5) + 1):
            for s in read_json(sdir / f"{la}_{lo}.json", {"spots": []})["spots"]:
                if km(lat, lon, s["lat"], s["lon"]) <= radius_km:
                    out.append({k: s.get(k) for k in ("id", "name", "lat", "lon", "kind", "score", "osm", "wd")})
    return sorted(out, key=lambda x: -x["score"])[:limit]
