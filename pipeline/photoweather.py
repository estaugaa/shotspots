"""Validation from history (MEASURED photos x MODELED reanalysis weather): did people photograph sunrise or sunset
more in some weather than others, and does the app's sky formula agree?

Input: data/archive/commons/photos_<dump>_v2.csv.gz (commonsphotos.py; run first if missing).
1. Each photo gets its time zone from the nearest US airport station (Iowa Mesonet station lists carry tzname; photos
   more than ~150 km from any are dropped, which also drops most of Canada and Mexico), then UTC, then that day's
   sunrise/sunset at the cell centre (sunlite.sun_times). Morning golden hour: -45..+75 min of sunrise, evening:
   -75..+45 min of sunset (as photostats.py).
2. Per 0.25-degree cell and local date: the photographers (distinct uploaders) out that day, at sunrise, at sunset,
   and how many of the golden-hour ones named a file sunset/sunrise/afterglow... Photographers, not photos.
3. Weather at the sunrise and sunset hour, 2016-2025, from the Open-Meteo archive (ERA5 reanalysis: what the sky was
   doing, not what a forecast said), busiest cells first, within the free limit (~10,000 units a day; ten years of one
   place is ~260), so about 35 cells a run; the scheduler runs this daily until every cell with enough days is in.
   Stored per cell in data/photoweather/wx/<cell>.json.gz.
4. Analysis -> feed/photoweather.json: for cell-days with >= 3 photographers out, the share who shot the golden hour,
   relative to that cell's usual share for the event and season; that share by low/mid/high cloud and rain; the sky
   formula's score (camtruth.sky_q, the app's skyCalc; no horizon-gap term, since that needs a second point 90 km
   toward the sun) against it (Spearman), and the weights that agree best.
Caveats kept in the output: the measure is "worth going out for", which includes pleasant weather, not colour alone.

    python -m pipeline photoweather
"""
import csv, gzip, json, math, time, datetime as dt
from collections import defaultdict
from zoneinfo import ZoneInfo
from .common import http, soft_fail, log, utcnow, iso, DATA, FEED
from .sunlite import sun_times
from .camtruth import sky_q, _spearman
from . import commonsphotos

DIR = DATA / "photoweather"
WX = DIR / "wx"
STATE = DIR / "state.json"
OUT = FEED / "photoweather.json"
NET = "https://mesonet.agron.iastate.edu/geojson/network/{}_ASOS.geojson"
STATES = ["AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA",
          "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI",
          "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY"]
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
Y0, Y1 = 2016, 2025
VARS = ["cloud_cover_low", "cloud_cover_mid", "cloud_cover_high", "precipitation", "snowfall", "weather_code"]
UNITS_PER_CELL = math.ceil(((dt.date(Y1, 12, 31) - dt.date(Y0, 1, 1)).days + 1) / 14) * math.ceil(len(VARS) / 10)
DAY_UNITS, HOUR_UNITS = 9000, 4500   # Open-Meteo free: 10,000 a day, 5,000 an hour
MIN_PEOPLE = 3                       # photographers out that day for a cell-day to count
CELL = 0.25
BUDGET_MIN = 300


def _read(p, d):
    try:
        return json.load(gzip.open(p, "rt") if str(p).endswith(".gz") else open(p))
    except Exception:
        return d


def _stations():
    f = DIR / "stations.json"
    s = _read(f, None)
    if s:
        return s
    s = []
    for st in STATES:
        try:
            for ft in http(NET.format(st), timeout=60).json()["features"]:
                p, (lo, la) = ft["properties"], ft["geometry"]["coordinates"][:2]
                if p.get("tzname") and p.get("country", "US") == "US":
                    s.append([round(la, 3), round(lo, 3), p["tzname"]])
        except Exception as e:
            soft_fail(f"photoweather: stations {st}", e)
        time.sleep(0.5)
    DIR.mkdir(parents=True, exist_ok=True); json.dump(s, open(f, "w"))
    return s


def cell_days(photos_file):
    """{(cell_lat, cell_lon): {date: [day set, am set, pm set, am words, pm words]}} from the photo file."""
    import numpy as np
    st = _stations()
    sla, slo = np.array([a for a, *_ in st]), np.array([b for _, b, _ in st]); tzs = [ZoneInfo(t) for *_, t in st]
    def nearest(la, lo):   # (distance in degrees of latitude, station index); once per cell
        d = np.hypot(sla - la, (slo - lo) * math.cos(math.radians(la))); i = int(d.argmin()); return d[i], i
    tzc, sunc, out = {}, {}, defaultdict(dict)
    kept = dropped = 0
    for r in csv.DictReader(gzip.open(photos_file, "rt")):
        la, lo, who = float(r["lat"]), float(r["lon"]), r["who"]
        if not who:
            continue
        ck = (math.floor(la / CELL) * CELL, math.floor(lo / CELL) * CELL)
        if ck not in tzc:
            d, i = nearest(ck[0] + CELL / 2, ck[1] + CELL / 2)
            tzc[ck] = tzs[i] if d < 1.4 else None
        tz = tzc[ck]
        if tz is None:
            dropped += 1; continue
        t = dt.datetime.strptime(r["taken"], "%Y-%m-%d %H:%M")
        if not (Y0 <= t.year <= Y1):
            continue
        day = t.date()
        if (ck, day) not in sunc:
            sunc[(ck, day)] = sun_times(ck[0] + CELL / 2, ck[1] + CELL / 2, day)
        rise, sset = sunc[(ck, day)]
        if not rise:
            continue
        u = t.replace(tzinfo=tz).astimezone(dt.timezone.utc)
        dr, ds = (u - rise).total_seconds() / 60, (u - sset).total_seconds() / 60
        e = out[ck].setdefault(day.isoformat(), [set(), set(), set(), 0, 0])
        e[0].add(who)
        if -45 <= dr <= 75:
            e[1].add(who); e[3] += "s" in r["words"]
        elif -75 <= ds <= 45:
            e[2].add(who); e[4] += "s" in r["words"]
        kept += 1
    log.info("photoweather: %d photos kept, %d outside station range, %d cells", kept, dropped, len(out))
    return out


def _fetch(ck, dates):
    """Weather at the sunrise and sunset hour of each date: {date: {"r": [...], "s": [...]}}, VARS + rain over the 3 h before."""
    la, lo = ck[0] + CELL / 2, ck[1] + CELL / 2
    j = http(ARCHIVE, params={"latitude": la, "longitude": lo, "start_date": f"{Y0}-01-01", "end_date": f"{Y1}-12-31",
                              "hourly": ",".join(VARS), "timezone": "GMT", "timeformat": "unixtime"}, timeout=180, tries=3).json()
    h = j["hourly"]; t0 = h["time"][0]; cols = [h[v] for v in VARS]; pr = h["precipitation"]
    at = lambda u: int(round((u.timestamp() - t0) / 3600))
    out = {}
    for d in dates:
        day = dt.date.fromisoformat(d); rise, sset = sun_times(la, lo, day)
        if not rise:
            continue
        o = {}
        for k, u in (("r", rise), ("s", sset)):
            i = at(u)
            if 3 <= i < len(pr):
                o[k] = [c[i] for c in cols] + [round(sum(x or 0 for x in pr[i - 3:i]), 1)]
        out[d] = o
    return out


def analyse(cd):
    rows = []
    for f in WX.glob("*.json.gz"):
        la, lo = (float(x) for x in f.name[:-8].split("_")); ck = (la, lo)
        wx = _read(f, {})
        for d, e in cd.get(ck, {}).items():
            if len(e[0]) < MIN_PEOPLE or d not in wx:
                continue
            for k, i, wi in (("r", 1, 3), ("s", 2, 4)):
                w = wx[d].get(k)
                if not w or any(x is None for x in w[:4]):
                    continue
                low, mid, high, prc, snow, code, prev = w
                rows.append({"cell": f.name[:-8], "ev": k, "m": int(d[5:7]), "share": len(e[i]) / len(e[0]), "people": len(e[0]),
                             "words": e[wi], "low": low, "mid": mid, "high": high, "rain": prc >= 0.2 or code in (61, 63, 65, 80, 81, 82, 95),
                             "prev": prev, "code": code})
    if len(rows) < 200:
        return {"n": len(rows), "note": "too few cell-days with weather yet"}
    season = lambda m: "DJF" if m in (12, 1, 2) else "MAM" if m <= 5 else "JJA" if m <= 8 else "SON"
    base = defaultdict(list)
    for r in rows:
        base[(r["cell"], r["ev"], season(r["m"]))].append(r["share"])
    for r in rows:
        b = base[(r["cell"], r["ev"], season(r["m"]))]; r["rel"] = r["share"] - sum(b) / len(b) if len(b) >= 5 else None
    rel = [r for r in rows if r["rel"] is not None]
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None

    def table(key, bins):
        o = {}
        for a, b in bins:
            g = [r for r in rel if a <= r[key] < b]
            if len(g) >= 30:
                o[f"{a}-{b if b <= 100 else 100}"] = {"n": len(g), "rel_share": mean([r["rel"] for r in g]), "share": mean([r["share"] for r in g])}
        return o
    B = [(0, 10), (10, 30), (30, 50), (50, 70), (70, 90), (90, 101)]
    DEF = {"canvasFloor": 0.32, "lowBroken": 0.85, "lowDeck": 0.4}
    q = lambda r, p: sky_q(r["low"], r["mid"], r["high"], 100 if r["rain"] else 0, None, None, p)
    out = {"gen": iso(utcnow()), "kind": "MEASURED photos x MODELED ERA5 weather", "years": [Y0, Y1], "min_people": MIN_PEOPLE,
           "n": len(rows), "n_rel": len(rel), "cells": len({r["cell"] for r in rows}),
           "caveat": "share of that day's photographers who shot the golden hour, vs the cell's usual share for the event and season; includes 'pleasant weather', not colour alone; no horizon-gap term",
           "by": {k: table(k, B) for k in ("low", "mid", "high")},
           "rain": {str(v): {"n": len(g), "rel_share": mean([r["rel"] for r in g])} for v in (True, False) for g in [[r for r in rel if r["rain"] == v]]},
           "clearing": {"n": len(g := [r for r in rel if r["prev"] >= 0.5 and not r["rain"]]), "rel_share": mean([r["rel"] for r in g])}}
    for ev in ("r", "s"):
        g = [r for r in rel if r["ev"] == ev]
        out[f"spearman_{ev}"] = round(_spearman([q(r, DEF) for r in g], [r["rel"] for r in g]), 3) if len(g) >= 30 else None
    out["spearman"] = round(_spearman([q(r, DEF) for r in rel], [r["rel"] for r in rel]), 3)
    bands = defaultdict(list)
    for r in rel:
        bands[min(4, int(q(r, DEF) // 20))].append(r["rel"])
    out["share_by_score"] = {f"{b * 20}-{b * 20 + 19}": {"n": len(v), "rel_share": mean(v)} for b, v in sorted(bands.items())}
    best = (out["spearman"], DEF)
    for cf in (0.2, 0.32, 0.45, 0.6, 0.8):
        for lb in (0.5, 0.7, 0.85, 1.0):
            for ld in (0.1, 0.2, 0.4, 0.6):
                p = {"canvasFloor": cf, "lowBroken": lb, "lowDeck": ld}; sp = _spearman([q(r, p) for r in rel], [r["rel"] for r in rel])
                if sp is not None and sp > best[0]:
                    best = (round(sp, 3), p)
    out["best"] = {"spearman": best[0], "params": best[1]}
    return out


def run():
    t0 = time.time(); left = lambda: BUDGET_MIN - (time.time() - t0) / 60
    idx = _read(commonsphotos.OUT / "index.json", {})
    if idx.get("version") != commonsphotos.VERSION:
        log.info("photoweather: photo file v%s missing, extracting first", commonsphotos.VERSION)
        commonsphotos.run()
        idx = _read(commonsphotos.OUT / "index.json", {})
    pf = commonsphotos.OUT / idx.get("file", "")
    if idx.get("version") != commonsphotos.VERSION or not pf.is_file():
        return "photo file not ready yet"
    cd = cell_days(pf)
    WX.mkdir(parents=True, exist_ok=True)
    st = _read(STATE, {}); today = utcnow().date().isoformat()
    used = st.get("units", 0) if st.get("day") == today else 0
    # busiest cells first: days with enough photographers out
    rank = sorted(((sum(len(e[0]) >= MIN_PEOPLE for e in v.values()), ck) for ck, v in cd.items()), reverse=True)
    todo = [(n, ck) for n, ck in rank if n >= 30 and not (WX / f"{ck[0]:g}_{ck[1]:g}.json.gz").exists()]
    got, hour_start, hour_used = 0, time.time(), 0
    for n, ck in todo:
        if used + UNITS_PER_CELL > DAY_UNITS or left() < 20:
            break
        if hour_used + UNITS_PER_CELL > HOUR_UNITS:
            wait = 3600 - (time.time() - hour_start)
            if wait > 0 and left() > wait / 60 + 20:
                time.sleep(wait)
            hour_start, hour_used = time.time(), 0
        dates = [d for d, e in cd[ck].items() if len(e[0]) >= MIN_PEOPLE]
        try:
            wx = _fetch(ck, dates)
        except Exception as e:
            soft_fail("photoweather: weather", e)
            if "429" in str(e):
                break
            continue
        with gzip.open(WX / f"{ck[0]:g}_{ck[1]:g}.json.gz", "wt") as f:
            json.dump(wx, f, separators=(",", ":"))
        used += UNITS_PER_CELL; hour_used += UNITS_PER_CELL; got += 1
        time.sleep(2)
    json.dump({"day": today, "units": used, "cells_done": len(list(WX.glob("*.json.gz"))), "cells_wanted": sum(n >= 30 for n, _ in rank)}, open(STATE, "w"))
    res = analyse(cd)
    FEED.mkdir(parents=True, exist_ok=True); json.dump(res, open(OUT, "w"), separators=(",", ":"))
    left_cells = sum(1 for n, ck in todo) - got
    return (f"{got} cells of weather fetched ({left_cells} left, ~{UNITS_PER_CELL} units each); {res.get('n', 0)} cell-day events, "
            f"Spearman formula vs golden-hour share {res.get('spearman')}, best {res.get('best', {}).get('spearman')}")
