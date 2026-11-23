"""A/B of the spot-quality measure on identical weather: each place ranked with ss2:photoq off (old measure) and on
(photographers, Nov 23), back to back. Prints top 5 both ways and where a well-known anchor spot lands.
    python tools/abtest.py            (diag.yml; output on branch diag-abtest, ab.txt)"""
import asyncio, json, re, os
from playwright.async_api import async_playwright
RANK = re.search(r'RANK = """(.*?)"""', open("tools/expect.py").read(), re.S).group(1).replace("R.slice(0, 10)", "R.slice(0, 20)")
URL = "https://estaugaa.github.io/shotspots/"
CASES = [  # place, lat, lon, drive, window, anchors (well-known spots for that light)
 ("Washougal", 45.582, -122.353, 60, "sunrise", ["Vista House", "Crown Point", "Larch"]),
 ("Cannon Beach", 45.892, -123.961, 30, "sunset", ["Haystack", "Ecola", "Hug Point"]),
 ("Hood River", 45.705, -121.521, 45, "sunrise", ["Rowena", "Panorama", "Vista House", "Lost Lake"]),
 ("Seattle", 47.606, -122.332, 60, "sunrise", ["Kerry Park", "Gas Works", "Alki"]),
 ("Bend", 44.058, -121.315, 60, "sunrise", ["Smith Rock", "Pilot Butte", "Tumalo"]),
 ("Moab", 38.573, -109.55, 60, "sunrise", ["Mesa Arch", "Dead Horse", "Delicate Arch", "Turret"]),
 ("Sedona", 34.870, -111.761, 30, "sunset", ["Airport", "Cathedral Rock", "Bell Rock"]),
 ("Grand Canyon", 36.054, -112.140, 45, "sunrise", ["Mather", "Yaki", "Hopi", "Yavapai"]),
 ("Yosemite", 37.745, -119.593, 45, "sunset", ["Tunnel View", "Glacier Point", "Valley View", "Sentinel"]),
 ("Springdale", 37.189, -112.999, 30, "sunset", ["Watchman", "Canyon Overlook", "Court of the Patriarchs"]),
 ("Denver", 39.739, -104.990, 90, "sunset", ["Red Rocks", "Lookout", "Maroon", "Garden of the Gods"]),
 ("La Jolla", 32.847, -117.273, 30, "sunset", ["La Jolla Cove", "Sunset Cliffs", "Windansea"]),
 ("Acadia", 44.388, -68.204, 30, "sunrise", ["Cadillac", "Otter", "Bass Harbor", "Sand Beach"]),
 ("Smokies", 35.714, -83.510, 45, "sunrise", ["Clingmans", "Newfound", "Morton", "Le Conte"]),
 ("Miami", 25.774, -80.193, 45, "sunrise", ["South Pointe", "Cape Florida", "Bill Baggs", "Miami Beach"]),
 ("Jackson", 43.480, -110.762, 60, "sunrise", ["Mormon", "Schwabacher", "Snake River Overlook", "Oxbow"]),
]
async def rank(br, lat, lon, md, kind, off):
    c = await br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles")
    st = {"ss2:loc": {"lat": lat, "lon": lon, "label": "X", "src": "search", "at": 9e12}, "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": md, "maxWalk": 30, "start": "gps"},
          "ss2:group": "all", "ss2:welcomed": True}
    js = "".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()) + (f'localStorage.setItem("ss2:photoq","0");' if off else 'localStorage.removeItem("ss2:photoq");')
    await c.add_init_script(js); pg = await c.new_page()
    try:
        await pg.goto(URL); await pg.wait_for_timeout(14000); r = await pg.evaluate(RANK, [kind])
    except Exception as e:
        r = {"err": str(e)[:200]}
    await c.close(); return r
async def main():
    out = []
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for name, lat, lon, md, kind, anchors in CASES:
            line = [f"## {name} {kind}"]
            for off in (True, False):
                r = await rank(br, lat, lon, md, kind, off); top = r.get("top", [])
                pos = [next((i + 1 for i, t in enumerate(top) if a.lower() in t["n"].lower()), None) for a in anchors]
                best = min([x for x in pos if x] or [99])
                line.append(f"  {'OLD' if off else 'NEW'} anchor best rank {best if best < 99 else '-'} | " + " | ".join(f'{t["sc"]} {t["n"][:30]}' for t in top[:5]) + (f" ERR {r['err']}" if r.get("err") else ""))
            out.append("\n".join(line)); print(out[-1], flush=True)
        await br.close()
    os.makedirs("diag", exist_ok=True); print("\n".join(out))
asyncio.run(main())
