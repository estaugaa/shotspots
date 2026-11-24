"""Seasonal planner check: serve this checkout's app/ with the data branch's feed/ (diag.yml links it in), open the nearest
spot and the nearest waterfall at a few places outside the Gorge, and dump the planner. ux/season.txt + ux/season_<n>.png
Run: diag.yml with inputs.script=tools/seasonprobe.py (any branch: -f ref=<branch>) -> branch diag-seasonprobe."""
import asyncio, functools, traceback, http.server, json, os, pathlib, sys, threading
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLACES = [("Moab", 38.573, -109.550), ("Yosemite Valley", 37.745, -119.593), ("Acadia", 44.350, -68.210), ("Smokies", 35.611, -83.425)]
os.makedirs("ux", exist_ok=True)


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

    def translate_path(self, path):   # /feed/... from the data branch, everything else from app/
        p = path.split("?")[0].split("#")[0].lstrip("/")
        base = ROOT if p.startswith("feed/") else ROOT / "app"
        return str(base / (p or "index.html"))


def serve():
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{s.server_address[1]}/"


PICK = """([lat, lon]) => { const d = s => km({ lat, lon }, s), all = SPOTS.filter(s => d(s) < 60).sort((a, b) => d(a) - d(b));
  const v = all.find(s => !s.cats.includes("waterfall")), w = all.find(s => s.cats.includes("waterfall")); return [v, w].filter(Boolean).map(s => s.id); }"""
READ = """() => { const b = document.querySelector('#sheetBody .seasbox'); if (!b) return null;
  const c = [...b.querySelectorAll('.seascells')].map(r => [...r.children].map(i => i.className.includes('none') ? '.' : i.className.includes('fog') ? (i.className.includes('best') ? 'F' : 'f') : i.className.includes('best') ? '*' : '#').join(''));
  return { text: b.innerText, rows: c, cl: document.querySelector('#sheetBody .climoline') ? document.querySelector('#sheetBody .climoline').innerText : null }; }"""

NL = chr(10)


def save(out): open("ux/season.txt", "w").write(NL.join(out))


async def place(c, base, name, lat, lon, out):
    n = bad = 0
    st = {"ss2:loc": {"lat": lat, "lon": lon, "label": name, "src": "search", "at": 9e12}, "ss2:welcomed": True}
    await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
    pg = await c.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    await pg.goto(base); await pg.wait_for_timeout(12000)
    ids = await pg.evaluate(PICK, [lat, lon])
    out.append(f"== {name}: spots {ids}")
    for i in ids:
        await pg.evaluate(f"openSpot({json.dumps(i)})"); await pg.wait_for_timeout(5000)
        r = await pg.evaluate(READ)
        if not r: out.append(f"{i}: NO PLANNER"); bad += 1; continue
        out.append(f"--- {i}" + NL + NL.join(r["rows"]) + NL + r["text"] + NL + f"(spot line: {r['cl']})")
        await pg.evaluate("document.querySelector('#sheetBody .seas i[data-w=\"26\"]').click()")
        out.append("tap week 26: " + await pg.evaluate("[...document.querySelectorAll('.seasdetail')].map(x => x.innerText).join(' | ')"))
        el = await pg.query_selector("#sheetBody .seasbox"); await el.scroll_into_view_if_needed()
        await el.screenshot(path=f"ux/season_{name.split()[0]}_{i[:30]}.png"); n += 1
        await pg.evaluate("typeof closeSheet === 'function' && closeSheet()"); await pg.wait_for_timeout(400)
    soft = await pg.evaluate("typeof SOFT_ERRS === 'object' ? SOFT_ERRS : {}")
    out.append(f"page errors: {errs[:4]}  soft errors: {json.dumps(soft)[:400]}")
    return n, bad


async def main():
    base, out, n, bad = serve(), ["started"], 0, 0; save(out)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, lat, lon in PLACES:
            c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles")
            try:
                a, z = await place(c, base, name, lat, lon, out); n += a; bad += z
            except Exception:
                out.append(f"{name}: PROBE ERROR" + NL + traceback.format_exc()[-1500:])
            save(out); await c.close()
        await b.close()
    out.append(f"planners shown: {n}, missing: {bad}"); save(out); print(NL.join(out))
    sys.exit(1 if n == 0 else 0)

asyncio.run(main())
