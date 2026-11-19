"""Load profile of the live app on a phone-like connection: what loads when, and what moves on screen while it does.
Chromium with Lighthouse's mobile settings (150 ms RTT, 1.6 Mbit/s down, CPU slowed 4x), a 375x812 touch screen and
a saved location, as a returning user has. Two loads: cold (first visit, nothing cached) and warm (reload through the
service worker). For 30 s from first paint it records every change in the six cards at the top of the list (order,
new or gone, moved more than 8 px), page height jumps, layout shifts with the element that moved, long script tasks,
and when the forecast and the list's "core data" arrive. Output: ux/loadprofile.txt (diag.yml pushes ux/ to a branch)

    python tools/loadprofile.py [lat lon]        default Washougal
"""
# (a run is also started by any push that changes this file or its workflow)
import asyncio, json, os, re, sys, time, urllib.request
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"
SECS = 30
os.makedirs("ux", exist_ok=True)

WATCH = """(() => { const W = window.__lp = { t0: performance.now(), ev: [], cls: 0, shifts: [], long: 0, longN: 0, marks: {} };
  const t = () => Math.round(performance.now() - W.t0), log = s => W.ev.push(t() + "ms " + s);
  try { new PerformanceObserver(l => l.getEntries().forEach(e => { if (e.hadRecentInput) return; W.cls += e.value;
    if (e.value > 0.002) W.shifts.push(t() + "ms " + e.value.toFixed(3) + " " + (e.sources || []).map(s => { const n = s.node; if (!n) return "?"; const nm = x => x ? (x.id ? "#" + x.id : String(x.className || x.nodeName).split(" ")[0]) : "";
      return nm(n.parentElement) + ">" + nm(n) + " y" + Math.round(s.previousRect.y) + "->" + Math.round(s.currentRect.y) + " h" + Math.round(s.previousRect.height) + "->" + Math.round(s.currentRect.height) + " '" + String(n.textContent || "").trim().slice(0, 30) + "'"; }).join("; ")); }))
    .observe({ type: "layout-shift", buffered: true }); } catch (e) {}
  try { new PerformanceObserver(l => l.getEntries().forEach(e => { W.long += e.duration; W.longN++; if (e.duration > 200) log("long task " + Math.round(e.duration) + "ms"); })).observe({ type: "longtask", buffered: true }); } catch (e) {}
  let last = null, lastH = 0;
  const tick = () => { if (t() > %d) return;
    if (!W.marks.wx && typeof WX !== "undefined" && WX && WX.pts) { W.marks.wx = t(); log("forecast loaded"); }
    if (!W.marks.core && typeof BOOT !== "undefined" && BOOT.core) { W.marks.core = t(); log("core data ready (BOOT.core)"); }
    const view = document.querySelector(".view:not([hidden])");
    // the picks: the first real (not placeholder) list under the forecast headline; other cards (week planner, extra
    // sections) are counted separately, since those are expected to fill in while the week is ranked
    const pl = view && view.querySelector("#winDetail ul.picks:not(.skel)");
    const cards = pl ? [...pl.querySelectorAll("[data-spot]")] : [];
    const cur = cards.map(e => { const r = e.getBoundingClientRect(); return { id: e.dataset.spot, y: Math.round(r.top + scrollY), h: Math.round(r.height), tx: e.innerText.replace(/\\s+/g, " ").slice(0, 300) }; });
    // heights of everything above the picks, to name what pushed them when they move
    const above = []; if (pl) { let n = pl; while (n && n !== view) { let p = n.previousElementSibling; while (p) { if (getComputedStyle(p).position !== "fixed") above.push([(p.id ? "#" + p.id : String(p.className || p.nodeName).split(" ")[0]) || p.nodeName, Math.round(p.getBoundingClientRect().height)]); p = p.previousElementSibling; } n = n.parentElement; } }
    const other = view ? [...view.querySelectorAll("[data-spot]")].filter(e => !pl || !pl.contains(e)).map(e => e.dataset.spot).join(",") : "";
    if (W.lastOther != null && other !== W.lastOther) W.otherN = (W.otherN || 0) + 1; W.lastOther = other;
    if (cur.length && !W.marks.first) { W.marks.first = t(); log("picks shown: " + cur.map(x => x.id.slice(0, 18)).join(" | ") + " (first at y=" + cur[0].y + ")"); }
    if (last && cur.length) {
      const a = last.map(x => x.id).join(","), b = cur.map(x => x.id).join(",");
      if (a !== b) { const gone = last.filter(x => !cur.some(y => y.id === x.id)).length, add = cur.filter(x => !last.some(y => y.id === x.id)).length;
        log("picks changed: " + (gone || add ? add + " new, " + gone + " gone" : "reordered") + " -> " + cur.map(x => x.id.slice(0, 18)).join(" | ")); W.marks.lastChange = t(); W.pickChanges = (W.pickChanges || 0) + 1; }
      else { const mv = cur.filter((x, i) => Math.abs(x.y - last[i].y) > 8); if (mv.length) {
        const was = new Map((W.above || []).map(([k, h]) => [k, h])), d = above.filter(([k, h]) => was.get(k) !== h).map(([k, h]) => k + " " + (was.has(k) ? was.get(k) + "->" : "new ") + h + "px");
        // a card that grew pushes the ones below it: name it and what text it gained
        const grew = cur.map((x, i) => x.h !== last[i].h ? "card " + (i + 1) + " " + last[i].h + "->" + x.h + "px" + (x.tx !== last[i].tx ? " (text was '" + last[i].tx.slice(-80) + "' now '" + x.tx.slice(-80) + "')" : "") : "").filter(Boolean);
        log("picks moved: " + mv.map(x => "card " + (cur.indexOf(x) + 1) + " " + (x.y - last[cur.indexOf(x)].y) + "px").join(", ") + (grew.length ? "; grew: " + grew.join(", ") : "") + (d.length ? "; above: " + d.join(", ") : "")); W.marks.lastChange = t(); W.pickMoves = (W.pickMoves || 0) + 1; } }
    }
    if (cur.length) { last = cur; W.above = above; }
    const h = document.documentElement.scrollHeight; if (lastH && Math.abs(h - lastH) > 150) log("page height " + lastH + " -> " + h); lastH = h;
    setTimeout(tick, 100); };
  addEventListener("DOMContentLoaded", tick); })()""" % (SECS * 1000)

SUMMARY = """() => { const W = window.__lp, R = performance.getEntriesByType("resource"), nav = performance.getEntriesByType("navigation")[0];
  const kb = f => Math.round(R.filter(f).reduce((a, r) => a + (r.transferSize || 0), 0) / 1024);
  const host = u => { try { const x = new URL(u); return x.host === location.host ? x.pathname.replace("/shotspots/", "") : x.host; } catch (e) { return u; } };
  const big = R.map(r => ({ n: host(r.name), kb: Math.round((r.transferSize || 0) / 1024), end: Math.round(r.responseEnd) })).sort((a, b) => b.kb - a.kb).slice(0, 10);
  const fcp = (performance.getEntriesByType("paint").find(p => p.name === "first-contentful-paint") || {}).startTime;
  return { fcp: fcp && Math.round(fcp), dcl: Math.round(nav.domContentLoadedEventEnd), marks: W.marks, pickChanges: W.pickChanges || 0, pickMoves: W.pickMoves || 0, otherN: W.otherN || 0, cls: +W.cls.toFixed(3), long: Math.round(W.long), longN: W.longN,
    req: R.length, kbAll: kb(() => true), kbJs: kb(r => /\\.js(\\?|$)/.test(r.name)), kbFeed: kb(r => r.name.includes("/feed/")), kbOther: kb(r => !r.name.includes(location.host)),
    lastReq: Math.round(Math.max(0, ...R.map(r => r.responseEnd))), big, paints: window.__paints, ev: W.ev, shifts: W.shifts }; }"""


def hotspots(prof, n=30):
    """Aggregate a CDP CPU profile by function: self time, and total time (self + callees, counted once per sample)."""
    nodes = {x["id"]: x for x in prof["nodes"]}; parent = {}
    for x in prof["nodes"]:
        for ch in x.get("children", []): parent[ch] = x["id"]
    dt = prof.get("timeDeltas", []); samples = prof.get("samples", [])
    def key(x):
        f = x["callFrame"]; u = f.get("url", "").rsplit("/", 1)[-1]
        return f"{f.get('functionName') or '(anonymous)'} {u}:{f.get('lineNumber', -1) + 1}" if u else (f.get("functionName") or "(program)")
    self_t, total_t = {}, {}
    for sid, d in zip(samples, dt[1:] + [0]):
        x = nodes.get(sid)
        if not x: continue
        k = key(x); self_t[k] = self_t.get(k, 0) + d
        seen = set(); cur = sid
        while cur in nodes:
            kk = key(nodes[cur])
            if kk not in seen: total_t[kk] = total_t.get(kk, 0) + d; seen.add(kk)
            cur = parent.get(cur)
    ms = lambda us: round(us / 1000)
    skip = ("(program)", "(idle)", "(root)", "(garbage collector)")
    top_self = sorted(((v, k) for k, v in self_t.items() if k not in skip), reverse=True)[:n]
    top_total = sorted(((v, k) for k, v in total_t.items() if k not in skip and ".js:" in k), reverse=True)[:n]
    return ([f"self  {ms(v):>6} ms  {k}" for v, k in top_self] + [f"total {ms(v):>6} ms  {k}" for v, k in top_total]
            + [f"garbage collection {ms(self_t.get('(garbage collector)', 0))} ms"])


async def profile(p, lat, lon):
    out = []
    b = await p.chromium.launch()
    c = await b.new_context(viewport={"width": 375, "height": 812}, device_scale_factor=3, is_mobile=True, has_touch=True,
                            timezone_id="America/Los_Angeles", service_workers="allow")
    st = {"ss2:loc": {"lat": lat, "lon": lon, "label": "Test", "src": "search", "at": 9e12},
          "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 60, "maxWalk": 30, "start": "gps"}, "ss2:group": "all", "ss2:welcomed": True}
    await c.add_init_script("if (!sessionStorage.__lpSeeded) { sessionStorage.__lpSeeded = 1; " + "".join(
        f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()) + "}")
    await c.add_init_script(WATCH)
    pg = await c.new_page(); cdp = await c.new_cdp_session(pg)
    await cdp.send("Network.enable")
    await cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150, "downloadThroughput": 1.6e6 / 8, "uploadThroughput": 750e3 / 8})
    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    for name in ("cold (first visit)", "warm (returning, service worker)"):
        warm = not name.startswith("cold")
        if warm:   # CPU profile of the warm load: which functions take the time
            await cdp.send("Profiler.enable"); await cdp.send("Profiler.setSamplingInterval", {"interval": 1000}); await cdp.send("Profiler.start")
            await pg.reload(wait_until="domcontentloaded", timeout=90000)
        else: await pg.goto(URL, wait_until="domcontentloaded", timeout=90000)
        await pg.wait_for_timeout(SECS * 1000 + 1000)
        s = await pg.evaluate(SUMMARY); m = s["marks"]
        hot = []
        if warm:
            prof = (await cdp.send("Profiler.stop"))["profile"]; hot = hotspots(prof)
        out.append(f"\n=== {name} ===")
        out.append(f"first paint {s['fcp']} ms | picks shown {m.get('first')} ms | forecast {m.get('wx')} ms | core data {m.get('core')} ms | "
                   f"picks changed {s['pickChanges']}x, moved {s['pickMoves']}x (last {m.get('lastChange', '-')} ms) | other cards changed {s['otherN']}x | list redraws {s['paints']} | layout shift {s['cls']}")
        out.append(f"{s['req']} requests, {s['kbAll']} KB transferred (scripts {s['kbJs']}, feed {s['kbFeed']}, other sites {s['kbOther']}); "
                   f"last request done {s['lastReq']} ms | long script tasks {s['longN']} totalling {s['long']} ms")
        out.append("largest downloads: " + "; ".join(f"{x['kb']}KB {x['n']} (done {x['end']} ms)" for x in s["big"]))
        out.append("timeline:"); out += ["  " + e for e in s["ev"][:60]]
        if s["shifts"]: out.append("layout shifts:"); out += ["  " + e for e in s["shifts"][:25]]
        if hot: out.append("CPU, warm load (self time = in the function itself; total = including what it calls):"); out += ["  " + h for h in hot]
    await b.close()
    return out


async def main():
    lat, lon = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) > 2 else (45.582, -122.353)
    async with async_playwright() as p:
        try:   # which build is live (the service-worker version is a hash of the app files), so a report names what it measured
            ver = re.search(r'const V\s*=\s*"([^"]+)"', urllib.request.urlopen(URL + "sw.js?v=" + str(int(time.time())), timeout=20).read().decode()).group(1)
        except Exception as e: ver = f"unknown ({str(e)[:60]})"
        out = [f"Load profile {URL} (live build {ver}) at {lat},{lon}: Chromium, 150 ms RTT, 1.6 Mbit/s, CPU x4, 375x812"] + await profile(p, lat, lon)
    txt = "\n".join(out)
    open("ux/loadprofile.txt", "w", encoding="utf-8").write(txt + "\n")
    print(txt.encode("ascii", "replace").decode())

if __name__ == "__main__":
    asyncio.run(main())
