"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite.
UX review: phone-size screenshots of the live site plus all visible text."""
import asyncio, os
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
os.makedirs("ux", exist_ok=True)
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        c = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True, timezone_id="America/Los_Angeles",
                                geolocation={"latitude": 45.582, "longitude": -122.353}, permissions=["geolocation"])
        pg = await c.new_page()
        await pg.goto(URL); await pg.wait_for_timeout(10000)
        async def snap(name):
            await pg.screenshot(path=f"ux/{name}.png", full_page=True)
            t = await pg.evaluate("document.querySelector('#main')?.innerText || document.body.innerText")
            open(f"ux/{name}.txt", "w").write(t)
        await snap("1_plan")
        await pg.evaluate("UI.planView='night'; typeof show==='function' && show('now')")
        for seg in ("night", "calendar"):
            el = await pg.query_selector(f"[data-pv='{seg}'], [data-planview='{seg}'], [data-seg='{seg}']")
            if el: await el.tap(); await pg.wait_for_timeout(1500); await snap(f"2_plan_{seg}")
        await pg.evaluate("show('spots')"); await pg.wait_for_timeout(1500); await snap("3_spots")
        await pg.evaluate("openSpot('ridgefield')"); await pg.wait_for_timeout(4000)
        await pg.screenshot(path="ux/4_spot.png")
        open("ux/4_spot.txt", "w").write(await pg.evaluate("document.querySelector('#sheetBody')?.innerText || ''"))
        await pg.evaluate("openSpot('vista-house')"); await pg.wait_for_timeout(3000)
        open("ux/5_spot_vista.txt", "w").write(await pg.evaluate("document.querySelector('#sheetBody')?.innerText || ''"))
        await b.close()
asyncio.run(main())
