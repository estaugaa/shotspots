import asyncio, json, os
from playwright.async_api import async_playwright
os.makedirs("ux", exist_ok=True); O = []
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        await c.add_init_script('localStorage.setItem("ss2:welcomed","true");localStorage.setItem("ss2:loc",JSON.stringify({lat:45.582,lon:-122.353,label:"Washougal",src:"search",at:9e12}))')
        pg = await c.new_page(); errs = []; res = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:300])); pg.on("console", lambda m: m.type == "error" and errs.append("console: " + m.text[:200]))
        pg.on("response", lambda r: r.url.endswith(".js") and res.append(f"{r.status} {r.url.split('/')[-1]}"))
        await pg.goto("https://estaugaa.github.io/shotspots/"); await pg.wait_for_timeout(8000)
        O.append("typeof isOwner: " + await pg.evaluate("typeof isOwner"))
        O.append("typeof researchHtml: " + await pg.evaluate("typeof researchHtml"))
        O.append("scripts: " + " ".join(res))
        O.append("errors: " + json.dumps(errs[:8]))
        await b.close()
    open("ux/js.txt", "w").write("\n".join(O))
asyncio.run(main())
