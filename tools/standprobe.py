"""Prototype: where photographers stand at a spot, and which way they point (Wikimedia Commons). Output ux/stand.json + ux/stand.txt"""
import json, math, os, re, time, requests
os.makedirs("ux", exist_ok=True)
API = "https://commons.wikimedia.org/w/api.php"
S = requests.Session(); S.headers["User-Agent"] = "ShotSpots/1.0 (https://estaugaa.github.io/shotspots/; photo-planning research)"
SUBJ = {"waterfall", "geology", "historic"}
def q(**p):
    for i in range(4):
        r = S.get(API, params={"format": "json", "formatversion": 2, **p}, timeout=60)
        if r.status_code == 429: time.sleep(10 * (i + 1)); continue
        return r.json()
    return {}
def bearing(a, b):
    y = math.sin(math.radians(b[1] - a[1])) * math.cos(math.radians(b[0])); x = math.cos(math.radians(a[0])) * math.sin(math.radians(b[0])) - math.sin(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.cos(math.radians(b[1] - a[1]))
    return (math.degrees(math.atan2(y, x)) + 360) % 360
def m(a, b): return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))
def num(v):
    try:
        if isinstance(v, (int, float)): return float(v)
        if "/" in str(v): a, b = str(v).split("/")[:2]; return float(a) / float(b)
        return float(v)
    except Exception: return None
def circ(hs):
    s = sum(math.sin(math.radians(h)) for h in hs); c = sum(math.cos(math.radians(h)) for h in hs); R = math.hypot(s, c) / len(hs)
    return (math.degrees(math.atan2(s, c)) + 360) % 360, R   # R: 1 = all agree, 0 = scattered
def photos(s, radius):
    g = q(action="query", list="geosearch", gscoord=f"{s['lat']}|{s['lon']}", gsradius=radius, gslimit=500, gsnamespace=6)
    titles = [x["title"] for x in g.get("query", {}).get("geosearch", [])]
    out = []
    for i in range(0, len(titles), 25):
        j = q(action="query", titles="|".join(titles[i:i + 25]), prop="coordinates|imageinfo", coprimary="all", coprop="type|name|dim", colimit=500,
              iiprop="url|user|timestamp|metadata", iiurlwidth=240)
        for p in j.get("query", {}).get("pages", []):
            co = p.get("coordinates") or []; ii = (p.get("imageinfo") or [{}])[0]
            cam = next((c for c in co if c.get("primary")), None); obj = next((c for c in co if not c.get("primary")), None)
            if not cam: continue
            md = {x["name"]: x["value"] for x in (ii.get("metadata") or []) if isinstance(x, dict) and "name" in x}
            h = num(md.get("GPSImgDirection")); src = "exif" if h is not None else None
            if h is None and obj: h = bearing((cam["lat"], cam["lon"]), (obj["lat"], obj["lon"])); src = "object"
            out.append({"t": p["title"][5:], "lat": cam["lat"], "lon": cam["lon"], "h": None if h is None else round(h % 360), "hs": src, "u": ii.get("user"),
                        "d": (ii.get("timestamp") or "")[:4], "img": ii.get("thumburl"), "url": ii.get("descriptionurl")})
        time.sleep(0.5)
    return out
FK = os.environ.get("FLICKR_KEY")
def flickr(s, radius_km):
    """Flickr geotags (street-level accuracy only), with compass heading read from EXIF for up to 40 photos."""
    if not FK: return []
    out = []
    for page in (1, 2):
        j = S.get("https://api.flickr.com/services/rest/", params={"method": "flickr.photos.search", "api_key": FK, "lat": s["lat"], "lon": s["lon"], "radius": radius_km, "radius_units": "km",
              "has_geo": 1, "min_taken_date": "2005-01-01", "accuracy": 15, "content_type": 1, "media": "photos", "per_page": 250, "page": page,
              "extras": "geo,owner_name,url_q,date_taken", "format": "json", "nojsoncallback": 1}, timeout=60).json()
        ph = (j.get("photos") or {}).get("photo") or []
        for p in ph:
            if int(p.get("accuracy") or 0) < 15: continue
            out.append({"t": p.get("title") or "", "lat": float(p["latitude"]), "lon": float(p["longitude"]), "h": None, "hs": None, "u": "f:" + p["owner"], "d": (p.get("datetaken") or "")[:4],
                        "img": p.get("url_q"), "url": f"https://www.flickr.com/photos/{p['owner']}/{p['id']}", "fid": p["id"], "src": "flickr"})
        if len(ph) < 250: break
        time.sleep(0.5)
    # heading from EXIF: one call per photo, one photo per photographer, nearest first
    seen, n = set(), 0
    for p in sorted(out, key=lambda x: m((x["lat"], x["lon"]), (s["lat"], s["lon"]))):
        if p["u"] in seen or n >= 40: continue
        seen.add(p["u"]); n += 1
        try:
            e = S.get("https://api.flickr.com/services/rest/", params={"method": "flickr.photos.getExif", "api_key": FK, "photo_id": p["fid"], "format": "json", "nojsoncallback": 1}, timeout=30).json()
            for t in (e.get("photo") or {}).get("exif") or []:
                if t.get("tag") == "GPSImgDirection": h = num(str((t.get("raw") or {}).get("_content", "")).split()[0]); p["h"], p["hs"] = (round(h) % 360, "exif") if h is not None else (None, None)
        except Exception: pass
        time.sleep(0.25)
    return out
CW = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5}
def osm_dir(v):
    """OSM direction=*: degrees, compass letters, a range '45-135', or a list 'N;E'. Returns (centre, width) or None."""
    v = (v or "").strip().upper()
    parts = [x.strip() for x in v.split(";") if x.strip()]
    hs = []
    for x in parts:
        if "-" in x and not x.startswith("-"):
            a, b = [CW.get(y.strip(), num(y.strip())) for y in x.split("-", 1)]
            if a is not None and b is not None:
                w = (b - a) % 360; hs.append(((a + w / 2) % 360, w)); continue
        h = CW.get(x, num(x))
        if h is not None: hs.append((h % 360, 0))
    if not hs: return None
    if len(hs) == 1: return hs[0]
    f, R = circ([h for h, _ in hs]); return (f, 180 * (1 - R))
def osm_viewpoints(s, radius=400):
    q_ = f'[out:json][timeout:60];(node(around:{radius},{s["lat"]},{s["lon"]})[tourism=viewpoint];way(around:{radius},{s["lat"]},{s["lon"]})[tourism=viewpoint];);out center tags;'
    for url in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"):
        try:
            j = S.post(url, data={"data": q_}, timeout=90).json(); break
        except Exception: j = {}
    out = []
    for e in j.get("elements", []):
        la, lo = e.get("lat") or e.get("center", {}).get("lat"), e.get("lon") or e.get("center", {}).get("lon")
        t = e.get("tags", {}); d = osm_dir(t.get("direction") or t.get("viewpoint:direction"))
        out.append({"lat": la, "lon": lo, "name": t.get("name"), "dir": t.get("direction") or t.get("viewpoint:direction"), "face": None if not d else round(d[0]), "width": None if not d else round(d[1]),
                    "dist": round(m((la, lo), (s["lat"], s["lon"]))), "id": f'{e["type"]}/{e["id"]}'})
    return sorted(out, key=lambda x: x["dist"])
def wikidata_pov(s, km_=1.5):
    sp = f"""SELECT ?item ?itemLabel ?pov WHERE {{ SERVICE wikibase:around {{ ?item wdt:P625 ?loc . bd:serviceParam wikibase:center "Point({s['lon']} {s['lat']})"^^geo:wktLiteral; wikibase:radius "{km_}" }}
      ?item wdt:P1259 ?pov . SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }} LIMIT 20"""
    try: j = S.get("https://query.wikidata.org/sparql", params={"query": sp, "format": "json"}, timeout=60).json()
    except Exception: return []
    out = []
    for b in j.get("results", {}).get("bindings", []):
        mm = re.findall(r"[-\d.]+", b["pov"]["value"])
        if len(mm) >= 2: out.append({"name": b.get("itemLabel", {}).get("value"), "lon": float(mm[0]), "lat": float(mm[1])})
    return out
MT = os.environ.get("MAPILLARY_TOKEN")
def mapillary(lat, lon, half_m=120):
    """Street-level photos near a point. Keeps 'off-axis' frames: ones pointing well away from the direction the camera was travelling,
    i.e. someone stopped and aimed at something, not a dashcam rolling past."""
    if not MT: return None
    dl = half_m / 111320; dn = half_m / (111320 * math.cos(math.radians(lat)))
    try:
        j = S.get("https://graph.mapillary.com/images", params={"access_token": MT, "bbox": f"{lon-dn},{lat-dl},{lon+dn},{lat+dl}", "limit": 2000,
                  "fields": "id,geometry,compass_angle,captured_at,sequence,is_pano,creator"}, timeout=90).json()
    except Exception as e: return {"error": str(e)[:120]}
    if "error" in j: return {"error": str(j["error"])[:160]}
    rows = [x for x in j.get("data", []) if not x.get("is_pano") and x.get("compass_angle") is not None]
    seq = {}
    for x in rows: seq.setdefault(x.get("sequence"), []).append(x)
    off, users = [], set()
    for sq, xs in seq.items():
        xs.sort(key=lambda x: x.get("captured_at") or 0)
        for i, x in enumerate(xs):
            c = x["geometry"]["coordinates"]; nb = xs[i + 1] if i + 1 < len(xs) else (xs[i - 1] if i else None)
            if nb:
                nc = nb["geometry"]["coordinates"]; mv = m((c[1], c[0]), (nc[1], nc[0]))
                if mv > 3:   # moving: compare heading with travel direction
                    tb = bearing((c[1], c[0]), (nc[1], nc[0])) if nb is not x and i + 1 < len(xs) else bearing((nc[1], nc[0]), (c[1], c[0]))
                    if abs((x["compass_angle"] - tb + 540) % 360 - 180) < 50: continue   # looking where it was going
            off.append(x["compass_angle"] % 360); users.add((x.get("creator") or {}).get("id") if isinstance(x.get("creator"), dict) else sq)
    res = {"n": len(rows), "seqs": len(seq), "off": len(off), "users": len(users)}
    if len(off) >= 4:
        # strongest 45-degree sector, then its circular mean
        best = max(range(0, 360, 15), key=lambda a: sum(1 for h in off if abs((h - a + 540) % 360 - 180) <= 22.5))
        sec = [h for h in off if abs((h - best + 540) % 360 - 180) <= 22.5]
        f, R = circ(sec); res.update(face=round(f), share=round(len(sec) / len(off), 2), n_sec=len(sec))
    return res
def analyse(s):
    subj = bool(SUBJ & set(s["cats"]))
    key = [w for w in re.findall(r"[A-Za-z]{5,}", s["name"]) if w.lower() not in {"falls", "state", "point", "regional", "park", "national", "refuge", "trail", "historic", "creek", "preserve", "wildlife", "viewpoint", "mansion", "house", "bridge", "tunnels", "forum", "women", "portland", "lookout", "pullout", "river", "beach", "eagle", "natural"}]
    P = photos(s, 1500 if subj else 400) + flickr(s, 1.5 if subj else 0.4)
    near = []
    for p in P:
        d = m((p["lat"], p["lon"]), (s["lat"], s["lon"]))
        named = any(k.lower() in p["t"].lower() for k in key)
        aimed = p["h"] is not None and abs((bearing((p["lat"], p["lon"]), (s["lat"], s["lon"])) - p["h"] + 540) % 360 - 180) < 30
        p["dist"] = round(d); p["named"] = named
        if (subj and (named or (aimed and d < 800))) or (not subj and (d < 250 or named)): near.append(p)
    # cluster camera positions (40 m), score by distinct photographers
    best = None
    for p in near:
        grp = [x for x in near if m((p["lat"], p["lon"]), (x["lat"], x["lon"])) < 40]
        users = len({x["u"] for x in grp})
        if not best or users > best[0]: best = (users, grp)
    res = {"id": s["id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"], "role": "subject" if subj else "standpoint", "light": s.get("light"), "keys": key,
           "n_all": len(P), "n_used": len(near), "n_users": len({x["u"] for x in near}), "n_head": sum(1 for x in near if x["h"] is not None),
           "n_exif": sum(1 for x in near if x["hs"] == "exif"), "photos": near}
    if best and best[0] >= 2:
        g = best[1]; lat = sum(x["lat"] for x in g) / len(g); lon = sum(x["lon"] for x in g) / len(g)
        hs = [x["h"] for x in g if x["h"] is not None]
        res["stand"] = {"lat": round(lat, 5), "lon": round(lon, 5), "users": best[0], "photos": len(g), "dist_from_pin": round(m((lat, lon), (s["lat"], s["lon"])))}
        if len(hs) >= 3:
            f, R = circ(hs); res["stand"].update(face=round(f), agree=round(R, 2), n_head=len(hs), how="measured")
        elif subj and m((lat, lon), (s["lat"], s["lon"])) > 30:
            res["stand"].update(face=round(bearing((lat, lon), (s["lat"], s["lon"]))), how="toward subject")
    res["osm"] = osm_viewpoints(s)[:4]
    res["wd"] = wikidata_pov(s)
    st = res.get("stand") or {}
    at = (st["lat"], st["lon"]) if st else (res["osm"][0]["lat"], res["osm"][0]["lon"]) if res["osm"] and res["osm"][0]["dist"] < 250 else (s["lat"], s["lon"])
    res["mly"] = mapillary(*at)
    return res
OUT = []; spots = json.load(open("tools/stand_spots.json"))
if os.environ.get("ONLY"): spots = [x for x in spots if x["id"] in os.environ["ONLY"].split(",")]
_dbg = "FLICKR_KEY set: %s (len %d)" % (bool(FK), len(FK or ""))
try:
    r = S.get("https://api.flickr.com/services/rest/", params={"method": "flickr.photos.search", "api_key": FK or "", "lat": 45.5762, "lon": -122.1158, "radius": 0.5, "has_geo": 1, "min_taken_date": "2005-01-01", "per_page": 3, "format": "json", "nojsoncallback": 1}, timeout=30)
    _dbg += f" | HTTP {r.status_code}: {r.text[:300]}"
except Exception as e: _dbg += f" | error {e}"
for s in spots:
    try: OUT.append(analyse(s))
    except Exception as e: OUT.append({"id": s["id"], "name": s["name"], "error": str(e)[:200]})
    time.sleep(1)
json.dump(OUT, open("ux/stand.json", "w"))
lines = []
for r in OUT:
    st = r.get("stand") or {}
    o = (r.get("osm") or [{}])[0]; ml = r.get("mly") or {}
    lines.append(f"{r['id']:<18} OSM vp={len(r.get('osm') or [])} nearest={o.get('dist','-')}m dir={o.get('dir')} | WD pov={len(r.get('wd') or [])} | MLY n={ml.get('n','-')} off={ml.get('off','-')} face={ml.get('face','-')} share={ml.get('share','-')} {ml.get('error','')}")
    lines.append(f"{'':<18} {r.get('role','?'):<10} all={r.get('n_all')} used={r.get('n_used')} users={r.get('n_users')} heading={r.get('n_head')} (exif {r.get('n_exif')}) | stand: {st.get('users','-')} people, {st.get('dist_from_pin','-')} m from pin, face {st.get('face','-')} {st.get('how','')} agree={st.get('agree','')} | light={r.get('light')} {r.get('error','')}")
open("ux/stand.txt", "w").write(_dbg + "\n" + "\n".join(lines))
