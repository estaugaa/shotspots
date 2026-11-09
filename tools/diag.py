"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite. Live day-tab check."""
import asyncio, os
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
os.makedirs("ux", exist_ok=True)
async def main():
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w, h, mob in [(390, 844, True), (1440, 900, False)]:
            c = await b.new_context(viewport={"width": w, "height": h}, is_mobile=mob, has_touch=mob, timezone_id="America/Los_Angeles")
            pg = await c.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:400]))
            await pg.goto(URL); await pg.wait_for_timeout(9000)
            tabs = await pg.evaluate("[...document.querySelectorAll('[data-day]')].map(b=>b.dataset.day)")
            out.append(f"{w} tabs {tabs} UI.day={await pg.evaluate('UI.day')} focus={await pg.evaluate('UI.focus')}")
            for d in tabs[1:3]:
                el = await pg.query_selector(f"[data-day='{d}']"); bb = await el.bounding_box()
                at = await pg.evaluate(f"(()=>{{const e=document.elementFromPoint({bb['x']+bb['width']/2},{bb['y']+bb['height']/2});return e?e.tagName+'#'+e.id+'.'+e.className+(e.closest('[data-day]')?' IN-TAB':' NOT-TAB'):'none'}})()")
                if mob: await pg.tap(f"[data-day='{d}']")
                else: await pg.mouse.click(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2)
                await pg.wait_for_timeout(1500)
                out.append(f"{w} click {d} at={at} -> UI.day={await pg.evaluate('UI.day')} sel={await pg.evaluate('document.querySelector(\"[data-day][aria-selected=true]\")?.dataset.day')} focus={await pg.evaluate('UI.focus')}")
            await pg.screenshot(path=f"ux/day_{w}.png")
            out.append(f"{w} errors: " + " | ".join(errs[:6]))
            await c.close()
        await b.close()
    open("ux/days.txt", "w").write("\n".join(out)); print("\n".join(out))
asyncio.run(main())
