"""Smoke test after every publish: load the live app twice (the second load goes through the offline cache, like a
returning visitor), tap a day tab, and fail if the day doesn't change or the app throws its own errors.
Also watches the first 10 seconds of each load and fails if the page jumps around while data arrives: the first
card on screen changing or moving, the page growing under the reader, and (Chromium only) layout-shift score."""
import asyncio, os
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
os.makedirs("ux", exist_ok=True)
MAX_JUMPS, MAX_CLS = 3, 0.1
# Records, every 100 ms from first paint, which card sits at the top of the screen and where.
WATCH = """(() => { const J = window.__jumps = { n: 0, log: [], cls: 0, t0: performance.now() }; let last = null;
  try { new PerformanceObserver(l => l.getEntries().forEach(e => { if (!e.hadRecentInput) J.cls += e.value; })).observe({ type: "layout-shift", buffered: true }); } catch (e) { J.cls = null; }
  const tick = () => { const t = performance.now() - J.t0; if (t > 10000) return;
    const c = [...document.querySelectorAll(".view:not([hidden]) [data-spot]")].find(e => { const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight; });
    if (c) { const cur = { id: c.dataset.spot, y: Math.round(c.getBoundingClientRect().top) };
      if (last && (cur.id !== last.id || Math.abs(cur.y - last.y) > 8)) { J.n++; J.log.push(`${(t / 1000).toFixed(1)}s ${last.id}@${last.y} -> ${cur.id}@${cur.y}`); }
      last = cur; }
    setTimeout(tick, 100); };
  addEventListener("DOMContentLoaded", tick); })()"""
async def main():
    out = []
    async with async_playwright() as p:
        for eng in ("webkit", "chromium"):
            b = await getattr(p, eng).launch(); dev = p.devices["iPhone 14"] if eng == "webkit" else {"viewport": {"width": 390, "height": 844}}
            c = await b.new_context(**dev, timezone_id="America/Los_Angeles", service_workers="allow")
            await c.add_init_script(WATCH)
            pg = await c.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:300]))
            pg.on("console", lambda m: errs.append("console." + m.type + " " + m.text[:200]) if m.type == "error" else None)
            pg.on("response", lambda r: errs.append(f"HTTP {r.status} {r.url.split('?')[0][:120]}") if r.status >= 400 else None)   # which server said 429 (Nov 23: unnamed)
            await pg.goto(URL); await pg.wait_for_timeout(10500)
            j = await pg.evaluate("window.__jumps"); out.append(f"{eng} first load: jumps={j['n']} cls={j['cls']} paints={await pg.evaluate('window.__paints')} {' ; '.join(j['log'][:6])}")
            for i in range(2):
                await pg.reload(); await pg.wait_for_timeout(10500)
                j = await pg.evaluate("window.__jumps"); out.append(f"{eng} reload{i+1} load: jumps={j['n']} cls={j['cls']} paints={await pg.evaluate('window.__paints')} {' ; '.join(j['log'][:6])}")
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
    def jumpy(l):
        n = int(l.split("jumps=")[1].split()[0]); c = l.split("cls=")[1].split()[0]
        return n > MAX_JUMPS or (c not in ("None", "null") and float(c) > MAX_CLS)
    shaky = [l for l in out if " load: jumps=" in l and jumpy(l)]
    if bad or own or shaky:
        print("SMOKE FAILED:", bad, own, shaky); raise SystemExit(1)
asyncio.run(main())
