"""Evaluate a JS expression in the live app (Washougal), e.g. python tools/evalprobe.py "1+1". Output ux/eval.txt"""
import asyncio, json, os, sys
from playwright.async_api import async_playwright
os.makedirs("ux", exist_ok=True)
EXPR = " ".join(sys.argv[1:]) or "document.title"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles")
        await c.add_init_script('localStorage.setItem("ss2:welcomed","true");localStorage.setItem("ss2:loc",JSON.stringify({lat:45.582,lon:-122.353,label:"Washougal",src:"search",at:9e12}))')
        pg = await c.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto("https://estaugaa.github.io/shotspots/"); await pg.wait_for_timeout(10000)
        try: r = await pg.evaluate(EXPR)
        except Exception as e: r = "EVAL ERROR: " + str(e)[:300]
        open("ux/eval.txt", "w").write(json.dumps(r, default=str, indent=1)[:20000] + "\nerrors: " + json.dumps(errs[:5]))
        await b.close()
asyncio.run(main())
