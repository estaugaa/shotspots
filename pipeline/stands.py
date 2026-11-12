"""Where to stand, and which way the classic shot points.

For each worthwhile spot: cluster the camera positions of geotagged Wikimedia Commons photos (distinct photographers,
not photo counts) to find where people actually stand; take the classic direction from the cameras' compass headings.
OpenStreetMap viewpoints fill in a stand position where Commons is thin. Mapillary street-level photos give a direction
that is only trusted when it agrees with another source (alone it is shown as unconfirmed: road traffic skews it).

feed/stands/<tile>.json  {_at, <spot id>: {st:[lat,lon], d:m from pin, u:photographers, f:deg, fs:source, ag:agreement, ex:[[title,url]]}}
feed/stands/researched.json  same, for the hand-researched spots
fs: "photos" (measured, confident) | "feature" (toward a waterfall/arch/etc, confident) | "agree" (two sources agree) | "street" (Mapillary only)
Prototype and checks: tools/standprobe.py (Gorge spots, Nov 2026).
"""
import json, math, os, re, time
import requests
from .common import FEED, log, utcnow, iso, read_json

API = "https://commons.wikimedia.org/w/api.php"
S = requests.Session(); S.headers["User-Agent"] = "ShotSpots/1.0 (https://estaugaa.github.io/shotspots/; photo-planning research)"
MT = os.environ.get("MAPILLARY_TOKEN")
KINDS = {"viewpoint", "lookout", "waterfall", "arch", "lighthouse", "bridge", "landmark", "beach", "lake", "peak"}
SUBJECT = {"waterfall", "arch", "lighthouse", "bridge", "landmark"}
NOISE = re.compile(r"interior|inside|plaque|sign\b|signs\b|museum|exhibit|menu|room\b|ceiling|panel|display|map\b|brochure|restroom|toilet|parking", re.I)
STOP = {"falls", "state", "point", "regional", "park", "national", "refuge", "trail", "historic", "creek", "preserve", "wildlife", "viewpoint", "overlook",
        "mansion", "house", "bridge", "tunnels", "forum", "lookout", "pullout", "river", "beach", "natural", "county", "scenic", "upper", "lower", "north", "south"}


def m(a, b): return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))
def bearing(a, b):
    y = math.sin(math.radians(b[1] - a[1])) * math.cos(math.radians(b[0]))
    x = math.cos(math.radians(a[0])) * math.sin(math.radians(b[0])) - math.sin(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.cos(math.radians(b[1] - a[1]))
    return (math.degrees(math.atan2(y, x)) + 360) % 360
def adiff(a, b): return abs((a - b + 540) % 360 - 180)
def circ(hs):
    s = sum(math.sin(math.radians(h)) for h in hs); c = sum(math.cos(math.radians(h)) for h in hs)
    return (math.degrees(math.atan2(s, c)) + 360) % 360, math.hypot(s, c) / len(hs)
def num(v):
    try:
        if isinstance(v, (int, float)): return float(v)
        a, _, b = str(v).partition("/"); return float(a) / float(b) if b else float(a)
    except Exception: return None


def _get(url, params, tries=4):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=60)
            if r.status_code in (429, 503): time.sleep(8 * (i + 1)); continue
            return r.json()
        except Exception:
            time.sleep(3 * (i + 1))
    return {}


def commons(lat, lon, radius):
    g = _get(API, {"format": "json", "formatversion": 2, "action": "query", "list": "geosearch", "gscoord": f"{lat}|{lon}", "gsradius": radius, "gslimit": 200, "gsnamespace": 6})
    titles = [x["title"] for x in g.get("query", {}).get("geosearch", []) if not NOISE.search(x["title"])]
    out = []
    for i in range(0, len(titles), 50):
        j = _get(API, {"format": "json", "formatversion": 2, "action": "query", "titles": "|".join(titles[i:i + 50]), "prop": "coordinates|imageinfo",
                       "coprimary": "all", "colimit": 500, "iiprop": "url|user|metadata"})
        for p in j.get("query", {}).get("pages", []):
            co = p.get("coordinates") or []; ii = (p.get("imageinfo") or [{}])[0]
            cam = next((c for c in co if c.get("primary")), None); obj = next((c for c in co if not c.get("primary")), None)
            if not cam: continue
            md = {x["name"]: x["value"] for x in (ii.get("metadata") or []) if isinstance(x, dict) and "name" in x}
            h = num(md.get("GPSImgDirection"))
            if h is None and obj: h = bearing((cam["lat"], cam["lon"]), (obj["lat"], obj["lon"]))
            out.append({"t": p["title"][5:], "lat": cam["lat"], "lon": cam["lon"], "h": None if h is None else h % 360, "u": ii.get("user"), "url": ii.get("descriptionurl")})
        time.sleep(0.3)
    return out


def osm_viewpoints(spots):
    """One Overpass call per tile: tourism=viewpoint near any of the tile's spots."""
    if not spots: return []
    la = [s["lat"] for s in spots]; lo = [s["lon"] for s in spots]
    q = f'[out:json][timeout:120];(node["tourism"="viewpoint"]({min(la)-.01},{min(lo)-.01},{max(la)+.01},{max(lo)+.01}););out;'
    for url in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"):
        try:
            return [(e["lat"], e["lon"]) for e in S.post(url, data={"data": q}, timeout=150).json().get("elements", [])]
        except Exception:
            continue
    return []


def mapillary(lat, lon, half_m=120):
    if not MT: return None
    dl = half_m / 111320; dn = half_m / (111320 * math.cos(math.radians(lat)))
    j = _get("https://graph.mapillary.com/images", {"access_token": MT, "bbox": f"{lon-dn},{lat-dl},{lon+dn},{lat+dl}", "limit": 1000,
                                                     "fields": "geometry,compass_angle,captured_at,sequence,is_pano"}, tries=2)
    rows = [x for x in j.get("data", []) if not x.get("is_pano") and x.get("compass_angle") is not None]
    seq = {}
    for x in rows: seq.setdefault(x.get("sequence"), []).append(x)
    off = []
    for xs in seq.values():
        xs.sort(key=lambda x: x.get("captured_at") or 0)
        for i, x in enumerate(xs):
            c = x["geometry"]["coordinates"]
            nb = xs[i + 1] if i + 1 < len(xs) else (xs[i - 1] if i else None)
            if nb:
                nc = nb["geometry"]["coordinates"]
                if m((c[1], c[0]), (nc[1], nc[0])) > 3:
                    tb = bearing((c[1], c[0]), (nc[1], nc[0])) if i + 1 < len(xs) else bearing((nc[1], nc[0]), (c[1], c[0]))
                    if adiff(x["compass_angle"], tb) < 60: continue   # facing the way it was travelling
            off.append(x["compass_angle"] % 360)
    if len(off) < 5: return None
    best = max(range(0, 360, 15), key=lambda a: sum(1 for h in off if adiff(h, a) <= 22.5))
    sec = [h for h in off if adiff(h, best) <= 22.5]
    if len(sec) < 5 or len(sec) / len(off) < 0.4: return None
    return circ(sec)[0]


def analyse(s, vps):
    kind = s.get("kind") or ("waterfall" if "waterfall" in s.get("cats", []) else "viewpoint")
    subj = kind in SUBJECT or "waterfall" in s.get("cats", [])
    pin = (s["lat"], s["lon"])
    key = [w for w in re.findall(r"[A-Za-z]{5,}", s["name"]) if w.lower() not in STOP]
    P = commons(s["lat"], s["lon"], 1200 if subj else 300)
    near = []
    for p in P:
        d = m((p["lat"], p["lon"]), pin)
        named = any(k.lower() in p["t"].lower() for k in key)
        aimed = p["h"] is not None and adiff(bearing((p["lat"], p["lon"]), pin), p["h"]) < 30
        if (subj and (named or (aimed and d < 800))) or (not subj and (d < 250 or named)):
            near.append(p)
    rec = {}
    best = None
    for p in near:
        grp = [x for x in near if m((p["lat"], p["lon"]), (x["lat"], x["lon"])) < 40]
        users = len({x["u"] for x in grp})
        if not best or users > best[0]: best = (users, grp)
    vp = min(vps, key=lambda v: m(v, pin)) if vps else None
    vp_d = m(vp, pin) if vp else 1e9
    if best and (best[0] >= 3 or (best[0] >= 2 and vp and m(vp, (best[1][0]["lat"], best[1][0]["lon"])) < 50)):
        g = best[1]
        st = (sum(x["lat"] for x in g) / len(g), sum(x["lon"] for x in g) / len(g))
        rec = {"st": [round(st[0], 5), round(st[1], 5)], "u": best[0]}
        hs = [x["h"] for x in g if x["h"] is not None]
        ex = sorted(g, key=lambda x: x["h"] is None)[:2]
        rec["ex"] = [[x["t"][:70], x["url"]] for x in ex if x.get("url")]
    elif vp and vp_d < 150 and not subj:
        st = vp; rec = {"st": [round(vp[0], 5), round(vp[1], 5)], "u": 0}; hs = []
    else:
        st, hs = pin, []
    if rec:
        rec["d"] = round(m(st, pin))
    # direction
    face = src = None; ag = None
    if len(hs) >= 4:
        f, R = circ(hs)
        if R >= 0.75: face, src, ag = f, "photos", R
    if face is None and subj and rec and rec["d"] >= 30:
        face, src = bearing(st, pin), "feature"
    if face is None:
        mf = mapillary(*st)
        if mf is not None:
            weak = circ(hs)[0] if len(hs) >= 2 else None
            if weak is not None and adiff(weak, mf) <= 35: face, src = mf, "agree"
            else: face, src = mf, "street"
    if face is not None:
        rec.update(f=round(face), fs=src)
        if ag: rec["ag"] = round(ag, 2)
    return rec or None


def _worth(s):
    if s.get("kind") == "peak": return (s.get("pop") or 0) >= 8
    return s.get("kind") in KINDS


def run(budget_min=300):
    sd, od = FEED / "seed", FEED / "stands"; od.mkdir(exist_ok=True)
    t0, tiles, found, n = time.time(), 0, 0, 0
    # researched spots first (one file), refreshed every 90 days
    rp = od / "researched.json"
    old = read_json(rp, {}) or {}
    if old.get("_at", "") < iso(utcnow() - __import__("datetime").timedelta(days=90))[:10]:
        txt = (FEED.parent / "app" / "data.js").read_text()
        spots = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])["spots"]
        out = {"_at": iso(utcnow())[:10]}
        for s in spots:
            try:
                r = analyse(s, []); n += 1
                if r: out[s["id"]] = r; found += 1
            except Exception as e:
                log(f"stands {s['id']}: {e}")
        rp.write_text(json.dumps(out, separators=(",", ":")))
    pops = {}
    for f in sorted(sd.glob("*_*.json"), key=lambda f: (od / f.name).exists()):
        if time.time() - t0 > budget_min * 60:
            open(".more", "w").write("1")
            break
        o = read_json(od / f.name, {}) or {}
        if o.get("_at", "") >= iso(utcnow() - __import__("datetime").timedelta(days=120))[:10]:
            continue
        pp = read_json(FEED / "seedpop" / f.name, {}) or {}
        allsp = [dict(s, pop=(pp.get(s["id"]) or [None])[0]) for s in (read_json(f, {}) or {}).get("spots", [])]
        spots = sorted([s for s in allsp if _worth(s)], key=lambda s: -(s.get("pop") or 0))
        vps = [(s["lat"], s["lon"]) for s in allsp if s.get("kind") in ("viewpoint", "lookout")]   # OSM viewpoints are already in the starter-spot data
        out = {"_at": iso(utcnow())[:10]}
        for s in spots:
            try:
                r = analyse(s, [v for v in vps if 1 < m(v, (s["lat"], s["lon"])) < 400] if s.get("kind") not in ("viewpoint", "lookout") else []); n += 1
                if r: out[s["id"]] = r; found += 1
            except Exception as e:
                log(f"stands {s['id']}: {e}")
        (od / f.name).write_text(json.dumps(out, separators=(",", ":")))
        tiles += 1
    (od / "index.json").write_text(json.dumps(sorted(f.stem for f in od.glob("*_*.json"))))
    left = sum(1 for f in sd.glob("*_*.json") if not (od / f.name).exists())
    log(f"stands: {n} spots in {round((time.time() - t0) / 60)} min")
    return f"{tiles} tiles, {n} spots checked, {found} with a stand or direction; {left} tiles left"
