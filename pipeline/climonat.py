"""National sunrise/sunset sky climatology (MEASURED history) from the Iowa Environmental Mesonet ASOS/AWOS archive.

For every US airport station with at least 5 years of reports: fetch up to 10 years of routine hourly reports, keep for
each day the report closest to local sunrise and to local sunset (within 45 min), and count by week of year:
  clear  every reported layer CLR/SKC/FEW (ASOS ceilometers see only below 12,000 ft, so high cloud is invisible)
  bkn    broken cloud with base at or below 6,500 ft, not overcast
  ovc    overcast or sky obscured (OVC/VV) at any reported height
  fog    fog or mist reported (FG/BR, not patches/shallow) or visibility 5/8 mile or less
n is the number of days with a report near that event. Counts, not percentages, so sample sizes stay visible.

Output: feed/climo/<lat>_<lon>.json (1-degree tiles, like feed/seed) plus feed/climo/index.json listing the tiles.
Each tile: {"v", "cols", "stations": {id: {name, lat, lon, el, y: [first year, last year], r: [52 x cols], s: [...]}}}
(r = sunrise, s = sunset, flattened week by week). Long first run: ~5 s a station, chains itself with .more.
Re-done after a year or when VERSION changes.
"""
import csv, io, json, math, time, datetime as dt
from .common import soft_fail, http, utcnow, iso, FEED, DATA, log
from .sunlite import sun_times

VERSION = 1
YEARS = 10
MIN_YEARS = 5
WINDOW_MIN = 45
COLS = ["n", "clear", "bkn", "ovc", "fog"]
OUT = FEED / "climo"
STATE_FILE = DATA / "climonat.json"
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
NET = "https://mesonet.agron.iastate.edu/geojson/network/{}_ASOS.geojson"
# Pacific Northwest and the West first (Eric's home ground and most-used area), then everything else
STATES = ["WA", "OR", "ID", "CA", "NV", "MT", "UT", "AZ", "CO", "WY", "NM", "AK", "HI", "AL", "AR", "CT", "DE", "FL", "GA", "IL",
          "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "NE", "NH", "NJ", "NY", "NC", "ND", "OH", "OK",
          "PA", "RI", "SC", "SD", "TN", "TX", "VT", "VA", "WV", "WI", "PR"]


def tile_key(lat, lon):
    return f"{math.floor(lat)}_{math.floor(lon)}"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def sky_class(row):
    """(clear, bkn, ovc, fog) booleans for one report. clear/bkn/ovc are exclusive; None if the sky wasn't reported."""
    layers = [((row.get(f"skyc{i}") or "").strip(), _f(row.get(f"skyl{i}"))) for i in (1, 2, 3)]
    cover = [(c, h) for c, h in layers if c and c != "M"]
    v = _f(row.get("vsby"))
    wx = row.get("wxcodes") or ""
    wxw = [w for w in wx.replace("+", " ").split() if w != "M"]
    fog = (v is not None and v <= 0.62) or any(("FG" in w or "BR" in w) and not w.startswith(("BC", "MI", "PR")) for w in wxw)
    if not cover:
        return None
    ovc = any(c in ("OVC", "VV") for c, _ in cover)
    clear = not ovc and all(c in ("CLR", "SKC", "FEW", "NSC", "NCD") for c, _ in cover)
    bkn = not ovc and any(c == "BKN" and h is not None and h <= 6500 for c, h in cover)
    return clear, bkn, ovc, fog


def week_of(day):
    """0..51, same as the app's weekIdx (days since Jan 1 / 7, the last days of the year fold into week 51)."""
    return min(51, (day.timetuple().tm_yday - 1) // 7)


def aggregate(rows, lat, lon):
    """rows: dicts with 'valid' ("YYYY-MM-DD HH:MM" UTC) + sky/visibility fields. Returns (r, s, y0, y1): r and s are 52 lists
    of COLS counts; each day counts once per event, using the report closest to sunrise/sunset within WINDOW_MIN."""
    sun = {}
    best = {}   # (date, event) -> (minutes off, row)
    years = set()
    off = dt.timedelta(hours=lon / 15)   # local solar date: sunrise and sunset fall on the same one
    for row in rows:
        try:
            t = dt.datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
        except (KeyError, ValueError) as e:
            soft_fail("climonat: bad report time", e)
            continue
        d = (t + off).date()
        if d not in sun:
            sun[d] = sun_times(lat, lon, d)
        for ev, et in zip(("r", "s"), sun[d]):
            if et is None:
                continue
            m = abs((t - et).total_seconds()) / 60
            if m <= WINDOW_MIN and ((d, ev) not in best or m < best[(d, ev)][0]):
                best[(d, ev)] = (m, row)
    out = {"r": [[0] * len(COLS) for _ in range(52)], "s": [[0] * len(COLS) for _ in range(52)]}
    for (d, ev), (_, row) in best.items():
        c = sky_class(row)
        if c is None:
            continue
        years.add(d.year)
        cell = out[ev][week_of(d)]
        cell[0] += 1
        for i, b in enumerate(c):
            cell[i + 1] += int(b)
    return out["r"], out["s"], (min(years) if years else None), (max(years) if years else None)


def fetch(st, start, end):
    params = [("station", st), ("data", "vsby"), ("data", "skyc1"), ("data", "skyl1"), ("data", "skyc2"), ("data", "skyl2"),
              ("data", "skyc3"), ("data", "skyl3"), ("data", "wxcodes"), ("year1", start.year), ("month1", start.month), ("day1", start.day),
              ("year2", end.year), ("month2", end.month), ("day2", end.day), ("tz", "Etc/UTC"), ("format", "onlycomma"),
              ("latlon", "no"), ("missing", "M"), ("trace", "T"), ("direct", "no"), ("report_type", 3)]
    txt = http(IEM, params=params, timeout=300).text
    return list(csv.DictReader(io.StringIO(txt)))


def stations(state):
    """Stations of one state network with at least MIN_YEARS of archive and still reporting."""
    j = http(NET.format(state), timeout=60).json()
    cut = (utcnow().date() - dt.timedelta(days=365 * MIN_YEARS)).isoformat()
    res = []
    for f in j.get("features", []):
        p, g = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates")
        if not g or not p.get("sid") or p.get("archive_end") or not p.get("archive_begin") or p["archive_begin"] > cut:
            continue
        res.append({"id": p["sid"], "name": p.get("sname") or p["sid"], "lat": round(g[1], 4), "lon": round(g[0], 4),
                    "el": round(p["elevation"]) if p.get("elevation") is not None else None, "state": state})
    return res


def _read(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default
    except Exception as e:
        soft_fail(f"climonat: {path.name} unreadable", e)
        return default


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    tmp.replace(path)


def write_index(state):
    tiles = {}
    for p in OUT.glob("*_*.json"):
        n = len(_read(p, {}).get("stations", {}))
        if n:
            tiles[p.stem] = n
    _write(OUT / "index.json", {"v": VERSION, "gen": iso(utcnow()), "years": YEARS, "window_min": WINDOW_MIN, "cols": COLS,
                                "states_done": state.get("states_done", []), "tiles": dict(sorted(tiles.items()))})
    return sum(tiles.values())


def run(budget_min=300):
    t_end = time.time() + budget_min * 60
    state = _read(STATE_FILE, {})
    if state.get("v") != VERSION:
        state = {"v": VERSION, "done": {}, "states_done": []}
    end = utcnow().date()
    start = end.replace(year=end.year - YEARS)
    stale = (end - dt.timedelta(days=365)).isoformat()
    if len(state["states_done"]) == len(STATES) and state.get("checked", "") > (end - dt.timedelta(days=7)).isoformat():
        return f"up to date ({write_index(state)} stations; station lists re-checked weekly)"
    did = failed = 0
    out_of_time = False
    for stt in STATES:
        try:
            sts = stations(stt)
        except Exception as e:
            soft_fail(f"climonat: {stt} station list", e)
            failed += 1
            continue
        left = [s for s in sts if state["done"].get(s["id"], "") < stale]
        for s in left:
            if time.time() > t_end:
                out_of_time = True
                break
            try:
                rows = fetch(s["id"], start, end)
            except Exception as e:
                soft_fail(f"climonat: {s['id']} download", e)
                failed += 1
                time.sleep(10)
                continue
            r, ss, y0, y1 = aggregate(rows, s["lat"], s["lon"])
            path = OUT / f"{tile_key(s['lat'], s['lon'])}.json"
            tile = _read(path, {"v": VERSION, "cols": COLS, "stations": {}})
            if y0 is not None and sum(c[0] for c in r + ss) >= 200:
                tile["stations"][s["id"]] = {"name": s["name"], "lat": s["lat"], "lon": s["lon"], "el": s["el"], "y": [y0, y1],
                                             "r": [x for c in r for x in c], "s": [x for c in ss for x in c]}
                _write(path, tile)
            state["done"][s["id"]] = end.isoformat()   # also too-sparse stations, so they aren't fetched again for a year
            did += 1
            time.sleep(1)   # be gentle with IEM
        if out_of_time:
            break
        if stt not in state["states_done"]:
            state["states_done"].append(stt)
        _write(STATE_FILE, state)
        log.info("climonat: %s done (%d stations)", stt, len(sts))
    if not out_of_time and len(state["states_done"]) == len(STATES):
        state["checked"] = end.isoformat()
    _write(STATE_FILE, state)
    n = write_index(state)
    if out_of_time:
        open(".more", "w").write("1")
    return f"{n} stations in {len(state['states_done'])} states ({did} fetched this run, {failed} failed){'; more to do' if out_of_time else ''}"
