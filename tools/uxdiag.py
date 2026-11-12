"""UI/UX walkthroughs on Actions (workflow 'Diagnostic', script=tools/uxdiag.py). Writes ux/ux.txt + screenshots."""
import asyncio, os, json, time
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
os.makedirs("ux", exist_ok=True)
HOME = {"lat": 45.582, "lon": -122.353, "label": "Washougal"}
OUT = []
def log(*a): OUT.append(" ".join(str(x) for x in a))

# generic page audit: overflow, small tap targets, tiny text, clipped text, contrast-ish, dom size
AUDIT = """((sel) => { const root = document.querySelector(sel) || document.body, W = document.documentElement.clientWidth;
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !e.closest('[hidden]'); };
  const name = e => (e.getAttribute('aria-label') || e.innerText || e.title || e.className || e.tagName).toString().trim().replace(/\\s+/g, ' ').slice(0, 40);
  const els = [...root.querySelectorAll('*')].filter(vis);
  const over = els.filter(e => { const r = e.getBoundingClientRect(); return r.right > W + 2 && !e.closest('.winchips,.chips,.daybar,[style*=overflow],.scroller') && getComputedStyle(e.parentElement).overflowX === 'visible'; }).slice(0, 8).map(name);
  const taps = [...root.querySelectorAll('button,a,[role=button],input,select,summary,[data-spot]')].filter(vis);
  const small = taps.filter(e => { const r = e.getBoundingClientRect(); return r.height < 32 || r.width < 32; }).map(e => { const r = e.getBoundingClientRect(); return name(e) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height); });
  const unnamed = taps.filter(e => !(e.getAttribute('aria-label') || e.innerText.trim() || e.title || e.getAttribute('placeholder'))).map(e => e.outerHTML.slice(0, 60));
  const texts = els.filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1));
  const tiny = texts.filter(e => parseFloat(getComputedStyle(e).fontSize) < 12).map(e => name(e) + ' ' + getComputedStyle(e).fontSize);
  const clip = texts.filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).textOverflow !== 'ellipsis' && getComputedStyle(e).overflow !== 'visible').slice(0, 6).map(name);
  const lum = c => { const m = c.match(/[\\d.]+/g); if (!m) return null; const [r, g, b] = m.slice(0, 3).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return { L: .2126 * r + .7152 * g + .0722 * b, a: m[3] == null ? 1 : +m[3] }; };
  const bgOf = e => { for (let x = e; x; x = x.parentElement) { const l = lum(getComputedStyle(x).backgroundColor); if (l && l.a > .5) return l.L; } return 1; };
  const lowc = texts.map(e => { const f = lum(getComputedStyle(e).color); if (!f) return null; const b = bgOf(e), cr = (Math.max(f.L, b) + .05) / (Math.min(f.L, b) + .05); return cr < 4.5 ? name(e) + ' ' + cr.toFixed(1) : null; }).filter(Boolean);
  return { W, scrollW: document.documentElement.scrollWidth, height: Math.round(root.scrollHeight), domNodes: root.querySelectorAll('*').length, words: (root.innerText || '').split(/\\s+/).length,
    taps: taps.length, smallTaps: small.length, smallEx: small.slice(0, 10), unnamed: unnamed.slice(0, 5), tinyText: tiny.length, tinyEx: [...new Set(tiny)].slice(0, 8),
    lowContrast: lowc.length, lowEx: [...new Set(lowc)].slice(0, 8), overflow: over, clipped: clip }; })"""
READY = """new Promise(r => { const t0 = performance.now(); const iv = setInterval(() => { if (document.querySelector('#v-now [data-spot]')) { clearInterval(iv); r(Math.round(performance.now() - t0)); } }, 100); setTimeout(() => { clearInterval(iv); r(-1); }, 30000); })"""

async def ctx(b, w=390, h=844, mobile=True, loc=HOME, prefs=None, fresh=False, scheme="light", motion="no-preference"):
    c = await b.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile, timezone_id="America/Los_Angeles", color_scheme=scheme, reduced_motion=motion,
                            geolocation={"latitude": loc["lat"], "longitude": loc["lon"]}, permissions=["geolocation"], device_scale_factor=1)
    if not fresh:
        st = {"ss2:loc": {**loc, "src": "search", "at": 9e12}, "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 60, "maxWalk": 30, "start": "gps", **(prefs or {})}, "ss2:group": "all", "ss2:welcomed": True}
        await c.add_init_script("if(!sessionStorage.getItem('uxinit')){" + "".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()) + "sessionStorage.setItem('uxinit','1')}")
    pg = await c.new_page(); pg.errs = []
    pg.on("pageerror", lambda e: pg.errs.append(str(e)[:160]))
    pg.on("response", lambda r: (r.status >= 400 or "nominatim" in r.url) and pg.errs.append(f"{r.status} {r.url[:150]}"))
    return c, pg

async def audit(pg, sel, tag):
    a = await pg.evaluate(AUDIT, sel); log(f"  AUDIT {tag}: {json.dumps(a)}"); return a

async def shot(pg, n, full=False):
    try: await pg.screenshot(path=f"ux/{n}.png", full_page=full, animations="disabled", timeout=60000)
    except Exception as e: log("  (screenshot", n, "failed)")

async def t1(b):  # brand-new user, no saved state
    c, pg = await ctx(b, fresh=True); t0 = time.time(); await pg.goto(URL)
    await pg.wait_for_timeout(2500); await shot(pg, "u1a_firstopen")
    log("  first screen text:", (await pg.evaluate("document.body.innerText"))[:700].replace("\n", " | "))
    ready = await pg.evaluate(READY); log("  first spot visible after", ready, "ms (+2.5s)")
    await pg.wait_for_timeout(6000); await shot(pg, "u1b_settled"); await audit(pg, "#v-now", "plan view first run")
    log("  above-the-fold text:", (await pg.evaluate("document.querySelector('#v-now').innerText"))[:900].replace("\n", " | "))
    return c, pg

async def t2(b):  # smallest phone
    c, pg = await ctx(b, 320, 568); await pg.goto(URL); log("  ready", await pg.evaluate(READY), "ms"); await pg.wait_for_timeout(8000)
    await shot(pg, "u2_se320"); await audit(pg, "body", "320px plan")
    await pg.evaluate("openSpot(document.querySelector('#v-now .picks [data-spot]').dataset.spot)"); await pg.wait_for_timeout(9000)
    await shot(pg, "u2_se320_spot"); await audit(pg, "#sheet", "320px spot sheet"); return c, pg

async def t3(b):  # spot page: open, scroll, back button closes, reopen
    c, pg = await ctx(b); await pg.goto(URL); await pg.evaluate(READY); await pg.wait_for_timeout(8000)
    el = pg.locator("#v-now .picks [data-spot]").first; await el.tap(); t0 = time.time()
    await pg.wait_for_selector("#sheet:not([hidden])", timeout=5000); log("  sheet opened in", round((time.time() - t0) * 1000), "ms")
    await pg.wait_for_timeout(9000); a = await audit(pg, "#sheet", "spot sheet")
    body = await pg.evaluate("document.querySelector('#sheetBody').innerText"); hs = await pg.evaluate("[...document.querySelectorAll('#sheetBody h2,#sheetBody h3,#sheetBody summary')].map(h=>h.innerText.trim().slice(0,30))")
    log("  sheet sections in order:", hs); log("  sheet words:", len(body.split()), "| first 600:", body[:600].replace("\n", " | "))
    await shot(pg, "u3_spot_top"); await pg.evaluate("document.querySelector('#sheetBody').scrollTop=99999"); await pg.wait_for_timeout(500); await shot(pg, "u3_spot_bottom")
    await pg.go_back(); await pg.wait_for_timeout(800); log("  after Back: sheet hidden =", await pg.evaluate("document.querySelector('#sheet').hidden"), "| url", pg.url)
    await pg.keyboard.press("Escape"); return c, pg

async def t4(b):  # change location via search
    c, pg = await ctx(b); await pg.goto(URL); await pg.evaluate(READY); await pg.wait_for_timeout(5000)
    await pg.tap("#locBtn"); await pg.wait_for_timeout(600); await shot(pg, "u4a_locsheet"); await audit(pg, "#locSheet", "location sheet")
    await pg.fill("#locQ", "Bend, OR"); await pg.press("#locQ", "Enter"); await pg.wait_for_timeout(3500)
    hits = await pg.evaluate("[...document.querySelectorAll('#locHits button,#locHits a')].map(x=>x.innerText.trim().slice(0,50))"); log("  hits:", hits[:5], "| message:", await pg.evaluate("document.querySelector('#locMsg').textContent"))
    t0 = time.time()
    if hits: await pg.locator("#locHits button, #locHits a").first.tap()
    await pg.wait_for_timeout(500); log("  loc sheet closed =", await pg.evaluate("document.querySelector('#locSheet').hidden"), "| header:", await pg.evaluate("document.querySelector('#locName').innerText"))
    ok = await pg.evaluate("""new Promise(r=>{const t=performance.now();const iv=setInterval(()=>{const tx=document.querySelector('#v-now').innerText;if(/Smith Rock|Pilot Butte|Bend|Deschutes|Sparks|Tumalo/.test(tx)){clearInterval(iv);r(Math.round(performance.now()-t))}},100);setTimeout(()=>{clearInterval(iv);r(-1)},30000)})""")
    log("  Bend results showed after", ok, "ms"); await pg.wait_for_timeout(3000); await shot(pg, "u4b_bend")
    log("  loading states seen:", await pg.evaluate("[...document.querySelectorAll('#v-now .muted,#v-now .loading,#fresh')].map(x=>x.innerText.trim()).filter(Boolean).slice(0,5)"))
    return c, pg

async def t5(b):  # settings: switch to walking 20 min, persists after reload
    c, pg = await ctx(b); await pg.goto(URL); await pg.evaluate(READY); await pg.wait_for_timeout(6000)
    before = await pg.evaluate("[...document.querySelectorAll('#v-now .picks [data-spot]')].slice(0,3).map(a=>a.innerText.split('\\n')[0])")
    await pg.tap("#setBtn"); await pg.wait_for_timeout(800); await shot(pg, "u5a_settings", True)
    a = await audit(pg, "#setSheet", "settings")
    log("  settings controls:", await pg.evaluate("[...document.querySelectorAll('#setBody label,#setBody button,#setBody summary,#setBody h3')].map(x=>x.innerText.trim().slice(0,30)).filter(Boolean).slice(0,40)"))
    log("  settings words:", await pg.evaluate("document.querySelector('#setBody').innerText.split(/\\s+/).length"))
    walk = await pg.evaluate("""(()=>{const b=[...document.querySelectorAll('#setBody button,#setBody label,#setBody input')].find(x=>/walk/i.test(x.innerText||x.value||x.getAttribute('aria-label')||''));if(b){b.click();return (b.innerText||b.value).trim()}return null})()""")
    log("  tapped walk control:", walk); await pg.wait_for_timeout(500)
    await pg.tap("#setClose"); await pg.wait_for_timeout(4000)
    after = await pg.evaluate("[...document.querySelectorAll('#v-now .picks [data-spot]')].slice(0,3).map(a=>a.innerText.split('\\n')[0])")
    log("  top3 before:", before, "| after walk:", after)
    await pg.reload(); await pg.evaluate(READY); await pg.wait_for_timeout(3000)
    log("  travel after reload:", await pg.evaluate("JSON.parse(localStorage.getItem('ss2:prefs')).travel")); return c, pg

async def t6(b):  # every tab: speed, errors, empty states
    c, pg = await ctx(b); await pg.goto(URL); await pg.evaluate(READY); await pg.wait_for_timeout(5000)
    for v in ["map", "spots", "sky", "cal", "now"]:
        n = len(pg.errs); t0 = time.time(); await pg.tap(f'.tabs button[data-v="{v}"]') if await pg.locator(f'.tabs button[data-v="{v}"]').count() else await pg.evaluate(f"show('{v}')")
        await pg.wait_for_timeout(4000); txt = await pg.evaluate(f"(document.querySelector('#v-{v}')||{{}}).innerText||''")
        log(f"  tab {v}: words={len(txt.split())} newErrors={pg.errs[n:][:2]} start: {txt[:220]!r}"); await shot(pg, f"u6_{v}")
        if v != "map": await audit(pg, f"#v-{v}", f"tab {v}")
    log("  tab bar buttons:", await pg.evaluate("[...document.querySelectorAll('.tabs button')].map(b=>b.innerText.trim())")); return c, pg

async def t7(b):  # night vision + dark mode + accessibility (axe)
    c, pg = await ctx(b, scheme="dark"); await pg.goto(URL); await pg.evaluate(READY); await pg.wait_for_timeout(6000)
    await shot(pg, "u7a_dark"); await audit(pg, "#v-now", "dark mode")
    await pg.tap("#nightBtn"); await pg.wait_for_timeout(800); await shot(pg, "u7b_nightvision"); await audit(pg, "#v-now", "night vision")
    await pg.tap("#nightBtn")
    try:
        await pg.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js")
        r = await pg.evaluate("axe.run(document,{resultTypes:['violations']}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length,ex:v.nodes.slice(0,2).map(n=>n.target.join(' ').slice(0,60))})))")
        log("  AXE violations:", json.dumps(r))
        await pg.evaluate("openSpot(document.querySelector('#v-now .picks [data-spot]').dataset.spot)"); await pg.wait_for_timeout(8000)
        r = await pg.evaluate("axe.run('#sheet',{resultTypes:['violations']}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length,ex:v.nodes.slice(0,2).map(n=>n.target.join(' ').slice(0,60))})))")
        log("  AXE spot sheet:", json.dumps(r))
    except Exception as e: log("  axe failed", str(e)[:150])
    # keyboard only: tab order of first 15 focus stops
    await pg.keyboard.press("Escape"); await pg.evaluate("document.activeElement.blur()")
    stops = []
    for _ in range(15):
        await pg.keyboard.press("Tab"); stops.append(await pg.evaluate("(e=>(e.getAttribute('aria-label')||e.innerText||e.tagName).trim().slice(0,25)+(getComputedStyle(e).outlineStyle==='none'&&getComputedStyle(e).boxShadow==='none'?' [NO FOCUS RING]':''))(document.activeElement)"))
    log("  keyboard tab order:", stops); return c, pg

async def t8(b):  # slow phone: 4x CPU + slow 4G, then offline reload
    c, pg = await ctx(b); cdp = await c.new_cdp_session(pg)
    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    await cdp.send("Network.enable"); await cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150, "downloadThroughput": 1.6e6 / 8, "uploadThroughput": 750e3 / 8})
    t0 = time.time(); await pg.goto(URL); dcl = round((time.time() - t0) * 1000)
    ready = await pg.evaluate(READY); log("  slow: page", dcl, "ms, first spot +", ready, "ms")
    shots = []
    await pg.wait_for_timeout(3000); await shot(pg, "u8_slow")
    perf = await pg.evaluate("(()=>{const r=performance.getEntriesByType('resource');return {requests:r.length,kb:Math.round(r.reduce((s,x)=>s+(x.transferSize||0),0)/1024),biggest:r.sort((a,b)=>b.transferSize-a.transferSize).slice(0,6).map(x=>x.name.split('/').slice(-2).join('/').slice(0,50)+' '+Math.round(x.transferSize/1024)+'kb')}})()")
    log("  first load:", json.dumps(perf))
    await pg.wait_for_timeout(8000)
    await cdp.send("Network.emulateNetworkConditions", {"offline": True, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1}); await c.set_offline(True)
    try:
        await pg.reload(timeout=15000); r = await pg.evaluate(READY); await pg.wait_for_timeout(3000)
        log("  OFFLINE reload: first spot", r, "ms | banner:", (await pg.evaluate("document.body.innerText"))[:300].replace("\n", " | "))
    except Exception as e: log("  OFFLINE reload failed:", str(e)[:150])
    await shot(pg, "u8_offline"); return c, pg

async def t9(b):  # desktop and tablet
    for w, h, m, n in [(1440, 900, False, "desk"), (1024, 768, True, "ipad")]:
        c, pg = await ctx(b, w, h, mobile=m); await pg.goto(URL); log(f"  {n} ready", await pg.evaluate(READY), "ms"); await pg.wait_for_timeout(8000)
        await shot(pg, f"u9_{n}"); await audit(pg, "body", n)
        await pg.evaluate("openSpot(document.querySelector('#v-now .picks [data-spot]').dataset.spot)"); await pg.wait_for_timeout(7000); await shot(pg, f"u9_{n}_spot")
        log(f"  {n} errors:", pg.errs[:3]); await c.close()
    return None, None

async def t10(b):  # big text (accessibility font scaling 150%) + reduced motion + landscape phone
    c, pg = await ctx(b, motion="reduce"); await pg.add_init_script("document.addEventListener('DOMContentLoaded',()=>document.documentElement.style.fontSize='150%')")
    await pg.goto(URL); await pg.evaluate(READY); await pg.wait_for_timeout(7000)
    await pg.evaluate("document.documentElement.style.fontSize='150%'; document.body.style.zoom=1.5"); await pg.wait_for_timeout(1000)
    await shot(pg, "u10a_bigtext"); await audit(pg, "body", "150% zoom")
    await c.close()
    c, pg = await ctx(b, 844, 390); await pg.goto(URL); await pg.evaluate(READY); await pg.wait_for_timeout(7000)
    await shot(pg, "u10b_landscape"); await audit(pg, "body", "landscape phone")
    log("  visible picks without scrolling:", await pg.evaluate("[...document.querySelectorAll('#v-now .picks [data-spot]')].filter(e=>e.getBoundingClientRect().top<innerHeight).length"))
    return c, pg

TESTS = [("1 Brand-new visitor, no saved state", t1), ("2 Smallest phone (320x568)", t2), ("3 Spot page: open, scroll, Back", t3),
         ("4 Change location to Bend by search", t4), ("5 Settings: switch to walking, persists", t5), ("6 Every tab", t6),
         ("7 Dark mode, night vision, accessibility, keyboard", t7), ("8 Slow phone + offline", t8), ("9 Desktop + iPad", t9), ("10 Big text + landscape", t10)]
import sys
if len(sys.argv) > 1: TESTS = [t for t in TESTS if t[0].split()[0] in sys.argv[1:]]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, fn in TESTS:
            log(f"\n######## {name}")
            try:
                c, pg = await fn(b)
                if pg: log("  errors:", pg.errs[:4])
                if c: await c.close()
            except Exception as e: log("  TEST CRASHED:", str(e)[:300])
            await asyncio.sleep(8)
        await b.close()
    open("ux/ux.txt", "w").write("\n".join(OUT))
asyncio.run(main())
