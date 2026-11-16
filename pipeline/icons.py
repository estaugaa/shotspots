"""Famous US landscape places that the OpenStreetMap starter data misses or doesn't link (Smith Rock, Clingmans Dome,
Otter Cliff ...). Wikidata: items in the US of landscape classes (subclasses included), with coordinates, an English
article and >= 6 language editions; English Wikipedia views over 12 months; keep >= 30k/yr. Items already present as
a starter spot (same Wikidata id, or a starter spot within 600 m sharing a name word) are skipped: the views job
covers those. Output feed/icons.json {gen, spots:[{id,name,lat,lon,kind,cats,views,wd,state}]}; the app adds them as
starter spots. Monthly."""
import json, re, time, glob, datetime as dt, urllib.parse
from .common import FEED, log, utcnow, iso, write_json, read_json
from .wikiviews import S, _get, _views

CLASSES = {  # Wikidata class -> starter kind
    "Q34038": "waterfall", "Q8502": "peak", "Q40080": "beach", "Q39715": "lighthouse", "Q150784": "canyon", "Q107679": "cliff",
    "Q133056": "pass", "Q6017969": "viewpoint", "Q2143825": "trail", "Q35666": "glacier", "Q41575": "butte", "Q207524": "mesa",
    "Q1365179": "park", "Q19817101": "arch", "Q2465017": "rock"
}
CATS = {"waterfall": ["waterfall"], "peak": ["mountain", "vista"], "beach": ["coast"], "lighthouse": ["coast", "historic"], "canyon": ["geology", "vista"],
        "cliff": ["geology", "vista"], "pass": ["mountain", "vista"], "viewpoint": ["vista"], "trail": ["vista"], "glacier": ["mountain"], "butte": ["geology", "vista"],
        "mesa": ["geology", "vista"], "park": ["vista"], "arch": ["geology"], "rock": ["geology", "vista"], "lake": ["water", "reflection"], "range": ["mountain", "vista"]}
KIND = {"canyon": "viewpoint", "cliff": "viewpoint", "trail": "viewpoint", "glacier": "viewpoint", "butte": "viewpoint", "mesa": "viewpoint", "park": "viewpoint", "rock": "viewpoint", "range": "peak"}
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


def run():
    have_q, near = set(), {}
    for f in glob.glob(str(FEED / "seed" / "*_*.json")):
        for s in (read_json(f, {}) or {}).get("spots", []):
            if s.get("wd"): have_q.add(s["wd"])
            near.setdefault((round(s["lat"], 1), round(s["lon"], 1)), []).append(s)
    cand = {}
    for cls, kind in CLASSES.items():
        rows = _sparql(Q.format(cls=cls)); log.info(f"icons {cls} {kind}: {len(rows)}")
        for b in rows:
            q = b["item"]["value"].rsplit("/", 1)[1]
            m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
            if not m or q in have_q or q in cand: continue
            lon, lat = float(m.group(1)), float(m.group(2))
            if not (18 < lat < 72 and -180 < lon < -60): continue
            cand[q] = {"wd": q, "name": b["title"]["value"], "lat": round(lat, 5), "lon": round(lon, 5), "kind0": kind, "sl": int(b["sl"]["value"])}
        time.sleep(2)
    # drop ones a starter spot already covers under another id (within 600 m, sharing a name word)
    def covered(c):
        words = {w for w in re.findall(r"[a-z]{4,}", c["name"].lower()) if w not in {"mount", "state", "park", "national", "falls", "lake", "beach", "lighthouse"}}
        for dlat in (-0.1, 0, 0.1):
            for dlon in (-0.1, 0, 0.1):
                for s in near.get((round(c["lat"] + dlat, 1), round(c["lon"] + dlon, 1)), []):
                    if abs(s["lat"] - c["lat"]) < 0.0055 and abs(s["lon"] - c["lon"]) < 0.0075 and (words & set(re.findall(r"[a-z]{4,}", s["name"].lower())) or not words):
                        return True
        return False
    cand = {q: c for q, c in cand.items() if not covered(c)}
    today = dt.date.today().replace(day=1); end = today - dt.timedelta(days=1); start = (end.replace(day=1) - dt.timedelta(days=330)).replace(day=1)
    out = []
    for c in sorted(cand.values(), key=lambda c: -c["sl"]):
        v = _views(c["name"], start.strftime("%Y%m%d00"), end.strftime("%Y%m%d00")); time.sleep(0.12)
        if v < 30000: continue
        k = c["kind0"]
        out.append({"id": f"icon-{c['wd']}", "name": c["name"], "lat": c["lat"], "lon": c["lon"], "kind": KIND.get(k, k), "cats": CATS.get(k, ["vista"]), "views": v, "wd": c["wd"],
                    "light": "both", "effort": "short", "tip": f"A well-known {k.replace('rock', 'rock formation')} (about {round(v / 1000)}k Wikipedia views a year). The pin is the mapped centre: check where the classic view is."})
    write_json("icons.json", {"gen": iso(utcnow()), "spots": sorted(out, key=lambda x: -x["views"])})
    return f"{len(cand)} uncovered candidates, {len(out)} with >=30k views/yr added"
