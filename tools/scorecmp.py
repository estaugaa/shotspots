"""Compare scoring v1 vs v2 on the diag situations (same page load, same forecast): top 6 under each.
python tools/scorecmp.py -> ux/scorecmp.txt"""
import asyncio, ast, json, os
from playwright.async_api import async_playwright
os.makedirs("ux", exist_ok=True)
src = open(os.path.join(os.path.dirname(__file__), "diag.py")).read()
S = next(ast.literal_eval(n.value) for n in ast.parse(src).body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "S")
PICK = next(ast.literal_eval(n.value) for n in ast.parse(src).body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PICK")
CMP = """(() => { const w = UI.win && allWindows(LOC, PLAN_HOURS).find(x => x.id === UI.win) || UI.cur || null; return null; })"""
RANK = """(() => { const w = allWindows(LOC, PLAN_HOURS)[UI.focus];
  if (!w) return { err: "no window" };
  const top = v => { SCORE_V = v; return rankFor(w).slice(0, 6).map(x => `${x.f.n} ${x.s.name.slice(0, 34)} [${x.s.kind || 'curated'}${x.q != null ? '' : ''}] q${x.f.q != null ? x.f.q.toFixed(2) : '-'} ${Math.round(x.d)}m`); };
  const a = top(1), b = top(2); SCORE_V = 2; return { kind: w.kind, v1: a, v2: b }; })"""
async def main():
    out = []
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for name, loc, prefs, group, (day, kind), _ in S:
            if group == "life" or kind == "night": continue
            c = await br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles")
            st = {"ss2:loc": {**loc, "src": "search", "at": 9e12}, "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 120, "maxWalk": 30, "start": "gps", **prefs}, "ss2:group": group, "ss2:welcomed": True}
            await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
            pg = await c.new_page(); await pg.goto("https://estaugaa.github.io/shotspots/"); await pg.wait_for_timeout(15000)
            try:
                win = await pg.evaluate(PICK, [day, kind])
                r = await pg.evaluate(RANK); r["win"] = win
            except Exception as e: r = {"err": str(e)[:300]}
            out.append({"s": name, **(r if isinstance(r, dict) else {"err": str(r)})}); await c.close()
            print(name, flush=True)
        await br.close()
    open("ux/scorecmp.txt", "w").write(json.dumps(out, indent=1))
asyncio.run(main())
