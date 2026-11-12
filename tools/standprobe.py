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
def analyse(s):
    subj = bool(SUBJ & set(s["cats"]))
    key = [w for w in re.findall(r"[A-Za-z]{5,}", s["name"]) if w.lower() not in {"falls", "state", "point", "regional", "park", "national", "refuge", "trail", "historic", "creek", "preserve", "wildlife", "viewpoint", "mansion", "house", "bridge", "tunnels", "forum", "women", "portland", "lookout", "pullout", "river", "beach", "eagle", "natural"}]
    P = photos(s, 1500 if subj else 400)
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
    return res
OUT = []; spots = json.load(open("tools/stand_spots.json"))
for s in spots:
    try: OUT.append(analyse(s))
    except Exception as e: OUT.append({"id": s["id"], "name": s["name"], "error": str(e)[:200]})
    time.sleep(1)
json.dump(OUT, open("ux/stand.json", "w"))
lines = []
for r in OUT:
    st = r.get("stand") or {}
    lines.append(f"{r['id']:<18} {r.get('role','?'):<10} all={r.get('n_all')} used={r.get('n_used')} users={r.get('n_users')} heading={r.get('n_head')} (exif {r.get('n_exif')}) | stand: {st.get('users','-')} people, {st.get('dist_from_pin','-')} m from pin, face {st.get('face','-')} {st.get('how','')} agree={st.get('agree','')} | light={r.get('light')} {r.get('error','')}")
open("ux/stand.txt", "w").write("\n".join(lines))
