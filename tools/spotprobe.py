"""Open given spots on the live app and dump their 'Where to stand' section. ux/spot.txt + ux/spot_<id>.png"""
import asyncio, json, os, sys
from playwright.async_api import async_playwright
os.makedirs("ux", exist_ok=True); OUT = []
IDS = sys.argv[1:] or ["vista-house", "multnomah", "womens-forum"]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles")
        st = {"ss2:loc": {"lat": 45.582, "lon": -122.353, "label": "Washougal", "src": "search", "at": 9e12}, "ss2:welcomed": True}
        await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
        pg = await c.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto("https://estaugaa.github.io/shotspots/"); await pg.wait_for_timeout(9000)
        for i in IDS:
            await pg.evaluate(f"openSpot({json.dumps(i)})"); await pg.wait_for_timeout(4000)
            t = await pg.evaluate("(()=>{const b=document.querySelector('#sheetBody');const h=[...b.querySelectorAll('h3')].find(x=>/Where to stand/.test(x.textContent));if(!h)return 'NO SECTION';let s=h.textContent,n=h.nextElementSibling;while(n&&n.tagName!=='H3'){s+=' | '+n.innerText;n=n.nextElementSibling}h.scrollIntoView();return s})()")
            OUT.append(f"{i}: {t}"); await pg.screenshot(path=f"ux/spot_{i}.png"); await pg.keyboard.press("Escape"); await pg.wait_for_timeout(500)
        OUT.append(f"errors: {errs[:4]}"); await b.close()
    open("ux/spot.txt", "w").write("\n".join(OUT))
asyncio.run(main())
