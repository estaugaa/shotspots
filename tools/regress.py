"""Nightly regression: 5 real-use scenarios on the live site with hard checks. Exits non-zero (so GitHub emails the
owner) when any check fails. Results also go to the run summary."""
import asyncio, json, os, sys
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
S = [
 ("Washougal, drive 60", {"lat": 45.582, "lon": -122.353, "label": "Washougal"}, {"maxDrive": 60}, "all", True),
 ("Portland walker, 20 min", {"lat": 45.523, "lon": -122.676, "label": "Pearl District"}, {"travel": "walk", "maxWalk": 20}, "all", False),
 ("Seattle, drive 60", {"lat": 47.61, "lon": -122.33, "label": "Seattle"}, {"maxDrive": 60}, "all", False),
 ("Denver, drive 90", {"lat": 39.739, "lon": -104.99, "label": "Denver"}, {"maxDrive": 90}, "all", False),
 ("Bend waterfalls, drive 60", {"lat": 44.058, "lon": -121.315, "label": "Bend"}, {"maxDrive": 60}, "water", False),
]
CHECK = """(async () => {
  const t0 = Date.now(); while (!WX && Date.now() - t0 < 30000) await new Promise(r => setTimeout(r, 500));
  const all = allWindows(LOC, PLAN_HOURS), want = laYMD(new Date(Date.now() + 864e5));
  const b = [...document.querySelectorAll('[data-day]')].find(x => x.dataset.day === want); if (b) b.click();
  await new Promise(r => setTimeout(r, 1500));
  const w = all[UI.focus], dayOk = !!b && winDay(w) === want;
  const ranked = rankFor(w), tops = windowTops(all), chip = tops[UI.focus] ? tops[UI.focus].f.n : null, top = ranked[0] ? ranked[0].f.n : null;
  const txt = document.querySelector('#v-now').innerText, home = km(LOC, HOME) < 60;
  return { wx: !!WX, wxErr: typeof WXERR !== 'undefined' ? WXERR : null, dayButtonWorks: dayOk, chipMatchesList: chip === top,
    tooFarListed: ranked.slice(0, 10).filter(x => tooFar(x.s)).map(x => x.s.name),
    homeTextLeak: home ? [] : ["Washougal", "Ridgefield", "Crown Point", "Sauvie"].filter(k => txt.includes(k)),
    spotsShown: document.querySelectorAll('#v-now [data-spot]').length, horizonPaths: HZN ? HZN.paths.length : 0 }; })()"""

async def main():
    rows, bad = [], []
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for name, loc, prefs, group, home in S:
            c = await br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, timezone_id="America/Los_Angeles")
            st = {"ss2:loc": {**loc, "src": "search", "at": 9e12}, "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 120, "maxWalk": 30, "start": "gps", **prefs}, "ss2:group": group, "ss2:welcomed": True}
            await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
            pg = await c.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
            await pg.goto(URL)
            first = await pg.evaluate("""new Promise(r => { const t0 = performance.now(); const iv = setInterval(() => { if (document.querySelector('#v-now [data-spot]')) { clearInterval(iv); r(Math.round(performance.now() - t0)); } }, 100); setTimeout(() => { clearInterval(iv); r(-1); }, 20000); })""")
            await pg.wait_for_timeout(6000)
            r = await pg.evaluate(CHECK); r["firstSpotMs"] = first; r["errors"] = errs[:3]
            fails = [k for k, ok in [("forecast didn't load", r["wx"]), ("day button", r["dayButtonWorks"]), ("time-button score != list", r["chipMatchesList"]),
                                     ("spot beyond travel limit", not r["tooFarListed"]), ("home text shown elsewhere", not r["homeTextLeak"]),
                                     ("no spots shown", r["spotsShown"] > 0), ("first spot slower than 15 s", 0 <= first < 15000), ("page errors", not errs)] if not ok]
            rows.append((name, fails, r)); bad += [f"{name}: {f}" for f in fails]
            await c.close(); await asyncio.sleep(10)
        await br.close()
    md = ["## ShotSpots nightly check", "", "| Scenario | Result | Details |", "|---|---|---|"]
    md += [f"| {n} | {'✅' if not f else '❌ ' + ', '.join(f)} | first spot {r['firstSpotMs']} ms; {r['spotsShown']} spots; wx err {r['wxErr']}; {r['tooFarListed'] or ''} {r['homeTextLeak'] or ''} {r['errors'] or ''} |" for n, f, r in rows]
    s = "\n".join(md); print(s)
    if os.environ.get("GITHUB_STEP_SUMMARY"): open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(s + "\n")
    sys.exit(1 if bad else 0)
asyncio.run(main())
