"""Why does a spot rank where it does? For each case (place, window kind, spot names) print the spot's fit score, reasons,
drive minutes and rank among the list. python tools/whyprobe.py -> ux/why.txt"""
import asyncio, json, os
from playwright.async_api import async_playwright
os.makedirs("ux", exist_ok=True)
CASES = [
 ("Moab", 38.573, -109.55, 60, "sunrise", ["Mesa Arch", "Delicate Arch", "Dead Horse Point", "Mars Hotel", "Portal Overlook", "Balanced Rock", "Turret Arch"]),
 ("Cannon Beach", 45.892, -123.961, 30, "sunset", ["Haystack Rock", "Ecola", "Hug Point", "Blumenthal Falls", "Necanicum"]),
 ("Bend", 44.058, -121.315, 60, "sunrise", ["Smith Rock", "Pilot Butte", "Benham Falls", "Drake Park", "Mirror Pond", "Tumalo"]),
 ("La Jolla", 32.847, -117.273, 30, "sunset", ["La Jolla Cove", "Sunset Cliffs", "Scripps", "USS Midway", "Plaza de las Armas", "Windansea", "Torrey Pines"]),
 ("Springdale", 37.189, -112.999, 30, "sunset", ["Watchman", "Canyon Overlook", "Court of the Patriarchs", "Grafton", "Johnson Mountain", "Observation Point", "Towers of the Virgin"]),
 ("Seattle", 47.606, -122.332, 60, "sunrise", ["Kerry Park", "Gas Works", "Gratias Agimus", "Control Tower", "Space Needle", "Alki", "Discovery Park"]),
 ("Acadia", 44.388, -68.204, 30, "sunrise", ["Cadillac", "Otter", "Sand Beach", "Jordan Pond", "Beech Mountain", "Bass Harbor"]),
]
JS = """(([kind, names]) => { const t0 = Date.now(), tom = laYMD(new Date(t0 + 864e5));
  const w = allWindows(LOC, PLAN_HOURS).find(w => winDay(w) === tom && w.kind === kind); if (!w) return "no window";
  const list = rankFor(w); const out = { top: list.slice(0, 6).map(x => `${Math.round(x.f.n)} r${Math.round(x.r)} ${x.s.name} [${x.s.kind}/${x.s.light}] d${Math.round(x.d)}`) };
  for (const nm of names) { const ss = SPOTS.filter(s => s.name.toLowerCase().includes(nm.toLowerCase())).slice(0, 3);
    out[nm] = ss.length ? ss.map(s => { const f = fitFor(s, w), i = list.findIndex(x => x.s === s);
      return `${s.id} [${s.kind}/${s.light}${s.hz ? '/hz' : ''}] score=${s.score} views=${s.views || 0} fame=${typeof seedFame === 'function' && s.seed ? seedFame(s).toFixed(1) : '-'} d=${Math.round(driveMin(s))} far=${tooFar(s)} grp=${inGroup(s)} fit=${f ? Math.round(f.n) : null} rank=${i} :: ${f ? f.why.join('; ').slice(0, 220) : ''}`; }) : "not in SPOTS"; }
  return out; })"""
async def main():
    res = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, lat, lon, md, kind, names in CASES:
            c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles")
            st = {"ss2:loc": {"lat": lat, "lon": lon, "label": name, "src": "search", "at": 9e12}, "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": md, "maxWalk": 30, "start": "gps"}, "ss2:group": "all", "ss2:welcomed": True}
            await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
            pg = await c.new_page(); await pg.goto("https://estaugaa.github.io/shotspots/"); await pg.wait_for_timeout(16000)
            try: r = await pg.evaluate(JS, [kind, names])
            except Exception as e: r = "ERR " + str(e)[:300]
            res.append({"case": f"{name} {kind}", "r": r}); await c.close()
        await b.close()
    open("ux/why.txt", "w").write(json.dumps(res, indent=1))
asyncio.run(main())
