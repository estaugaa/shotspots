"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite. Real-life scenario walkthroughs with automatic checks."""
import asyncio, os, json
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
os.makedirs("ux", exist_ok=True)
# name, location, prefs, filter group, (day, window kind), extra actions
S = [
 ("1 Owner Washougal: switch to Wednesday, check sunrise", {"lat": 45.582, "lon": -122.353, "label": "Washougal"}, {"maxDrive": 60}, "all", ("wed", "sunrise"), ["nighttab"]),
 ("2 Hood River fog morning, drive 45", {"lat": 45.709, "lon": -121.521, "label": "Hood River"}, {"maxDrive": 45}, "all", ("tomorrow", "sunrise"), []),
 ("3 Portland walker: blue hour city, walk 20", {"lat": 45.523, "lon": -122.676, "label": "Pearl District"}, {"travel": "walk", "maxWalk": 20}, "city", ("today", "bluePM"), []),
 ("4 Ashford (Rainier) sunrise, drive 60", {"lat": 46.759, "lon": -122.031, "label": "Ashford"}, {"maxDrive": 60}, "land", ("tomorrow", "sunrise"), []),
 ("5 Olympic coast (Forks) sunset, drive 45", {"lat": 47.95, "lon": -124.385, "label": "Forks"}, {"maxDrive": 45}, "all", ("tomorrow", "sunset"), []),
 ("6 Spokane sunset, drive 60", {"lat": 47.659, "lon": -117.426, "label": "Spokane"}, {"maxDrive": 60}, "all", ("tomorrow", "sunset"), []),
 ("7 Boise stargazer, drive 90", {"lat": 43.615, "lon": -116.202, "label": "Boise"}, {"maxDrive": 90}, "night", ("today", "night"), ["nighttab"]),
 ("8 Jackson WY wildlife morning, drive 60", {"lat": 43.48, "lon": -110.762, "label": "Jackson"}, {"maxDrive": 60}, "life", ("tomorrow", "morning"), []),
 ("9 Sedona sunset, drive 45", {"lat": 34.87, "lon": -111.761, "label": "Sedona"}, {"maxDrive": 45}, "all", ("tomorrow", "sunset"), []),
 ("10 Bend waterfalls, drive 60", {"lat": 44.058, "lon": -121.315, "label": "Bend"}, {"maxDrive": 60}, "water", ("tomorrow", "morning"), []),
]
PICK = """(([day, kind]) => { const all = allWindows(LOC, PLAN_HOURS); const t0 = Date.now();
  const want = day === "today" ? laYMD(new Date()) : day === "tomorrow" ? laYMD(new Date(t0 + 864e5)) : laYMD(new Date(t0 + 2 * 864e5));
  // tap the day button like a person would, then the window chip
  const db = [...document.querySelectorAll('[data-day]')].find(b => b.dataset.day === want); if (db) db.click();
  const i = all.findIndex(w => winDay(w) === want && w.kind === kind);
  if (i >= 0) { UI.focus = i; UI.day = want; render(); } return i >= 0 ? wTitle(all[i]) + " " + fmtT(all[i].peak) : "no window " + kind; })"""
CHECKS = """(() => { const all = allWindows(LOC, PLAN_HOURS), w = all[UI.focus], ranked = rankFor(w), tops = windowTops(all);
  const chip = tops[UI.focus] ? tops[UI.focus].f.n : null, top = ranked[0] ? ranked[0].f.n : null;
  const far = ranked.slice(0, 10).filter(x => tooFar(x.s)).map(x => x.s.name);
  const txt = document.querySelector('#v-now').innerText, home = km(LOC, HOME) < 60;
  const leak = home ? [] : ["Gorge", "Washougal", "Ridgefield", "Crown Point", "Sauvie", "Columbia"].filter(k => txt.includes(k));
  const scores = ranked.slice(0, 10).map(x => x.f.n), spread = scores.length ? Math.max(...scores) - Math.min(...scores) : 0;
  return { wx: !!WX, wxErr: WX && WX.err || (typeof WXERR !== 'undefined' ? WXERR : null), wxPts: WX ? WX.pts.length : 0, hz: HZN ? HZN.paths.length : 0, chip, top, chipMatches: chip === top,
           tooFarListed: far, leak, alertline: !!document.querySelector('.alertline'), spots: SPOTS.length, ranked: ranked.length, top10spread: spread,
           seeing: typeof SEVEN !== 'undefined' && SEVEN ? (SEVEN.err || SEVEN.note || 'ok') : 'n/a' }; })()"""
async def main():
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, loc, prefs, group, (day, kind), extra in S:
            c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, timezone_id="America/Los_Angeles",
                                    geolocation={"latitude": loc["lat"], "longitude": loc["lon"]}, permissions=["geolocation"])
            st = {"ss2:loc": {**loc, "src": "search", "at": 9e12}, "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 120, "maxWalk": 30, "start": "gps", **prefs}, "ss2:group": group, "ss2:welcomed": True}
            await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
            pg = await c.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
            await pg.goto(URL)
            first = await pg.evaluate("""new Promise(r => { const t0 = performance.now(); const iv = setInterval(() => { if (document.querySelector('#v-now [data-spot]')) { clearInterval(iv); r(Math.round(performance.now() - t0)); } }, 100); setTimeout(() => { clearInterval(iv); r(-1); }, 25000); })""")
            await pg.wait_for_timeout(10000)
            win = await pg.evaluate(PICK, [day, kind]); await pg.wait_for_timeout(3000)
            chk = await pg.evaluate(CHECKS)
            await pg.screenshot(path=f"ux/t{name.split()[0]}_now.png")
            txt = await pg.evaluate("document.querySelector('#v-now')?.innerText || ''")
            out.append(f"\n######## {name}\nfirst spot {first} ms | window={win} | errors={errs[:3]}\nCHECKS {json.dumps(chk)}\n" + txt[:2600])
            if "nighttab" in extra:
                await pg.evaluate("show('sky')")
                await pg.wait_for_timeout(4000)
                out.append("--- night sky tab:\n" + (await pg.evaluate("document.querySelector('#v-sky').innerText"))[:1800]); await pg.evaluate("show('now')")
            tops = await pg.evaluate("[...document.querySelectorAll('#v-now .picks [data-spot]')].slice(0, 2).map(a => a.dataset.spot)")
            for k, sid in enumerate(tops):
                await pg.evaluate(f"openSpot({json.dumps(sid)})"); await pg.wait_for_timeout(5000)
                if k == 0: await pg.screenshot(path=f"ux/t{name.split()[0]}_spot.png")
                body = await pg.evaluate("document.querySelector('#sheetBody')?.innerText || ''")
                secs = [h for h in ["Tides", "River now", "Weather alerts here", "Getting there", "Rain, past 48 h", "Night sky here", "Best photos here", "Seen here"] if h in body]
                out.append(f"--- spot #{k+1} page ({sid}) sections={secs}:\n" + body[:1800])
            await c.close()
            await asyncio.sleep(12)   # space runs so one runner IP doesn't get rate-limited
        await b.close()
    open("ux/scenarios.txt", "w").write("\n".join(out))
asyncio.run(main())
