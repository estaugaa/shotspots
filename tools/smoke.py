"""Smoke test after every publish: load the live app twice (the second load goes through the offline cache, like a
returning visitor), tap a day tab, and fail if the day doesn't change or the app throws its own errors."""
import asyncio, os
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
os.makedirs("ux", exist_ok=True)
async def main():
    out = []
    async with async_playwright() as p:
        for eng in ("webkit", "chromium"):
            b = await getattr(p, eng).launch(); dev = p.devices["iPhone 14"] if eng == "webkit" else {"viewport": {"width": 390, "height": 844}}
            c = await b.new_context(**dev, timezone_id="America/Los_Angeles", service_workers="allow")
            pg = await c.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:300]))
            pg.on("console", lambda m: errs.append("console." + m.type + " " + m.text[:200]) if m.type == "error" else None)
            await pg.goto(URL); await pg.wait_for_timeout(8000)
            for i in range(2):
                await pg.reload(); await pg.wait_for_timeout(8000)
                ctl = await pg.evaluate("!!(navigator.serviceWorker && navigator.serviceWorker.controller)")
                fdok = await pg.evaluate("typeof fd")
                tabs = await pg.evaluate("[...document.querySelectorAll('[data-day]')].map(b=>b.dataset.day)")
                await pg.tap(f"[data-day='{tabs[1]}']") if eng == "webkit" else await pg.click(f"[data-day='{tabs[1]}']")
                await pg.wait_for_timeout(1200)
                out.append(f"{eng} reload{i+1} controlled={ctl} typeof fd={fdok} after tap UI.day={await pg.evaluate('UI.day')} (want {tabs[1]})")
            scripts = await pg.evaluate("[...document.scripts].map(s=>s.src.split('/').pop()).join(' ')")
            out.append(f"{eng} scripts: {scripts}")
            out.append(f"{eng} errors: " + " | ".join(errs[:10]))
            await b.close()
    print("\n".join(out))
    bad = [l for l in out if "after tap" in l and l.split("UI.day=")[1].split(" ")[0] != l.split("want ")[1].rstrip(")")]
    own = [e for l in out if "errors:" in l for e in l.split(" | ") if "PAGEERROR" in e and "7timer" not in e and "access control" not in e]
    if bad or own:
        print("SMOKE FAILED:", bad, own); raise SystemExit(1)
asyncio.run(main())
