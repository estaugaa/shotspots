"""Repeatable scoring test: the app code in app/ ranks spots on a frozen copy of every feed and forecast, at a fixed clock,
and the result must match tests/score/expected.json exactly. Catches scoring changes before they are published, instead
of the next night on live weather (tools/expect.py).

    python tools/scoretest.py            check (app-publish, before publishing): replay fixtures, compare with expected
    python tools/scoretest.py --update   accept the current ranking as expected (after an intended scoring change)
    python tools/scoretest.py --capture  record new fixtures from the live site at the current time, then --update

Fixtures: tests/score/responses.json.gz (every response the page needed, keyed by URL) and tests/score/cases.json (the
fixed time). App code (any path that exists under app/) always comes from the working copy: that is what is tested.
Compared: the top 10 (names, scores, score after each layer for the top 5) and the score of every ranked spot.
Each case runs twice; differing runs fail as unstable (the ranking must not depend on load order).
Nov 18: the app's forecast caches key on time plus version (wxVer), so a replaced forecast is never missed under the
frozen clock; the baseline was re-recorded then (8 far spots changed, every top 10 unchanged).

    python tools/scoretest.py --live     prediction log (nightly, regress.yml): the LIVE site at the real time ranks the
                                         next sunrise and sunset for LIVE_CASES; the top 20 (score, score after each layer,
                                         drive time) per case are appended to data/archive/predictions/<YYYY-MM>.jsonl.gz
                                         so rankings can later be checked against outcomes (tools/predeval.py).
"""
import asyncio, base64, datetime as dt, functools, gzip, hashlib, http.server, json, os, pathlib, re, sys, threading, urllib.parse
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP, DIR = ROOT / "app", ROOT / "tests" / "score"
LIVE = "https://estaugaa.github.io/shotspots/"
SKIP = {"image", "font", "media"}

# name, (lat, lon), prefs, group, window kind (the day after the fixed time)
CASES = [
    ("Washougal sunrise", (45.582, -122.353), {"maxDrive": 60}, "all", "sunrise"),
    ("Washougal sunset", (45.582, -122.353), {"maxDrive": 60}, "all", "sunset"),
    ("Washougal night", (45.582, -122.353), {"maxDrive": 60}, "all", "night"),
    ("Washougal wildlife morning", (45.582, -122.353), {"maxDrive": 60}, "life", "sunrise"),
    ("Grand Canyon sunrise", (36.0, -112.12), {"maxDrive": 45}, "all", "sunrise"),
    ("Yosemite sunset", (37.745, -119.59), {"maxDrive": 45}, "all", "sunset"),
]

RANK = """(async ([kind]) => {
  for (let i = 0; i < 120 && !WX; i++) await new Promise(r => setTimeout(r, 250));
  if (!WX) return { err: "no forecast loaded" };
  const all = allWindows(LOC, PLAN_HOURS), want = laYMD(new Date(Date.now() + 864e5));
  const w = all.find(x => winDay(x) === want && x.kind === kind); if (!w) return { err: "no " + kind + " window" };
  const R = rankFor(w);
  return { top: R.slice(0, 10).map((x, i) => {
    const o = { name: x.s.name, score: x.f.n };
    if (i < 5) o.layers = scoreLayers(x.s, w).map(l => l.n);
    return o; }),
    all: R.map(x => x.s.name + " = " + x.f.n),
    why: Object.fromEntries(R.map(x => [x.s.name, (x.f.why || []).slice(0, 5).join("; ")])) }; })"""


# prediction log: places with ground truth nearby (airport reports in WA/OR, webcams in OR/CA, airports nationwide)
LIVE_CASES = [
    ("Washougal", (45.582, -122.353), {"maxDrive": 60}),
    ("Cannon Beach", (45.892, -123.961), {"maxDrive": 45}),
    ("Hood River", (45.705, -121.521), {"maxDrive": 45}),
    ("Bend", (44.058, -121.315), {"maxDrive": 45}),
    ("Yosemite", (37.745, -119.59), {"maxDrive": 45}),
    ("Grand Canyon", (36.0, -112.12), {"maxDrive": 45}),
    ("Denver", (39.739, -104.99), {"maxDrive": 60}),
    ("Great Smoky Mountains", (35.653, -83.507), {"maxDrive": 45}),
]
LIVE_KINDS = ("sunrise", "sunset")

LIVE_RANK = """(async ([kinds]) => {
  for (let i = 0; i < 120 && !WX; i++) await new Promise(r => setTimeout(r, 250));
  if (!WX) return { err: "no forecast loaded" };
  const iso = d => d && new Date(d).toISOString(), labels = SCORE_LAYERS.map(l => l[0]), out = [];
  for (const kind of kinds) {
    const w = allWindows(LOC, PLAN_HOURS).find(x => x.kind === kind && !x.live);   // the next one that hasn't started
    if (!w) { out.push({ kind, err: "no " + kind + " window" }); continue; }
    const R = rankFor(w);
    out.push({ kind, window: { start: iso(w.start), peak: iso(w.peak), end: iso(w.end) }, labels, n_ranked: R.length,
      scorev: typeof SCORE_V !== "undefined" ? SCORE_V : null,
      top: R.slice(0, 20).map((x, i) => ({ rank: i + 1, id: x.s.id, name: x.s.name, lat: x.s.lat, lon: x.s.lon, cats: (x.s.cats || []).slice(0, 2),
        score: x.f.n, r: Math.round(x.r * 10) / 10, drive_min: Math.round(x.d), layers: scoreLayers(x.s, w).map(l => l.n) })) });
  }
  return { cases: out }; })"""


async def live_case(br, case):
    """The live site, real clock, real data: nothing is replayed (only images and form posts are blocked)."""
    name, (lat, lon), prefs = case
    c = await br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles",
                             service_workers="block")
    st = {"ss2:loc": {"lat": lat, "lon": lon, "label": name, "src": "search", "at": 9e12},
          "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 60, "maxWalk": 30, "start": "gps", **prefs},
          "ss2:group": "all", "ss2:welcomed": True, "ss2:dev": "scoretest"}
    await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
    pg = await c.new_page(); inflight = [0]
    pg.on("request", lambda r: inflight.__setitem__(0, inflight[0] + 1))
    for ev in ("requestfinished", "requestfailed"):
        pg.on(ev, lambda r: inflight.__setitem__(0, inflight[0] - 1))
    async def route(rt):
        rq = rt.request
        if rq.resource_type in SKIP or "/f/" in rq.url: return await rt.abort()
        await rt.continue_()
    await pg.route("**/*", route)
    try:
        await pg.goto(LIVE, wait_until="load", timeout=60000)
        await settle(pg, inflight, quiet=5.0, least=10.0, limit=90)
        r = await pg.evaluate(LIVE_RANK, [list(LIVE_KINDS)])
    except Exception as e:
        r = {"err": f"error: {str(e)[:200]}"}
    await c.close()
    return r


async def live():
    at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    recs, bad = [], 0
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for case in LIVE_CASES:
            r = await live_case(br, case)
            name, (lat, lon), prefs = case
            for x in r.get("cases") or [{"kind": k, "err": r.get("err")} for k in LIVE_KINDS]:
                rec = {"at": at.isoformat().replace("+00:00", "Z"), "case": name, "lat": lat, "lon": lon, "group": "all", **prefs, **x}
                recs.append(rec); bad += bool(x.get("err"))
                print(f"{name} {x['kind']}: " + (x.get("err") or f"{x['n_ranked']} ranked; " + "; ".join(f"{t['score']} {t['name']}" for t in x["top"][:3])), flush=True)
        await br.close()
    f = ROOT / "data" / "archive" / "predictions" / f"{at:%Y-%m}.jsonl.gz"
    f.parent.mkdir(parents=True, exist_ok=True)
    old = gzip.decompress(f.read_bytes()).decode("utf-8") if f.exists() else ""
    new = "".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n" for r in recs)
    f.write_bytes(gzip.compress((old + new).encode("utf-8"), 9, mtime=0))
    print(f"{len(recs) - bad}/{len(recs)} predictions logged to {f.relative_to(ROOT)} ({f.stat().st_size / 1e3:.0f} kB)")
    return 0 if recs and bad < len(recs) else 1


OSRM = "https://router.project-osrm.org/table/v1/driving/"
_OSRM = {}


def osrm_table(store):
    """Drive times are asked for in batches whose make-up depends on which spot tiles had loaded at that moment, so
    replaying by exact URL made a spot's drive time (and score) change between runs. Every recorded batch is split into
    (start, destination) -> seconds; a destination never recorded gets null, as OSRM does, and the app's estimate."""
    if id(store) not in _OSRM:
        t = {}
        for k, (st, _, b) in store.items():
            if not k.startswith(OSRM) or st != 200: continue
            try: d = json.loads(base64.b64decode(b))["durations"][0]
            except Exception: continue
            src, *dst = k[len(OSRM):].split("?")[0].split(";")
            for c, sec in zip(dst, d[1:]):
                if sec is not None: t[(src, c)] = sec
        _OSRM[id(store)] = t
    return _OSRM[id(store)]


_OM = {}
OM_HOST = re.compile(r"^https://(api|air-quality-api|marine-api)\.open-meteo\.com/")


def om_inner(k):
    """An Open-Meteo URL, asked for directly or through the forms Worker's /om forwarder; else None."""
    if "/om?u=" in k: k = urllib.parse.unquote(k.split("/om?u=", 1)[1])
    return k if OM_HOST.match(k) else None


def om_split(u):
    p = urllib.parse.urlsplit(u); q = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    lat = next((v for k, v in q if k == "latitude"), None); lon = next((v for k, v in q if k == "longitude"), None)
    rest = urllib.parse.urlencode(sorted((k, v) for k, v in q if k not in ("latitude", "longitude")))
    return f"{p.netloc}{p.path}?{rest}", (lat or "").split(","), (lon or "").split(",")


def om_table(store):
    """The forecast is asked for at a set of points that grows as spot tiles load (wxPoints in app.js), so replaying by
    exact URL gave far spots a different forecast point from run to run. Every recorded response is split per point;
    every request is answered point by point (never by exact URL, which would again depend on load order): the exact
    point if recorded, else the nearest recorded one with the same parameters."""
    if id(store) not in _OM:
        t = {}
        # forwarded copies first, so a direct answer for the same point (fresher) wins; sorted, so the choice never varies
        for k, (st, _, b) in sorted(store.items(), key=lambda kv: ("/om?u=" not in kv[0], kv[0])):
            u = om_inner(k)
            if not u or st != 200: continue
            try: j = json.loads(base64.b64decode(b))
            except Exception: continue
            params, lats, lons = om_split(u); j = j if isinstance(j, list) else [j]
            if len(j) != len(lats): continue
            for la, lo, x in zip(lats, lons, j):
                t.setdefault(params, {})[(float(la), float(lo))] = x
        _OM[id(store)] = t
    return _OM[id(store)]


def om_answer(store, k):
    u = om_inner(k)
    params, lats, lons = om_split(u); pts = om_table(store).get(params)
    if not pts or not lats[0]: return None
    out = []
    for la, lo in zip(lats, lons):
        p = (float(la), float(lo))
        out.append(pts.get(p) or pts[min(pts, key=lambda q: (q[0] - p[0]) ** 2 + ((q[1] - p[1]) * 0.7) ** 2)])
    return out if len(out) > 1 else out[0]


def key(url, base):
    return "SITE/" + url[len(base):] if url.startswith(base) else url


def local_path(k):
    if not k.startswith("SITE/"): return None
    p = k[5:].split("?")[0].split("#")[0] or "index.html"
    f = APP / p
    return f if f.is_file() and APP in f.resolve().parents else None


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    h = functools.partial(Quiet, directory=str(APP))
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{s.server_address[1]}/"


async def settle(pg, inflight, quiet=4.0, least=6.0, limit=60):
    """Wait until no request has been open for `quiet` seconds and at least `least` seconds have passed (real time; the
    page clock is frozen). Both must exceed the app's deferred loads: seed.js fetches stands and opening hours 2.5 s
    after the spot tiles, and a 2.5 s quiet window sometimes ranked before they arrived (Washougal, Nov 17)."""
    loop = asyncio.get_running_loop(); t0 = last = loop.time()
    while loop.time() - t0 < limit:
        if inflight[0] > 0: last = loop.time()
        elif loop.time() - last >= quiet and loop.time() - t0 >= least: return
        await asyncio.sleep(0.25)


async def run_case(br, case, at, base, store, mode, missing):
    name, (lat, lon), prefs, group, kind = case
    c = await br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, timezone_id="America/Los_Angeles",
                             service_workers="block")
    st = {"ss2:loc": {"lat": lat, "lon": lon, "label": name.split(" ")[0], "src": "search", "at": 9e12},
          "ss2:prefs": {"units": "us", "travel": "drive", "maxDrive": 60, "maxWalk": 30, "start": "gps", **prefs},
          "ss2:group": group, "ss2:welcomed": True, "ss2:dev": "scoretest"}
    await c.add_init_script("".join(f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});" for k, v in st.items()))
    pg = await c.new_page()
    await pg.clock.set_fixed_time(at)
    inflight = [0]
    pg.on("request", lambda r: inflight.__setitem__(0, inflight[0] + 1))
    for ev in ("requestfinished", "requestfailed"):
        pg.on(ev, lambda r: inflight.__setitem__(0, inflight[0] - 1))

    async def route(rt):
        rq = rt.request
        k = key(rq.url, base)
        # never send forms (they would write to the live database); other POSTs (Overpass queries) are keyed by body
        if rq.resource_type in SKIP or "/f/" in rq.url or (rq.method != "GET" and k.startswith("SITE/")): return await rt.abort()
        if rq.method != "GET": k += " POST " + hashlib.sha1((rq.post_data or "").encode()).hexdigest()[:16]
        if mode == "capture":
            try:
                r = await rt.fetch(timeout=30000); body = await r.body()
            except Exception:
                return await rt.abort()
            if r.ok and not local_path(k):
                store[k] = [r.status, r.headers.get("content-type", ""), base64.b64encode(body).decode()]
            return await rt.fulfill(response=r, body=body)
        if local_path(k): return await rt.continue_()
        if k.startswith(OSRM):   # any batch of destinations, answered per destination (see osrm_table)
            src, *dst = k[len(OSRM):].split("?")[0].split(";")
            durs = [0] + [osrm_table(store).get((src, d)) for d in dst]
            return await rt.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"},
                                    body=json.dumps({"code": "Ok", "durations": [durs]}))
        if om_inner(k):
            ans = om_answer(store, k)
            if ans is not None:
                return await rt.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"},
                                        body=json.dumps(ans))
        hit = store.get(k) or store.get(k.split("?")[0])
        if not hit:
            missing.add(k); return await rt.fulfill(status=404, body="")
        await rt.fulfill(status=hit[0], content_type=hit[1], body=base64.b64decode(hit[2]),
                         headers={"access-control-allow-origin": "*"})

    await pg.route("**/*", route)
    try:
        await pg.goto(base, wait_until="load", timeout=60000)
        await settle(pg, inflight)
        r = await pg.evaluate(RANK, [kind])
    except Exception as e:
        r = {"err": f"error: {str(e)[:200]}"}
    await c.close()
    return r


async def main(mode):
    DIR.mkdir(parents=True, exist_ok=True)
    fx, cf = DIR / "responses.json.gz", DIR / "cases.json"
    if mode == "capture":
        at = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
        store = {}
    else:
        if not fx.exists(): print("no fixtures yet (run with --capture): skipped"); return 0
        at = dt.datetime.fromisoformat(json.loads(cf.read_text(encoding="utf-8"))["at"])
        store = json.loads(gzip.decompress(fx.read_bytes()))
    missing = set()
    async with async_playwright() as p:
        br = await p.chromium.launch()
        if mode == "capture":
            for case in CASES:
                r = await run_case(br, case, at, LIVE, store, "capture", missing)
                print(f"captured {case[0]}: {r.get('err') or str(len(r['top'])) + ' ranked'}", flush=True)
            fx.write_bytes(gzip.compress(json.dumps(store, sort_keys=True).encode(), 9, mtime=0))
            cf.write_text(json.dumps({"at": at.isoformat(), "cases": [c[0] for c in CASES]}, indent=1) + "\n")
            print(f"{len(store)} responses, {fx.stat().st_size / 1e6:.1f} MB", flush=True)
        base = serve(); got = {}
        runs = int(os.environ.get("SCORETEST_RUNS") or 2)
        for case in CASES:
            rs = [await run_case(br, case, at, base, store, "replay", missing) for _ in range(runs)]
            whys = [r.pop("why", {}) for r in rs]
            a = rs[0]; b = next((x for x in rs if x != a), a); wb = whys[rs.index(b)] if b in rs else {}
            if a != b:
                A = dict(x.rsplit(" = ", 1) for x in a.get("all") or []); B = dict(x.rsplit(" = ", 1) for x in b.get("all") or [])
                d = [f"{k}: {A.get(k, '-')} | {B.get(k, '-')}" for k in {**A, **B} if A.get(k) != B.get(k)][:15]
                for k in [k for k in {**A, **B} if A.get(k) != B.get(k)][:3]:   # why they differ: the reasons each run gave
                    d.append(f"  {k} run 1: {whys[0].get(k, '-')[:240]}"); d.append(f"  {k} other: {wb.get(k, '-')[:240]}")
                if not d:   # same scores, different order or layers
                    d = [f"#{i + 1}: {x} | {y}" for i, (x, y) in enumerate(zip(a.get("top", []), b.get("top", []))) if x != y][:5] or [f"{a.get('err')} | {b.get('err')}"]
                a = {"err": f"unstable: runs on the same data ranked differently ({sum(x != rs[0] for x in rs)} of {runs} differ from run 1; run 1 | other):\n    " + "\n    ".join(d)}
            got[case[0]] = a
        await br.close()

    if missing: print(f"{len(missing)} requests had no fixture (404):", *sorted(missing)[:15], sep="\n  ")
    ef = DIR / "expected.json"
    if mode in ("capture", "update"):
        bad = [k for k, v in got.items() if v.get("err")]
        if bad: print("not saved, cases failed:", bad, json.dumps({k: got[k] for k in bad})[:1500]); return 1
        ef.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"); print(f"expected.json updated ({len(got)} cases)")
        return 0
    want = json.loads(ef.read_text(encoding="utf-8")); lines, fails = [], 0
    for name, r in got.items():
        w = want.get(name)
        if r.get("err") or r != w:
            fails += 1; lines.append(f"FAIL {name}: {r.get('err') or 'ranking changed'}")
            if not r.get("err") and w:
                for i in range(max(len(r["top"]), len(w["top"]))):
                    o = w["top"][i] if i < len(w["top"]) else {}; n = r["top"][i] if i < len(r["top"]) else {}
                    if o != n:
                        lines.append(f"  #{i + 1}: was {o.get('score')} {o.get('name')} {o.get('layers', '')}"
                                     f" -> now {n.get('score')} {n.get('name')} {n.get('layers', '')}")
                was = dict(x.rsplit(" = ", 1) for x in w.get("all") or []); now = dict(x.rsplit(" = ", 1) for x in r.get("all") or [])
                ch = [f"{k} {was.get(k, '-')}->{now.get(k, '-')}" for k in {**was, **now} if was.get(k) != now.get(k)]
                if ch: lines.append(f"  {len(ch)} of {len(now)} spots changed score: " + "; ".join(ch[:10]))
        else: lines.append(f"PASS {name} | " + "; ".join(f"{t['score']} {t['name']}" for t in r["top"][:3]))
    print("\n".join(lines))
    print(f"{len(got) - fails}/{len(got)} match. If the change is intended: run scoretest.yml with mode=update"
          " (or on a branch, push a commit whose message contains [scoretest:update]).")
    s = os.environ.get("GITHUB_STEP_SUMMARY")
    if s:
        with open(s, "a") as f: f.write(f"## Scoring test: {len(got) - fails}/{len(got)} match\n\n```\n" + "\n".join(lines) + "\n```\n")
    return 1 if fails else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--live" in a: sys.exit(asyncio.run(live()))
    sys.exit(asyncio.run(main("capture" if "--capture" in a else "update" if "--update" in a else "check")))  # --check = default
