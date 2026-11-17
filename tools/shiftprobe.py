"""Which elements cause layout shift while the page loads (Chromium; first load and a reload)."""
import asyncio, json, os
from playwright.async_api import async_playwright
os.makedirs("ux", exist_ok=True)
INIT = """window.__ls = []; new PerformanceObserver(l => l.getEntries().forEach(e => { if (e.hadRecentInput) return;
  window.__ls.push({ t: Math.round(e.startTime), v: +e.value.toFixed(4), src: (e.sources || []).map(s => { const n = s.node; const el = n && (n.nodeType === 1 ? n : n.parentElement);
    return el ? `${el.tagName}.${(el.className || '').toString().slice(0, 40)}#${el.id} "${(el.innerText || '').replace(/\\s+/g, ' ').slice(0, 60)}" ${Math.round(s.previousRect.y)}->${Math.round(s.currentRect.y)} h${Math.round(s.previousRect.height)}->${Math.round(s.currentRect.height)}` : '?'; }) }); })).observe({ type: 'layout-shift', buffered: true });"""
async def main():
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch(); c = await b.new_context(viewport={"width": 390, "height": 844}, timezone_id="America/Los_Angeles", service_workers="allow")
        await c.add_init_script(INIT); pg = await c.new_page()
        for label in ("first", "reload"):
            if label == "first": await pg.goto("https://estaugaa.github.io/shotspots/")
            else: await pg.reload()
            await pg.wait_for_timeout(10500)
            out.append(label + " " + json.dumps(await pg.evaluate("window.__ls"), indent=0))
        await b.close()
    open("ux/shift.txt", "w").write("\n".join(out))
asyncio.run(main())
