"""Grab live road-camera images near a place (ODOT TripCheck inventory), for checking scores against the real sky.
python tools/camgrab.py [lat lon km] -> ux/cams/*.jpg + ux/cams.json"""
import requests, re, json, os, sys, math, time
os.makedirs("ux/cams", exist_ok=True)
lat, lon, R = (float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (45.582, -122.353, 45)
H = {"User-Agent": "Mozilla/5.0 (ShotSpots research; github.com/estaugaa/shotspots)"}
log = []
def km(a, b, c, d): return 6371 * 2 * math.asin(math.sqrt(math.sin(math.radians(c - a) / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(math.radians(d - b) / 2) ** 2))
cams = []
for url in ["https://tripcheck.com/Scripts/map/data/cctvinventory.js", "https://www.tripcheck.com/Scripts/map/data/cctvinventory.js"]:
    try:
        r = requests.get(url, headers=H, timeout=30); log.append(f"{url}: {r.status_code} {len(r.text)} {r.text[:300]!r}")
        if r.ok:
            txt = r.text; j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1]) if "{" in txt else None
            feats = (j or {}).get("features", [])
            for f in feats:
                a = f.get("attributes") or f.get("properties") or {}; g = f.get("geometry") or {}
                la = a.get("latitude") or g.get("y"); lo = a.get("longitude") or g.get("x")
                if la is None: continue
                cams.append({"name": a.get("title") or a.get("name"), "lat": float(la), "lon": float(lo), "file": a.get("filename") or a.get("fileName"), "raw": {k: a[k] for k in list(a)[:12]}})
            break
    except Exception as e: log.append(f"{url}: ERR {e}")
near = sorted([c for c in cams if km(lat, lon, c["lat"], c["lon"]) <= R], key=lambda c: km(lat, lon, c["lat"], c["lon"]))[:14]
for c in near:
    fn = c["file"]; urls = [f"https://tripcheck.com/RoadCams/cams/{fn}", f"https://www.tripcheck.com/RoadCams/cams/{fn}"] if fn else []
    for u in urls:
        try:
            r = requests.get(u, headers=H, timeout=30)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                p = f"ux/cams/{re.sub(r'[^A-Za-z0-9]+', '_', c['name'] or fn)[:50]}.jpg"; open(p, "wb").write(r.content); c["img"] = p; break
            log.append(f"{u}: {r.status_code} {r.headers.get('content-type')}")
        except Exception as e: log.append(f"{u}: ERR {e}")
    time.sleep(0.5)
json.dump({"at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "n_inventory": len(cams), "near": near, "log": log[:40]}, open("ux/cams.json", "w"), indent=1)
print(len(cams), "cams;", sum(1 for c in near if c.get("img")), "images saved")
