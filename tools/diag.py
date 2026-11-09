"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite. Real-life scenario walkthroughs."""
import asyncio, os, json
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
os.makedirs("ux", exist_ok=True)
S = [
 ("A owner Washougal, tomorrow sunrise, drive<=60", {"lat": 45.582, "lon": -122.353, "label": "Washougal"}, {"maxDrive": 60}, "all", ("tomorrow", "sunrise")),
 ("B Portland walker, today sunset, walk<=30", {"lat": 45.519, "lon": -122.679, "label": "Downtown Portland"}, {"travel": "walk", "maxWalk": 30}, "all", ("today", "sunset")),
 ("C rainy waterfalls, tomorrow morning", {"lat": 45.582, "lon": -122.353, "label": "Washougal"}, {"maxDrive": 90}, "water", ("tomorrow", "morning")),
 ("D stars tonight, drive<=120", {"lat": 45.582, "lon": -122.353, "label": "Washougal"}, {"maxDrive": 120}, "night", ("today", "night")),
 ("E Seattle, tomorrow sunset", {"lat": 47.61, "lon": -122.33, "label": "Seattle"}, {"maxDrive": 90}, "all", ("tomorrow", "sunset")),
 ("F Bend OR, tomorrow sunrise", {"lat": 44.058, "lon": -121.315, "label": "Bend"}, {"maxDrive": 90}, "all", ("tomorrow", "sunrise")),
 ("G Denver, tomorrow sunset", {"lat": 39.739, "lon": -104.99, "label": "Denver"}, {"maxDrive": 90}, "all", ("tomorrow", "sunset")),
 ("H New York, tomorrow sunset", {"lat": 40.713, "lon": -74.006, "label": "New York"}, {"maxDrive": 60}, "all", ("tomorrow", "sunset")),
]
PICK = """(([day, kind]) => { const all = allWindows(LOC, PLAN_HOURS); const t = laYMD(new Date()), tm = laYMD(new Date(Date.now() + 864e5));
  const want = day === "today" ? t : tm; const i = all.findIndex(w => winDay(w) === want && (w.kind === kind || (kind === "morning" && w.kind === "morning")));
  if (i >= 0) { UI.focus = i; UI.day = want; render(); } return i >= 0 ? wTitle(all[i]) + " " + fmtT(all[i].peak) : "no window " + kind; })"""
async def main():
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, loc, prefs, group, (day, kind) in S:
            c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, timezone_id="America/Los_Angeles",
                                    geolocation={"latitude": loc["lat"], "longitude": loc["lon"]}, permissions=["geolocation"])
            st = {"ss2:loc": {**loc, "src": "search", "at": 9e12}, "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 120, "maxWalk": 30, "start": "gps", **prefs}, "ss2:group": group, "ss2:welcomed": True}
            await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
            pg = await c.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
            await pg.goto(URL); await pg.wait_for_timeout(9000)
            if name.startswith(("E", "F", "G", "H")): await pg.wait_for_timeout(6000)
            win = await pg.evaluate(PICK, [day, kind]); await pg.wait_for_timeout(2500)
            txt = await pg.evaluate("document.querySelector('#v-now')?.innerText || ''")
            out.append(f"\n######## {name}\nLOC={await pg.evaluate('LOC.label')} window={win} spots_loaded={await pg.evaluate('SPOTS.length')} errors={errs[:3]}\n" + txt[:2600])
            top = await pg.evaluate("(() => { const a = document.querySelector('#v-now [data-spot]'); return a ? a.dataset.spot : null })()")
            if top:
                await pg.evaluate(f"openSpot({json.dumps(top)})"); await pg.wait_for_timeout(3500)
                out.append(f"--- top spot page ({top}):\n" + (await pg.evaluate("document.querySelector('#sheetBody')?.innerText || ''"))[:1800])
            await c.close()
        await b.close()
    open("ux/scenarios.txt", "w").write("\n".join(out))
asyncio.run(main())
