"""Opening hours from OpenStreetMap, so the app stops sending people to gardens that close before sunset.

Researched spots: a named OSM feature with opening_hours within 250 m whose name shares a real word with the spot.
Starter spots: their own OSM element (seed 'osm' field), looked up in one query per tile.
Output: feed/hours.json {spot id: opening_hours} and feed/seedhours/<tile>.json (separate from the seed tiles, so no
clash with a rebuild). Re-checked every 30 days.
"""
import json, re, time
from .common import FEED, http, log, read_json, write_json, spots, utcnow, iso
from .seed import OVERPASS

STOP = {"park", "state", "the", "trail", "trailhead", "viewpoint", "falls", "lake", "garden", "gardens", "national", "regional", "area", "and", "of", "at", "point", "mount", "mt"}


def _op(q, timeout=180):
    for u in OVERPASS * 2:
        try:
            j = http(u, method="POST", data={"data": q}, timeout=timeout, tries=1).json()
            if "runtime error" in (j.get("remark") or ""):
                raise RuntimeError(j["remark"][:120])
            return j["elements"]
        except Exception as e:
            log.warning("overpass hours %s: %s", u, e); time.sleep(8)
    raise RuntimeError("Overpass unavailable")


def _words(s):
    return {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in STOP}


def curated():
    out = {}
    sp = spots()
    for i in range(0, len(sp), 25):
        ch = sp[i:i + 25]
        # only the place itself: parks, gardens, reserves, attractions - not the shop, cafe, library or visitor centre next door
        q = "[out:json][timeout:150];(" + "".join(f'nwr(around:250,{s["lat"]},{s["lon"]})[opening_hours][name][~"^(leisure|tourism)$"~"^(park|garden|nature_reserve|attraction|zoo|theme_park|viewpoint)$"];' for s in ch) + ");out tags center;"
        try:
            els = _op(q)
        except Exception as e:
            log.warning("hours batch %d: %s", i, e); continue
        for s in ch:
            w = _words(s["name"])
            best = None
            for e in els:
                c = e.get("center") or e
                if "lat" not in c or abs(c["lat"] - s["lat"]) > 0.004 or abs(c["lon"] - s["lon"]) > 0.006:
                    continue
                ew = _words(e["tags"].get("name", "")); shared = w & ew
                if not shared or len(shared) / max(1, len(w | ew)) < 0.5:
                    continue
                if best is None or len(shared) > best[0]:
                    best = (len(shared), e["tags"]["opening_hours"], e["tags"]["name"])
            if best:
                out[s["id"]] = {"oh": best[1], "from": best[2]}
        time.sleep(2)
    for k, v in (read_json(__import__("pathlib").Path(__file__).resolve().parents[1] / "config" / "hours_overrides.json", {}) or {}).items():
        out[k] = {"oh": v["oh"], "from": v.get("from", "checked by hand")}   # gated places OSM doesn't have (or has wrong)
    write_json("hours.json", {"gen": iso(utcnow()), "spots": out})
    return f"{len(out)} researched spots have opening hours"


def seed(budget_min=200):
    sd, od = FEED / "seed", FEED / "seedhours"; od.mkdir(exist_ok=True)
    t0, tiles, found = time.time(), 0, 0
    cutoff = iso(utcnow())[:10]
    for f in sorted(sd.glob("*_*.json")):
        if time.time() - t0 > budget_min * 60:
            open(".more", "w").write("1")   # out of time with tiles left: the workflow queues another run
            break
        o = od / f.name; old = read_json(o, {}) or {}
        if old.get("_at") and (utcnow() - __import__("datetime").datetime.fromisoformat(old["_at"] + "T00:00:00+00:00")).days < 30:
            continue
        sp = [s for s in json.loads(f.read_text()).get("spots", []) if s.get("osm")]
        ids = {"node": [], "way": [], "relation": []}
        for s in sp:
            t, n = s["osm"].split("/"); ids.setdefault(t, []).append(n)
        q = "[out:json][timeout:120];(" + "".join(f'{t}(id:{",".join(v)});' for t, v in ids.items() if v) + ");out tags;"
        out = {"_at": cutoff}
        if sp:
            try:
                els = _op(q)
            except Exception as e:
                log.warning("seed hours %s: %s", f.stem, e); continue
            byosm = {f'{e["type"]}/{e["id"]}': e.get("tags", {}) for e in els}
            for s in sp:
                oh = byosm.get(s["osm"], {}).get("opening_hours")
                if oh:
                    out[s["id"]] = oh; found += 1
        write_json(o, out); tiles += 1
        time.sleep(1)
    return f"{tiles} tiles checked, {found} starter spots with opening hours"


def run():
    a = curated()
    return a + "; " + seed()
