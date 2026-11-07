"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite.
Loads the LIVE site in headless Chrome, clicks the day tabs, and prints page errors."""
import asyncio
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w, h, mob in [(1440, 900, False), (390, 844, True)]:
            c = await b.new_context(viewport={"width": w, "height": h}, is_mobile=mob, has_touch=mob, timezone_id="America/Los_Angeles")
            pg = await c.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:300]))
            pg.on("console", lambda m: errs.append("console." + m.type + " " + m.text[:200]) if m.type in ("error", "warning") else None)
            await pg.goto(URL); await pg.wait_for_timeout(9000)
            tabs = await pg.evaluate("[...document.querySelectorAll('[data-day]')].map(b=>b.dataset.day)")
            print(w, "tabs", tabs, "UI.day", await pg.evaluate("typeof UI!=='undefined' && UI.day"))
            for d in tabs[1:3]:
                el = await pg.query_selector(f"[data-day='{d}']"); bb = await el.bounding_box()
                at = await pg.evaluate(f"(()=>{{const e=document.elementFromPoint({bb['x']+bb['width']/2},{bb['y']+bb['height']/2});return e?e.tagName+'#'+e.id+'.'+e.className+(e.closest('[data-day]')?' IN-TAB':' NOT-TAB'):'none'}})()")
                if mob: await pg.tap(f"[data-day='{d}']")
                else: await pg.mouse.click(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2)
                await pg.wait_for_timeout(1200)
                print(w, "clicked", d, "top element:", at, "-> UI.day", await pg.evaluate("UI.day"), "selected", await pg.evaluate("document.querySelector('[data-day][aria-selected=true]')?.dataset.day"))
            print(w, "errors:", *errs[:15], sep="\n  ")
            await c.close()
        await b.close()
asyncio.run(main())
