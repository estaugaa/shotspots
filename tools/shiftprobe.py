"""What appears above the first card while the page loads (Chromium, first visit), and which requests fail."""
import asyncio, json, os
from playwright.async_api import async_playwright
os.makedirs("ux", exist_ok=True)
SNAP = """(() => { const v = document.querySelector('#v-now'); const c = v && v.querySelector('[data-spot]'); const kids = v ? [...v.children].slice(0, 6).map(e => `${e.tagName}.${e.className} h${Math.round(e.getBoundingClientRect().height)}: ${e.innerText.replace(/\\s+/g, ' ').slice(0, 90)}`) : [];
  return { t: Math.round(performance.now()), first: c ? c.dataset.spot + '@' + Math.round(c.getBoundingClientRect().top) : null, wx: !!window.WX, kids }; })()"""
async def main():
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch(); c = await b.new_context(viewport={"width": 390, "height": 844}, timezone_id="America/Los_Angeles"); pg = await c.new_page()
        pg.on("requestfailed", lambda r: out.append(f"REQFAIL {r.url[:120]} {r.failure}"))
        pg.on("response", lambda r: out.append(f"RESP {r.status} {r.url[:100]}") if ("open-meteo" in r.url or "workers.dev" in r.url) else None)
        await pg.goto("https://estaugaa.github.io/shotspots/")
        for ms in (300, 300, 400, 500, 1000, 1500, 2000, 3000):
            await pg.wait_for_timeout(ms); out.append(json.dumps(await pg.evaluate(SNAP)))
        await b.close()
    open("ux/shift.txt", "w").write("\n".join(out))
asyncio.run(main())
