"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite. Live day-tab check."""
import asyncio, os
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
os.makedirs("ux", exist_ok=True)
async def main():
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        STATES = {
          "owner": {"ss2:ownerKey": "x", "ss2:welcomed": True},
          "owner+home+night": {"ss2:ownerKey": "x", "ss2:welcomed": True, "ss2:group": "night", "ss2:prefs": {"start": "home", "travel": "drive", "maxDrive": 120, "units": "us"}},
          "life+walk": {"ss2:group": "life", "ss2:prefs": {"travel": "walk", "maxWalk": 30}},
          "sky+60": {"ss2:group": "sky", "ss2:prefs": {"maxDrive": 60}},
          "saved-loc": {"ss2:loc": {"lat": 45.582, "lon": -122.353, "label": "Washougal (home)", "src": "home", "at": 0}, "ss2:ownerKey": "x"},
        }
        import json as _j
        for name, st in STATES.items():
            w, h, mob = 390, 844, True
            c = await b.new_context(viewport={"width": w, "height": h}, is_mobile=mob, has_touch=mob, timezone_id="America/Los_Angeles")
            await c.add_init_script("".join(f"localStorage.setItem({_j.dumps(k)}, {_j.dumps(_j.dumps(v))});" for k, v in st.items()))
            out.append("== " + name)
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
            await pg.screenshot(path=f"ux/day_{name}.png")
            out.append(f"{w} errors: " + " | ".join(errs[:6]))
            await c.close()
        await b.close()
    open("ux/days.txt", "w").write("\n".join(out)); print("\n".join(out))
asyncio.run(main())
