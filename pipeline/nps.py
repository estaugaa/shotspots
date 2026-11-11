"""National Park Service: live alerts, closures and timed-entry rules for every NPS unit, with park outlines.

feed/nps.json  {gen, parks: [{c, n, url, b: [w,s,e,n], r: [thinned rings], al: [{t, cat, url, d}], te: "timed-entry text"}]}
The app tests a spot against the outlines (bbox first, then ring) and shows that park's alerts on the spot page.
Alerts are MEASURED (the park's own notices); whether one affects a particular viewpoint is left to the reader.

Needs a free api.data.gov key in the NPS_API_KEY secret (DEMO_KEY is shared and rate-limited, so outlines are
only fetched with a real key; they are cached in data/nps_bounds.json and refreshed every 30 days).
"""
import os, re, time, json
from .common import http, write_json, read_json, DATA, log, utcnow, iso

API = "https://developer.nps.gov/api/v1"
KEY = os.environ.get("NPS_API_KEY") or "DEMO_KEY"
BOUNDS = DATA / "nps_bounds.json"


def _all(ep, **params):
    out, start = [], 0
    while True:
        j = http(f"{API}/{ep}", params={"api_key": KEY, "limit": 500, "start": start, **params}, timeout=90).json()
        d = j.get("data") or []
        out += d
        start += len(d)
        if not d or start >= int(j.get("total") or 0):
            return out


def _rings(geom, keep=6, pts=160):
    if not geom:
        return None, None
    if geom.get("type") == "FeatureCollection":
        fs = geom.get("features") or []
        polys = [p for f in fs for p in _polys(f.get("geometry"))]
    elif geom.get("type") == "Feature":
        polys = _polys(geom.get("geometry"))
    else:
        polys = _polys(geom)
    rings = [p[0] for p in polys if p and len(p[0]) >= 4]
    if not rings:
        return None, None
    area = lambda r: abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2
    rings = sorted(rings, key=area, reverse=True)[:keep]
    big = area(rings[0])
    rings = [r for r in rings if area(r) >= big * 0.002]
    thin = [[[round(x, 4), round(y, 4)] for x, y in r[:: max(1, len(r) // pts)]] for r in rings]
    xs = [p[0] for r in thin for p in r]; ys = [p[1] for r in thin for p in r]
    return [min(xs), min(ys), max(xs), max(ys)], thin


def _polys(g):
    if not g:
        return []
    return g["coordinates"] if g.get("type") == "MultiPolygon" else [g["coordinates"]] if g.get("type") == "Polygon" else []


def _bounds(codes):
    old = read_json(BOUNDS) or {}
    fresh = old.get("gen") and time.time() - old.get("t", 0) < 30 * 86400
    if fresh or KEY == "DEMO_KEY":
        return old.get("parks", {})
    got = dict(old.get("parks", {}))
    for c in codes:
        try:
            g = http(f"{API}/mapdata/parkboundaries/{c}", params={"api_key": KEY}, timeout=90, tries=2).json()
            b, r = _rings(g)
            if b:
                got[c] = {"b": b, "r": r}
        except Exception as e:
            log(f"nps bounds {c}: {e}")
        time.sleep(0.4)
    BOUNDS.write_text(json.dumps({"gen": iso(utcnow()), "t": time.time(), "parks": got}, separators=(",", ":")))
    return got


TIMED = re.compile(r"timed[- ]entry|reservation[s]? (?:is |are )?required|vehicle reservation|entry reservation", re.I)


def run():
    parks = _all("parks", fields="url")
    alerts = _all("alerts")
    fees = []
    try:
        fees = _all("feespasses")
    except Exception as e:
        log(f"nps feespasses: {e}")
    te = {}
    for f in fees:
        code = f.get("parkCode")
        txt = " ".join(str(v) for k, v in f.items() if re.search(r"timed|reserv", k, re.I) and v and v is not True)
        flag = any(v is True for k, v in f.items() if re.search(r"timed|reserv", k, re.I))
        if code and (flag or TIMED.search(txt)):
            te[code] = re.sub(r"<[^>]+>", " ", txt).strip()[:400] or "Timed entry or a reservation is required at some times."
    al = {}
    for a in alerts:
        c = a.get("parkCode")
        if not c:
            continue
        al.setdefault(c, []).append({"t": (a.get("title") or "")[:160], "cat": a.get("category") or "", "url": a.get("url") or "",
                                     "d": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", a.get("description") or "")).strip()[:300]})
        if c not in te and TIMED.search((a.get("title") or "") + " " + (a.get("description") or "")):
            te[c] = (a.get("title") or "")[:200]
    order = {"Park Closure": 0, "Danger": 1, "Caution": 2, "Information": 3}
    bounds = _bounds([p["parkCode"] for p in parks])
    out = []
    for p in parks:
        c = p.get("parkCode")
        bo = bounds.get(c)
        rec = {"c": c, "n": p.get("fullName"), "url": p.get("url")}
        if bo:
            rec.update(bo)
        else:   # no outline yet: centre point only (the app uses a small radius)
            try:
                rec["pt"] = [round(float(p["longitude"]), 4), round(float(p["latitude"]), 4)]
            except (KeyError, ValueError, TypeError):
                continue
        if c in al:
            rec["al"] = sorted(al[c], key=lambda x: order.get(x["cat"], 4))[:8]
        if c in te:
            rec["te"] = te[c]
        if "al" in rec or "te" in rec:
            out.append(rec)
    write_json("nps.json", {"gen": iso(utcnow()), "key": "own" if KEY != "DEMO_KEY" else "demo", "parks": out})
    return f"{len(out)} parks with alerts or timed entry ({sum(len(x.get('al', [])) for x in out)} alerts, {len(te)} timed-entry, {len(bounds)} outlines)"
