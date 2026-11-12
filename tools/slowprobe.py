"""Why is a location slow to show its first spot? Logs pending requests and page state at intervals. ux/slow.txt"""
import asyncio, json, os, time, sys
from playwright.async_api import async_playwright
os.makedirs("ux", exist_ok=True); OUT = []
LOC = {"lat": 39.739, "lon": -104.99, "label": "Denver"}
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for rep in range(2):
            c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles")
            st = {"ss2:loc": {**LOC, "src": "search", "at": 9e12}, "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 90, "maxWalk": 30, "start": "gps"}, "ss2:group": "all", "ss2:welcomed": True}
            await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
            pg = await c.new_page(); t0 = time.time(); pend = {}; done = []
            pg.on("request", lambda r: pend.__setitem__(r.url, time.time()))
            def fin(r):
                t = pend.pop(r.url, None)
                if t: done.append((round(time.time() - t0, 1), round(time.time() - t, 1), r.url[:110]))
            pg.on("requestfinished", fin); pg.on("requestfailed", fin)
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200])); pg.on("console", lambda m: m.type in ("error", "warning") and errs.append(m.text[:200]))
            await pg.goto("https://estaugaa.github.io/shotspots/")
            for k in range(12):
                await pg.wait_for_timeout(2500)
                s = await pg.evaluate("(()=>({spots:document.querySelectorAll('#v-now [data-spot]').length, txt:(document.querySelector('#v-now')||{}).innerText?.slice(0,160), seedN: SPOTS.filter(x=>x.seed).length, wx: !!(typeof WX!=='undefined'&&WX)}))()")
                OUT.append(f"rep{rep} t={round(time.time()-t0,1)}s spots={s['spots']} seed={s['seedN']} wx={s['wx']} pending={[u[:90] for u in pend][:6]} | {s['txt']!r}")
                if s["spots"]: break
            OUT.append(f"rep{rep} slowest requests: " + json.dumps(sorted(done, key=lambda x: -x[1])[:10]))
            OUT.append(f"rep{rep} errors: {errs[:6]}")
            await c.close()
        await b.close()
    open("ux/slow.txt", "w").write("\n".join(OUT))
asyncio.run(main())
