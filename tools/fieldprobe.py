"""Field toolkit checks: sun & moon at odd places, notes, exports, map layers. ux/field.txt + ux/field_*.png"""
import asyncio, json, os
from playwright.async_api import async_playwright
os.makedirs("ux", exist_ok=True); O = []
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles")
        await c.add_init_script('if(!sessionStorage.getItem("i")){localStorage.setItem("ss2:welcomed","true");localStorage.setItem("ss2:loc",JSON.stringify({lat:45.582,lon:-122.353,label:"Washougal",src:"search",at:9e12}));localStorage.setItem("ss2:saved",JSON.stringify({"vista-house":1,"multnomah":1}));sessionStorage.setItem("i","1")}')
        pg = await c.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto("https://estaugaa.github.io/shotspots/"); await pg.wait_for_timeout(8000)
        for name, lat, lon in [("Utqiagvik AK", 71.29, -156.79), ("Honolulu HI", 21.31, -157.86), ("Fairbanks AK", 64.84, -147.72)]:
            r = await pg.evaluate(f"""(()=>{{ const keep={{...LOC}}; LOC.lat={lat}; LOC.lon={lon}; TZ=tzFor(LOC); UI.day=null;
                const h=sunMoonHtml({{id:"x",name:"{name}",lat:{lat},lon:{lon},cats:[]}}); const tz=TZ; LOC.lat=keep.lat; LOC.lon=keep.lon; TZ=tzFor(LOC);
                const d=document.createElement('div'); d.innerHTML=h; return tz+' | '+d.innerText.replace(/\\s+/g,' ').slice(0,700); }})()""")
            O.append(f"{name}: {r}")
        await pg.evaluate("openSpot('vista-house')"); await pg.wait_for_timeout(5000)
        O.append("sections: " + json.dumps(await pg.evaluate("[...document.querySelectorAll('#sheetBody h3')].map(h=>h.textContent.trim().slice(0,28))")))
        sm = await pg.evaluate("(()=>{const x=document.querySelector('.sunmoon');x&&x.scrollIntoView();return x?x.innerText.replace(/\\s+/g,' ').slice(0,900):'NO SUN&MOON'})()"); O.append("vista sun&moon: " + sm)
        await pg.screenshot(path="ux/field_sunmoon.png")
        await pg.fill("#noteBox", "Park at the upper lot; gate opens 9 AM."); await pg.wait_for_timeout(900)
        O.append("note stored: " + await pg.evaluate("localStorage.getItem('ss2:notes')"))
        O.append("copy button: " + str(await pg.locator("[data-copyll]").count()))
        await pg.keyboard.press("Escape"); await pg.evaluate("document.querySelector('.tabs button[data-v=\"spots\"]')?.click()"); await pg.wait_for_timeout(2500)
        O.append("export box: " + str(await pg.locator("#exportBox").count()))
        await pg.evaluate("window.__dl=[]; download=function(n,t){ window.__dl.push([n, String(t)]); }")
        await pg.evaluate("exportSaved('gpx'); exportSaved('kml')")
        dl = await pg.evaluate("window.__dl")
        O.append(f'downloads captured: {len(dl)} {[ (x[0], type(x[1]).__name__) for x in dl]}')
        for n, t in dl:
            t = t or ''
            ok = await pg.evaluate("t=>{const d=new DOMParser().parseFromString(t,'application/xml');return !d.querySelector('parsererror')}", t)
            O.append(f"{n}: valid xml={ok}, waypoints={t.count('<wpt')+t.count('<Placemark')}, has note={'upper lot' in t} :: {t[:260]!r}")
        await pg.evaluate("document.querySelector('.tabs button[data-v=\"map\"]')?.click()"); await pg.wait_for_timeout(3000)
        O.append("layer control: " + str(await pg.locator(".leaflet-control-layers").count()))
        await pg.reload(); await pg.wait_for_timeout(6000); await pg.evaluate("openSpot('vista-house')"); await pg.wait_for_timeout(3000)
        O.append("note after reload: " + await pg.evaluate("(document.querySelector('#noteBox')||{}).value||''"))
        O.append("errors: " + json.dumps(errs[:5])); await b.close()
    open("ux/field.txt", "w").write("\n".join(O))
try: asyncio.run(main())
except Exception as e:
    O.append("PROBE CRASH: " + str(e)[:300]); open("ux/field.txt", "w").write("\n".join(O))
