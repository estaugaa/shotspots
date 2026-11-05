"""Nightly spot research: requests, an expanding frontier, saturation, limits, validation and export.

How it fits together
  * The app submits two Netlify forms: "research" (a place + radius you want researched) and
    "research_settings" (nightly limits). sync() copies them into data/research/.
  * Each night a scheduled Claude task runs `python -m pipeline research_plan`, researches the targets it
    prints (web + map search, the same way the Gorge spots were built), writes candidate spots to a JSON file
    and runs `python -m pipeline research_add <file>`. That validates, de-duplicates, stores the spots and
    records how many were new.
  * The world is split into 0.25-degree cells (~25 km). A cell is SATURATED after two research runs that
    each add fewer than `saturation_min_new` spots. The frontier then moves to the nearest unsaturated cell,
    preferring cells next to saturated ones, within `max_km_from_home` (requests ignore that cap).
"""
import json, math, re, sys, datetime as dt
from pathlib import Path
from .common import DATA, CONFIG, FEED, spots, write_json, read_json, km, utcnow, iso, log, secret, http

R = DATA / "research"
R.mkdir(parents=True, exist_ok=True)
(R / "spots").mkdir(exist_ok=True)
CELL = 0.25
HOME = (45.582, -122.353)
DEFAULTS = {"enabled": True, "regions_per_night": 1, "max_new_spots_per_night": 8, "max_web_searches_per_night": 40,
            "max_minutes_per_night": 45, "auto_expand": True, "max_km_from_home": 250, "saturation_min_new": 2,
            "categories": ["vista", "waterfall", "mountain", "reflection", "wildlife", "birds", "night", "fallcolor", "wildflowers", "coast", "geology", "city", "historic"]}
CATS = set(DEFAULTS["categories"]) | {"garden", "aurora", "alignment"}


def cell_of(lat, lon):
    return f"{math.floor(lat / CELL) * CELL:.2f}_{math.floor(lon / CELL) * CELL:.2f}"


def cell_center(c):
    a, b = map(float, c.split("_"))
    return a + CELL / 2, b + CELL / 2


def load(name, default):
    return read_json(R / name, default)


def save(name, obj):
    json.dump(obj, open(R / name, "w"), indent=1)


def settings():
    s = dict(DEFAULTS)
    s.update(read_json(CONFIG / "research.json", {}))
    s.update(load("settings_from_app.json", {}))
    return s


# ---------------- sync from the app (Netlify Forms) ----------------
def sync():
    tok, site = secret("NETLIFY_TOKEN"), secret("NETLIFY_SITE_ID")
    if not tok or not site:
        return "no Netlify token; nothing synced"
    subs, page = [], 1
    while page <= 10:
        j = http(f"https://api.netlify.com/api/v1/sites/{site}/submissions", params={"per_page": 100, "page": page}, headers={"Authorization": f"Bearer {tok}"}).json()
        if not j:
            break
        subs += j
        page += 1
    return ingest(subs)


def ingest(subs):
    """Store research requests and the newest limits from a list of Netlify form submissions
    (from the API in sync(), or saved from the Netlify connector by the nightly task: research_import)."""
    if isinstance(subs, dict):
        subs = subs.get("submissions") or subs.get("data") or []
    req = load("requests.json", [])
    seen = {r["sub"] for r in req}
    newest_settings = None
    for s in sorted(subs, key=lambda x: x.get("created_at", "")):
        d = s.get("data", {})
        fname = s.get("form_name") or (s.get("form") or {}).get("name") if isinstance(s.get("form"), dict) else s.get("form_name")
        if fname == "research" and s["id"] not in seen:
            try:
                req.append({"sub": s["id"], "at": s.get("created_at"), "label": d.get("label") or "Requested place", "lat": float(d["lat"]), "lon": float(d["lon"]),
                            "radius_km": float(d.get("radius_km") or 25), "focus": d.get("focus") or "", "status": "queued"})
            except Exception as e:
                log.warning("bad research request %s: %s", s["id"], e)
        if fname == "research_settings":
            newest_settings = d
    save("requests.json", req)
    if newest_settings:
        out = {}
        for k, v in newest_settings.items():
            if k in ("regions_per_night", "max_new_spots_per_night", "max_web_searches_per_night", "max_minutes_per_night", "max_km_from_home", "saturation_min_new"):
                try:
                    out[k] = int(float(v))
                except Exception:
                    pass
            elif k in ("enabled", "auto_expand"):
                out[k] = str(v).lower() in ("1", "true", "on", "yes")
        save("settings_from_app.json", out)
    return f"{len(req)} requests total; settings {'updated' if newest_settings else 'unchanged'}"


# ---------------- planning ----------------
def _state():
    st = load("state.json", {"cells": {}, "runs": []})
    # seed: cells holding curated Gorge spots count as explored once (not saturated)
    for s in spots():
        c = cell_of(s["lat"], s["lon"])
        st["cells"].setdefault(c, {"status": "open", "runs": [], "spots": 0})
    for c in st["cells"].values():
        c["spots"] = 0
    for s in spots():
        st["cells"][cell_of(s["lat"], s["lon"])]["spots"] += 1
    return st


def _nearby(lat, lon, rad_km):
    return [{"id": s["id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"], "cats": s["cats"]} for s in spots() if km(lat, lon, s["lat"], s["lon"]) <= rad_km]


def plan():
    cfg = settings()
    st = _state()
    targets = []
    if not cfg["enabled"]:
        print(json.dumps({"settings": cfg, "targets": [], "note": "research paused in the app"}, indent=1))
        return
    for r in load("requests.json", []):
        if r["status"] in ("queued", "in_progress") and len(targets) < cfg["regions_per_night"]:
            targets.append({"kind": "request", "label": r["label"], "lat": r["lat"], "lon": r["lon"], "radius_km": r["radius_km"], "focus": r.get("focus"), "sub": r["sub"],
                            "known_spots": _nearby(r["lat"], r["lon"], r["radius_km"] + 5)})
    if cfg["auto_expand"] and len(targets) < cfg["regions_per_night"]:
        cells = st["cells"]
        saturated = {c for c, v in cells.items() if v["status"] == "saturated"}
        cand = set(c for c, v in cells.items() if v["status"] != "saturated")
        for c in list(saturated) + list(cells):  # neighbours of explored cells
            a, b = map(float, c.split("_"))
            for da in (-CELL, 0, CELL):
                for db in (-CELL, 0, CELL):
                    n = f"{a + da:.2f}_{b + db:.2f}"
                    if n not in saturated:
                        cand.add(n)

        def score(c):
            la, lo = cell_center(c)
            d = km(HOME[0], HOME[1], la, lo)
            if d > cfg["max_km_from_home"]:
                return None
            a, b = map(float, c.split("_"))
            adj_sat = sum(f"{a + da:.2f}_{b + db:.2f}" in saturated for da in (-CELL, 0, CELL) for db in (-CELL, 0, CELL))
            runs = len(cells.get(c, {}).get("runs", []))
            return d - 15 * adj_sat + 8 * runs  # nearer, next to finished areas, less-visited first

        ranked = sorted((s_, c) for c in cand if (s_ := score(c)) is not None)
        for _, c in ranked[: cfg["regions_per_night"] - len(targets)]:
            la, lo = cell_center(c)
            targets.append({"kind": "frontier", "cell": c, "label": f"Area around {la:.2f}, {lo:.2f}", "lat": la, "lon": lo, "radius_km": 18,
                            "runs_so_far": len(cells.get(c, {}).get("runs", [])), "known_spots": _nearby(la, lo, 20)})
    print(json.dumps({"settings": cfg, "targets": targets, "schema": SCHEMA_DOC}, indent=1))


SCHEMA_DOC = {
    "spot": {"name": "str (place name as signed/locally used)", "lat": "float (verified pin: the viewpoint, falls or parking you'd stand at)", "lon": "float",
             "region": "str (e.g. 'Banff · Bow Valley')", "cats": "list from " + ", ".join(sorted(CATS)), "months": "list of best months 1-12",
             "effort": "road | short | hike | hard", "light": "sunrise | sunset | both | overcast | night",
             "tip": "2-4 sentences: what the shot is, when, and how (specific, local, checked)", "lens": "optional: focal length advice for an X-T5 with 16-50, 27 and 70-300",
             "alert": "optional: access/permit/closure/safety", "park": "optional [lat, lon] of the trailhead/parking if different from the pin",
             "sources": "list of [title, url] you actually read; at least one", "confidence": "high | medium | low (pin accuracy and facts)"},
    "file": "{'target': <target label or cell>, 'searches_used': int, 'minutes_used': int, 'spots': [spot, ...], 'landmarks': optional [{name, lat, lon, elev}], 'notes': str}",
}


# ---------------- adding researched spots ----------------
def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48]


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", s.lower()))


def add(path):
    cfg = settings()
    sub = json.load(open(path))
    existing = spots()
    st = _state()
    added, rejected = [], []
    for sp in sub.get("spots", []):
        why = _validate(sp)
        if why:
            rejected.append({"name": sp.get("name"), "why": why})
            continue
        dup = next((e for e in existing if km(e["lat"], e["lon"], sp["lat"], sp["lon"]) < 0.25 or (_norm(e["name"]) == _norm(sp["name"]) and km(e["lat"], e["lon"], sp["lat"], sp["lon"]) < 3)), None)
        if dup:
            rejected.append({"name": sp["name"], "why": f"duplicate of {dup['id']}"})
            continue
        if len(added) >= cfg["max_new_spots_per_night"]:
            rejected.append({"name": sp["name"], "why": "nightly spot limit reached"})
            continue
        rec = {"id": "r-" + _slug(sp["name"]), "name": sp["name"], "region": sp.get("region") or "Researched", "cats": [c for c in sp["cats"] if c in CATS],
               "lat": round(float(sp["lat"]), 5), "lon": round(float(sp["lon"]), 5), "months": sorted({int(m) for m in sp.get("months") or range(1, 13)}),
               "effort": sp.get("effort", "short"), "light": sp.get("light", "both"), "tip": sp["tip"].strip(), "lens": sp.get("lens"), "alert": sp.get("alert"),
               "park": sp.get("park"), "sources": sp["sources"][:6], "confidence": sp.get("confidence", "medium"),
               "researched": utcnow().date().isoformat(), "reviewed": False}
        rec = {k: v for k, v in rec.items() if v not in (None, "", [])}
        while any(e["id"] == rec["id"] for e in existing):
            rec["id"] += "-2"
        c = cell_of(rec["lat"], rec["lon"])
        f = R / "spots" / f"{c}.json"
        lst = json.load(open(f)) if f.exists() else []
        lst.append(rec)
        json.dump(lst, open(f, "w"), indent=1)
        existing.append(rec)
        added.append(rec["id"])
    if sub.get("landmarks"):
        p = R / "landmarks.json"
        lm = json.load(open(p)) if p.exists() else []
        for l in sub["landmarks"]:
            if all(k in l for k in ("name", "lat", "lon")) and not any(km(x["lat"], x["lon"], l["lat"], l["lon"]) < 0.5 for x in lm):
                lm.append({"id": "rl-" + _slug(l["name"]), "name": l["name"], "lat": float(l["lat"]), "lon": float(l["lon"]), "elev": l.get("elev"), "kind": "peak" if l.get("elev", 0) and l["elev"] > 2500 else "landmark"})
        json.dump(lm, open(p, "w"), indent=1)
    # saturation bookkeeping for the target cell(s)
    tgt = sub.get("target", "")
    cells = {cell_of(*map(float, (s_["lat"], s_["lon"]))) for s_ in sub.get("spots", []) if _validate(s_) is None}
    if re.match(r"^-?\d+\.\d\d_-?\d+\.\d\d$", str(tgt)):
        cells.add(tgt)
    for c in cells or {tgt}:
        if not c:
            continue
        cell = st["cells"].setdefault(c, {"status": "open", "runs": [], "spots": 0})
        n_here = sum(1 for a in added if cell_of(*next((e["lat"], e["lon"]) for e in existing if e["id"] == a)) == c)
        cell["runs"].append({"date": utcnow().date().isoformat(), "added": n_here})
        last2 = cell["runs"][-2:]
        if len(last2) == 2 and all(r_["added"] < cfg["saturation_min_new"] for r_ in last2):
            cell["status"] = "saturated"
    # mark a matching request done when its area is saturated or this run found nothing new
    req = load("requests.json", [])
    for r_ in req:
        if r_["status"] in ("queued", "in_progress") and (r_.get("label") == tgt or r_.get("sub") == sub.get("sub")):
            r_["runs"] = r_.get("runs", 0) + 1
            r_["status"] = "done" if (len(added) < cfg["saturation_min_new"] and r_["runs"] >= 2) else "in_progress"
    save("requests.json", req)
    st["runs"].append({"at": iso(utcnow()), "target": tgt, "searches": sub.get("searches_used"), "minutes": sub.get("minutes_used"), "added": added, "rejected": rejected, "notes": (sub.get("notes") or "")[:500]})
    st["runs"] = st["runs"][-120:]
    for c in st["cells"].values():
        c.pop("spots", None)
    save("state.json", st)
    print(json.dumps({"added": added, "rejected": rejected}, indent=1))
    return added


def _validate(sp):
    try:
        lat, lon = float(sp["lat"]), float(sp["lon"])
    except Exception:
        return "missing lat/lon"
    if not (-90 < lat < 90 and -180 < lon < 180):
        return "bad coordinates"
    if not sp.get("name") or len(sp["name"]) < 3:
        return "missing name"
    if not sp.get("tip") or len(sp["tip"]) < 60:
        return "tip too short"
    if not [c for c in sp.get("cats", []) if c in CATS]:
        return "no valid category"
    src = sp.get("sources") or []
    if not src or not all(isinstance(x, (list, tuple)) and len(x) == 2 and str(x[1]).startswith("http") for x in src):
        return "needs at least one [title, url] source"
    if sp.get("confidence") == "low":
        return "low confidence: not added"
    return None


# ---------------- export for the app ----------------
def export():
    st = _state()
    extra = []
    for p in sorted((R / "spots").glob("*.json")):
        extra += [s for s in json.load(open(p)) if not s.get("removed")]
    write_json("spots_extra.json", {"gen": iso(utcnow()), "spots": extra})
    cells = {c: {"status": v["status"], "runs": len(v["runs"]), "added": sum(r["added"] for r in v["runs"])} for c, v in st["cells"].items() if v["runs"]}
    write_json("research_status.json", {"gen": iso(utcnow()), "settings": settings(), "requests": load("requests.json", [])[-30:], "runs": st["runs"][-20:], "cells": cells,
                                        "totals": {"researched_spots": len(extra), "cells_saturated": sum(1 for v in st["cells"].values() if v["status"] == "saturated")}})
    return f"{len(extra)} researched spots"


if __name__ == "__main__":
    {"plan": plan, "sync": lambda: print(sync()), "export": lambda: print(export())}[sys.argv[1]]() if sys.argv[1] != "add" else add(sys.argv[2])
