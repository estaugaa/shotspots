"""Why is 'Current weather unavailable'? Calls the Now-line Open-Meteo request directly, then loads the live app at
Washougal in a browser and records every api.open-meteo.com / workers.dev request, its status, and the now line."""
import asyncio, json, time, urllib.request, urllib.error
from playwright.async_api import async_playwright
U = ("https://api.open-meteo.com/v1/forecast?latitude=45.583&longitude=-122.353&current=precipitation,rain,showers,snowfall,"
     "weather_code,temperature_2m,cloud_cover,wind_speed_10m&minutely_15=precipitation&forecast_minutely_15=16&past_minutely_15=2"
     "&timeformat=unixtime&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=GMT")
out = []
for i in range(3):
    t = time.time()
    try:
        with urllib.request.urlopen(U, timeout=30) as r: b = r.read(); out.append(f"direct {r.status} {time.time()-t:.1f}s {b[:300]!r}")
    except urllib.error.HTTPError as e: out.append(f"direct HTTP {e.code} {time.time()-t:.1f}s {e.read()[:300]!r}")
    except Exception as e: out.append(f"direct ERR {time.time()-t:.1f}s {e}")
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(); c = await br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        await c.add_init_script('localStorage.setItem("ss2:loc", JSON.stringify({lat:45.583,lon:-122.353,label:"Washougal",src:"search",at:9e12}));localStorage.setItem("ss2:welcomed","true");')
        pg = await c.new_page(); t0 = time.time()
        pg.on("console", lambda m: out.append(f"console {m.type}: {m.text[:300]}") if m.type in ("error", "warning") else None)
        pg.on("requestfailed", lambda r: out.append(f"FAILED {r.url[:200]} {r.failure}"))
        async def resp(r):
            if "open-meteo" in r.url or "workers.dev" in r.url: out.append(f"{time.time()-t0:5.1f}s {r.status} {r.url[:230]}")
        pg.on("response", lambda r: asyncio.ensure_future(resp(r)))
        await pg.goto("https://estaugaa.github.io/shotspots/", wait_until="load"); await pg.wait_for_timeout(25000)
        out.append("NOWLINE: " + (await pg.evaluate("(document.querySelector('.nowline')||{}).innerText||'none'")))
        out.append("ERRS: " + json.dumps(await pg.evaluate("window.ERRS||window.__errs||null"))[:800])
        await br.close()
asyncio.run(main())
print("\n".join(out))
