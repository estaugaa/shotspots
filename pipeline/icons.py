"""Famous US landscape places that the OpenStreetMap starter data misses or doesn't link (Smith Rock, Clingmans Dome,
Otter Cliff ...). Wikidata: items in the US of landscape classes (subclasses included), with coordinates, an English
article and >= 6 language editions; English Wikipedia views over 12 months; keep >= 30k/yr. Items already present as
a starter spot (same Wikidata id, or a starter spot within 600 m sharing a name word) are skipped: the views job
covers those. Output feed/icons.json {gen, spots:[{id,name,lat,lon,kind,cats,views,wd,state}]}; the app adds them as
starter spots. Monthly."""
import json, re, time, glob, datetime as dt, urllib.parse
from .common import FEED, log, utcnow, iso, write_json, read_json
from .wikiviews import S, _get, _views

CLASSES = {  # English class label on Wikidata -> starter kind (ids are looked up by label at run time and logged)
    "waterfall": "waterfall", "mountain": "peak", "beach": "beach", "lighthouse": "lighthouse", "canyon": "canyon", "cliff": "cliff",
    "mountain pass": "pass", "scenic viewpoint": "viewpoint", "natural arch": "arch", "rock formation": "rock", "butte": "butte",
    "mesa": "mesa", "glacier": "glacier", "sea stack": "rock", "hoodoo": "rock", "geyser": "rock", "hot spring": "rock",
}
CATS = {"waterfall": ["waterfall"], "peak": ["mountain", "vista"], "beach": ["coast"], "lighthouse": ["coast", "historic"], "canyon": ["geology", "vista"],
        "cliff": ["geology", "vista"], "pass": ["mountain", "vista"], "viewpoint": ["vista"], "trail": ["vista"], "glacier": ["mountain"], "butte": ["geology", "vista"],
        "mesa": ["geology", "vista"], "park": ["vista"], "arch": ["geology"], "rock": ["geology", "vista"], "lake": ["water", "reflection"], "range": ["mountain", "vista"]}
KIND = {"canyon": "viewpoint", "cliff": "viewpoint", "trail": "viewpoint", "glacier": "viewpoint", "butte": "viewpoint", "mesa": "viewpoint", "park": "viewpoint", "rock": "viewpoint", "range": "peak"}
Q_DIRECT = """SELECT ?item ?title ?coord ?sl WHERE {{
  ?item wdt:P31 wd:{cls} ; wdt:P17 wd:Q30 ; wdt:P625 ?coord ; wikibase:sitelinks ?sl .
  FILTER(?sl >= 8)
  ?art schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
}}"""
Q = """SELECT ?item ?title ?coord ?sl WHERE {{
  ?item wdt:P31/wdt:P279* wd:{cls} ; wdt:P17 wd:Q30 ; wdt:P625 ?coord ; wikibase:sitelinks ?sl .
  FILTER(?sl >= 6)
  ?art schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
}}"""


def _sparql(q):
    for i in range(3):
        try:
            r = S.get("https://query.wikidata.org/sparql", params={"query": q, "format": "json"}, timeout=180)
            if r.status_code == 200: return r.json()["results"]["bindings"]
            time.sleep(20 * (i + 1))
        except Exception:
            time.sleep(20 * (i + 1))
    return []


# Curated: classic US photo locations (names resolved to Wikidata coordinates; unresolved names are logged, not guessed)
NAMES = [("Smith Rock State Park", "viewpoint"), ("Clingmans Dome", "viewpoint"), ("Otter Cliff", "viewpoint"), ("Anhinga Trail", "viewpoint"),
 ("Sand Beach (Maine)", "beach"), ("Jordan Pond", "lake"), ("Bass Harbor Head Light", "lighthouse"), ("Thunder Hole", "viewpoint"),
 ("Morton Overlook", "viewpoint"), ("Cades Cove", "viewpoint"), ("Roaring Fork Motor Nature Trail", "viewpoint"), ("Linn Cove Viaduct", "bridge"), ("Grandfather Mountain", "viewpoint"),
 ("Horseshoe Bend (Arizona)", "viewpoint"), ("Antelope Canyon", "viewpoint"), ("Monument Valley", "viewpoint"), ("Toroweap Overlook", "viewpoint"), ("Hopi Point", "viewpoint"),
 ("Delicate Arch", "arch"), ("Landscape Arch", "arch"), ("Turret Arch", "arch"), ("Dead Horse Point State Park", "viewpoint"), ("Grand View Point Overlook", "viewpoint"),
 ("Sunset Point (Bryce Canyon)", "viewpoint"), ("Inspiration Point (Bryce Canyon)", "viewpoint"), ("Angels Landing", "viewpoint"), ("The Watchman", "viewpoint"), ("Canyon Overlook Trail", "viewpoint"),
 ("Goblin Valley State Park", "viewpoint"), ("Valley of Fire State Park", "viewpoint"), ("Zabriskie Point", "viewpoint"), ("Badwater Basin", "viewpoint"), ("Mesquite Flat Sand Dunes", "viewpoint"), ("Racetrack Playa", "viewpoint"),
 ("Glacier Point", "viewpoint"), ("Tunnel View", "viewpoint"), ("Mono Lake", "lake"), ("Alabama Hills", "viewpoint"), ("Bixby Creek Bridge", "bridge"), ("McWay Falls", "waterfall"),
 ("Point Reyes Lighthouse", "lighthouse"), ("Pigeon Point Light Station", "lighthouse"), ("Moro Rock", "viewpoint"), ("Joshua Tree National Park", "viewpoint"), ("Keys View", "viewpoint"),
 ("Ruby Beach", "beach"), ("Rialto Beach", "beach"), ("Hurricane Ridge", "viewpoint"), ("Palouse Falls", "waterfall"), ("Steptoe Butte", "viewpoint"), ("Diablo Lake", "lake"),
 ("Reflection Lakes", "lake"), ("Sunrise (Mount Rainier)", "viewpoint"), ("Crater Lake", "lake"), ("Thor's Well", "viewpoint"), ("Heceta Head Light", "lighthouse"), ("Proxy Falls", "waterfall"),
 ("Trillium Lake", "lake"), ("Painted Hills", "viewpoint"), ("Shoshone Falls", "waterfall"), ("Mesa Falls", "waterfall"),
 ("Oxbow Bend", "viewpoint"), ("Schwabacher Landing", "viewpoint"), ("Mormon Row Historic District", "viewpoint"), ("Snake River Overlook", "viewpoint"), ("Grand Prismatic Spring", "viewpoint"),
 ("Lower Falls (Yellowstone River)", "waterfall"), ("Artist Point (Yellowstone)", "viewpoint"), ("Lamar Valley", "viewpoint"), ("Maroon Bells", "viewpoint"), ("Dream Lake (Colorado)", "lake"),
 ("Garden of the Gods", "viewpoint"), ("Great Sand Dunes National Park and Preserve", "viewpoint"), ("White Sands National Park", "viewpoint"), ("Shiprock", "viewpoint"),
 ("Devils Tower", "viewpoint"), ("Needles Highway", "viewpoint"), ("Badlands Loop Road", "viewpoint"), ("Big Bend National Park", "viewpoint"),
 ("Cathedral Rock (Arizona)", "viewpoint"), ("Bell Rock", "viewpoint"), ("Havasu Falls", "waterfall"), ("Hanging Lake", "lake"),
 ("Niagara Falls", "waterfall"), ("Watkins Glen State Park", "waterfall"), ("Portland Head Light", "lighthouse"), ("Pemaquid Point Light", "lighthouse"), ("Mount Washington (New Hampshire)", "viewpoint"),
 ("Kancamagus Highway", "viewpoint"), ("Ricketts Glen State Park", "waterfall"), ("Bridal Veil Falls (Utah)", "waterfall"), ("Mesa Arch", "arch"), ("Pictured Rocks National Lakeshore", "viewpoint"),
 ("Split Rock Lighthouse", "lighthouse"), ("Cape Hatteras Light", "lighthouse"), ("Bodie Island Light", "lighthouse"), ("Jennette's Pier", "viewpoint"), ("Sunset Cliffs", "viewpoint"),
 ("La Jolla Cove", "beach"), ("Ellen Browning Scripps Memorial Pier", "viewpoint"), ("Torrey Pines State Natural Reserve", "viewpoint"), ("Laguna Beach, California", "beach")]
KCATS = {"viewpoint": ["vista"], "beach": ["coast"], "lake": ["water", "reflection"], "lighthouse": ["coast", "historic"], "arch": ["geology", "vista"], "waterfall": ["waterfall"], "bridge": ["historic", "vista"]}


def _resolve(name):
    """Wikipedia title -> Wikidata id + coordinates (via the article, so the right item is used)."""
    j = _get("https://en.wikipedia.org/w/api.php", {"action": "query", "titles": name, "redirects": 1, "prop": "coordinates|pageprops", "ppprop": "wikibase_item", "format": "json"}) or {}
    for p in (j.get("query", {}).get("pages") or {}).values():
        co = (p.get("coordinates") or [None])[0]; q = (p.get("pageprops") or {}).get("wikibase_item")
        if co and q: return {"wd": q, "title": p["title"], "lat": round(co["lat"], 5), "lon": round(co["lon"], 5)}
    return None


def run():
    have_q, near = set(), {}
    for f in glob.glob(str(FEED / "seed" / "*_*.json")):
        for x in (read_json(f, {}) or {}).get("spots", []):
            if x.get("wd"): have_q.add(x["wd"])
            near.setdefault((round(x["lat"], 1), round(x["lon"], 1)), []).append(x)
    def covered(c):
        words = {w for w in re.findall(r"[a-z]{4,}", c["title"].lower()) if w not in {"mount", "state", "park", "national", "falls", "lake", "beach", "lighthouse", "light", "point", "trail", "overlook"}}
        for dlat in (-0.1, 0, 0.1):
            for dlon in (-0.1, 0, 0.1):
                for x in near.get((round(c["lat"] + dlat, 1), round(c["lon"] + dlon, 1)), []):
                    if abs(x["lat"] - c["lat"]) < 0.006 and abs(x["lon"] - c["lon"]) < 0.008 and words & set(re.findall(r"[a-z]{4,}", x["name"].lower())):
                        return x["name"]
        return None
    today = dt.date.today().replace(day=1); end = today - dt.timedelta(days=1); start = (end.replace(day=1) - dt.timedelta(days=330)).replace(day=1)
    out, unresolved, cov = [], [], []
    for name, kind in NAMES:
        c = _resolve(name); time.sleep(0.2)
        if not c: unresolved.append(name); continue
        if c["wd"] in have_q: cov.append(f"{name} (same id)"); continue
        hit = covered(c)
        if hit: cov.append(f"{name} ~ {hit}"); continue
        v = _views(c["title"], start.strftime("%Y%m%d00"), end.strftime("%Y%m%d00")); time.sleep(0.12)
        out.append({"id": f"icon-{c['wd']}", "name": c["title"], "lat": c["lat"], "lon": c["lon"], "kind": kind, "cats": KCATS.get(kind, ["vista"]), "views": v, "wd": c["wd"],
                    "light": "both", "effort": "short", "tip": f"A classic photo location (about {round(v / 1000)}k Wikipedia views a year). The pin is the mapped centre; check where the classic view is."})
    log.info(f"icons unresolved: {unresolved}"); log.info(f"icons already covered: {cov}")
    write_json("icons.json", {"gen": iso(utcnow()), "unresolved": unresolved, "covered": len(cov), "spots": sorted(out, key=lambda x: -x["views"])})
    return f"{len(NAMES)} curated: {len(cov)} already in the data, {len(out)} added, {len(unresolved)} unresolved"
