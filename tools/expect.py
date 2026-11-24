"""Pass/fail expectations: what a photographer would agree the app must get right, checked on the live site.
Each case: a place, travel limit, filter and window; an assertion on the ranked list. Kept loose ("any of these in the
top 3") so weather alone doesn't fail them. Exits non-zero on any failure (GitHub emails the owner).
Results are appended to data/test_history.jsonl (one line per run) so quality can be charted over time.

    python tools/expect.py            (nightly, in the "Nightly check" workflow)
Add a case whenever a bug is fixed, so it can't come back. Cases test outcomes (views lead), never coverage
(e.g. "a hand-researched spot leads"): ranking must be data driven.
"""
import asyncio, json, os, sys, datetime as dt
from playwright.async_api import async_playwright
URL = "https://estaugaa.github.io/shotspots/"

# name, (lat, lon), prefs, group, window kind (tomorrow), rule, arg
#   any_top: [n, [name substrings]]  - one of these is in the top n
#   max_life: [n, k]                 - at most k of the top n are wildlife-led (birding hotspot/refuge, or first category wildlife/birds)
#   max_kind: [n, kinds, k]          - at most k of the top n are of these kinds
#   none_top: [n, [name substrings]] - none of these is in the top n
CASES = [
 ("Grand Canyon sunrise: a rim point leads", (36.0, -112.12), {"maxDrive": 45}, "all", "sunrise", "any_top", [3, ["Mather", "Hopi", "Yaki", "Lipan", "Grandview", "Powell", "Yavapai", "Moran", "Desert View"]]),
 ("Acadia sunrise: Cadillac Mountain near the top", (44.388, -68.204), {"maxDrive": 30}, "all", "sunrise", "any_top", [5, ["Cadillac"]]),
 ("Moab sunrise: arches or the big overlooks lead", (38.573, -109.55), {"maxDrive": 60}, "all", "sunrise", "any_top", [3, ["Arch", "Dead Horse", "Grand View", "Mesa", "Balanced Rock"]]),
 ("Sedona sunset: a classic red-rock view in the top 5", (34.87, -111.76), {"maxDrive": 30}, "all", "sunset", "any_top", [5, ["Airport Mesa", "Cathedral", "Bell Rock", "Oak Creek Vista", "Devil's Bridge", "Canyon Overlook", "Doe Mountain", "Merry-Go-Round"]]),
 ("La Jolla sunset: coast leads, not museums", (32.847, -117.273), {"maxDrive": 30}, "all", "sunset", "any_top", [3, ["Beach", "Cove", "Cliffs", "Point Loma", "Windansea", "Torrey", "Scripps"]]),
 ("Seattle sunrise: a known view in the top 5", (47.61, -122.33), {"maxDrive": 60}, "all", "sunrise", "any_top", [5, ["Gas Works", "Kerry Park", "Snoqualmie", "West Point", "Alki", "Volunteer Park", "Discovery Park", "Space Needle"]]),
 ("Bend sunrise: a known spot in the top 5", (44.058, -121.315), {"maxDrive": 60}, "all", "sunrise", "any_top", [5, ["Mirror Pond", "Pilot Butte", "Smith Rock", "Benham", "Tumalo", "Sparks Lake", "Dillon"]]),
 ("Washougal sunrise: views lead, not wildlife spots", (45.582, -122.353), {"maxDrive": 60}, "all", "sunrise", "max_life", [3, 1]),
 ("Washougal sunset: views lead, not wildlife spots", (45.582, -122.353), {"maxDrive": 60}, "all", "sunset", "max_life", [3, 1]),
 ("Zion sunset: not taken over by birding spots", (37.189, -112.999), {"maxDrive": 30}, "all", "sunset", "max_kind", [3, ["hotspot", "refuge"], 1]),
 ("Yosemite sunset: Yosemite Valley icons in the top 5", (37.745, -119.59), {"maxDrive": 45}, "all", "sunset", "any_top", [5, ["Yosemite Fall", "El Capitan", "Tunnel View", "Glacier Point", "Half Dome", "Vernal", "Bridalveil", "Valley View", "Sentinel"]]),
 ("Denver sunset: no airport control tower near the top (Nov 16-23: 'Former Stapleton Airport Control Tower' led, on the airport's Wikidata fame)", (39.739, -104.99), {"maxDrive": 90}, "all", "sunset", "none_top", [5, ["Control Tower", "Stapleton"]]),
 ("Hood River sunrise: views lead, not the fish hatchery (Nov 16: Bonneville Fish Hatchery led)", (45.709, -121.521), {"maxDrive": 45}, "all", "sunrise", "none_top", [3, ["Hatchery"]]),
 ("Hood River sunrise: views lead, not wildlife spots", (45.709, -121.521), {"maxDrive": 45}, "all", "sunrise", "max_life", [3, 1]),
 ("Grand Canyon sunrise: nothing beyond the travel limit", (36.0, -112.12), {"maxDrive": 45}, "all", "sunrise", "none_far", 10),
 ("Jackson wildlife morning: nothing behind a closed seasonal gate in the top 5 (Nov 19: Jenny Lake led, Teton Park Road shut)", (43.48, -110.762), {"maxDrive": 60}, "life", "morning", "none_closed", 5),
 ("Washougal: no script errors on load (Nov 19: depth.js 'ns is not defined')", (45.582, -122.353), {"maxDrive": 60}, "all", "sunrise", "no_errors", 0),
 ("Washougal sunrise: 'Why this score' layers add up to the score shown", (45.582, -122.353), {"maxDrive": 60}, "all", "sunrise", "layers_ok", 5),
]

RANK = """(async ([kind]) => {
  const t0 = Date.now(); while (!WX && Date.now() - t0 < 30000) await new Promise(r => setTimeout(r, 500));
  const all = allWindows(LOC, PLAN_HOURS), want = laYMD(new Date(Date.now() + 864e5));
  const w = all.find(x => winDay(x) === want && x.kind === kind); if (!w) return { err: "no " + kind + " window" };
  // road times for this window's own candidates, as opening it in the app would fetch (the app routes the window on
  // screen; ranking another one read straight-line estimates: North Rim spots looked 45 min from the South Rim, Nov 23)
  for (let i = 0; i < 3; i++) { if (typeof loadDrives !== "function" || drivesFetched()) break; if (!(await loadDrives(rankFor(w).slice(0, 150).map(x => x.s.id)))) break; }
  const R = rankFor(w); const layersOk = R.slice(0, 5).every(x => { const L = scoreLayers(x.s, w); return L.length && L[L.length - 1].n === x.f.n; });
  return { wx: !!WX, layersOk, top: R.slice(0, 10).map(x => ({ n: x.s.name, k: x.s.kind || "", life: lifeLed(x.s), far: tooFar(x.s), sc: x.f.n, cl: typeof closedRule === "function" && !!closedRule(x.s.id, w.peak) })) }; })"""


def judge(rule, arg, top):
    if rule == "any_top":
        n, names = arg; hit = [t["n"] for t in top[:n] if any(k.lower() in t["n"].lower() for k in names)]
        return bool(hit), hit
    if rule == "max_life":
        n, k = arg; hit = [t["n"] for t in top[:n] if t["life"]]; return len(hit) <= k, hit
    if rule == "none_top":
        n, names = arg; hit = [t["n"] for t in top[:n] if any(k.lower() in t["n"].lower() for k in names)]
        return not hit, hit
    if rule == "max_kind":
        n, kinds, k = arg; hit = [t["n"] for t in top[:n] if t["k"] in kinds]; return len(hit) <= k, hit
    if rule == "layers_ok":
        return bool(top and top[0].get("_layers_ok")), []
    if rule == "none_closed":
        hit = [t["n"] for t in top[:arg] if t.get("cl")]; return not hit, hit
    if rule == "no_errors":
        return not ERRS, list(ERRS)[:3]
    if rule == "none_far":
        hit = [t["n"] for t in top[:arg] if t["far"]]; return not hit, hit
    return False, ["unknown rule"]


ERRS = []


async def main():
    res = []
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for name, (lat, lon), prefs, group, kind, rule, arg in CASES:
            c = await br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles")
            st = {"ss2:loc": {"lat": lat, "lon": lon, "label": name.split(" ")[0], "src": "search", "at": 9e12},
                  "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 60, "maxWalk": 30, "start": "gps", **prefs}, "ss2:group": group, "ss2:welcomed": True}
            await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
            pg = await c.new_page()
            ERRS.clear(); pg.on("pageerror", lambda e: ERRS.append(str(e)[:160]))
            try:
                await pg.goto(URL); await pg.wait_for_timeout(12000)
                r = await pg.evaluate(RANK, [kind])
                if r.get("err"): ok, why = False, [r["err"]]
                else:
                    if r.get("top"): r["top"][0]["_layers_ok"] = r.get("layersOk")
                    ok, why = judge(rule, arg, r["top"])
                top3 = [f'{t["sc"]} {t["n"]}' for t in r.get("top", [])[:3]]
            except Exception as e:
                ok, why, top3 = False, [f"error: {str(e)[:150]}"], []
            res.append({"case": name, "ok": ok, "why": why, "top3": top3}); await c.close()
            print(("PASS " if ok else "FAIL ") + name, "|", "; ".join(top3), flush=True)
        await br.close()
    passed = sum(r["ok"] for r in res)
    line = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "passed": passed, "total": len(res), "failed": [r["case"] for r in res if not r["ok"]]}
    os.makedirs("data", exist_ok=True)
    with open("data/test_history.jsonl", "a") as f: f.write(json.dumps(line) + "\n")
    s = os.environ.get("GITHUB_STEP_SUMMARY")
    if s:
        with open(s, "a") as f:
            f.write(f"## Expectations: {passed}/{len(res)} pass\n\n| | Case | Top 3 |\n|---|---|---|\n")
            for r in res: f.write(f"| {'✅' if r['ok'] else '❌'} | {r['case']} | {'; '.join(r['top3'])} |\n")
    print(f"{passed}/{len(res)} pass")
    sys.exit(0 if passed == len(res) else 1)

asyncio.run(main())
