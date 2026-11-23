"""Who photographs each spot, and when: measured the same way for every spot (hand-researched and starter alike).

Reads the Commons photo history (data/archive/commons/photos_<dump>_v3.csv.gz: lat, lon, local capture time, photographer
number; 3.08 M US photos with a time, Nov 2026) once, grids it, and for every spot counts:
  who    distinct photographers within R (500 m; 900 m for peaks, where people shoot from around the summit)
  lift   how much that stands out from the area: photographers per km2 within R vs in the ring R..5 km. A downtown
         landmark in a busy city has lift ~1; Multnomah Falls or Haystack Rock stand far above their surroundings.
  am/pm/night  share of those photographers with a photo in morning golden hour (-45..+75 min of sunrise), evening
         golden hour (-75..+45 of sunset) or night (> 90 min from either). Date-only stamps are skipped.
  area   distinct photographers within 5 km: says whether no photos means "nobody goes" or "nobody maps photos here".
Writes feed/spotphotos.json {"gen", "dump", "spots": {id: [who, lift x10, am%, pm%, night%, area]}}.
The old per-spot Commons geosearch (photostats.py) capped at 100 photos and found 8 at Multnomah Falls.

    python -m pipeline spotphotos
"""
import csv, gzip, io, json, math, datetime as dt
from collections import defaultdict
from zoneinfo import ZoneInfo
from .common import read_json, write_json, spots, utcnow, iso, log, soft_fail, DATA, FEED
from .sunlite import sun_times, tz_for

ARCH = DATA / "archive" / "commons"
OUT = FEED / "spotphotos.json"
CELL = 0.01   # grid cell, degrees (~1.1 km north-south)
AREA_KM = 5.0


def _all_spots():
    out = [dict(s, state=s.get("state", "WA")) for s in spots(deep=False)]
    idx = read_json(FEED / "seed" / "index.json", {"tiles": {}})
    for k in idx["tiles"]:
        out += read_json(FEED / "seed" / f"{k}.json", {"spots": []})["spots"]
    seen, uniq = set(), []
    for s in out:
        if s.get("id") and s["id"] not in seen and s.get("lat") is not None:
            seen.add(s["id"]); uniq.append(s)
    return uniq


def _load():
    idx = read_json(ARCH / "index.json", {})
    f = ARCH / (idx.get("file") or "")
    if not f.is_file():
        raise SystemExit(f"spotphotos: no photo file ({f}); run job commonsphotos / photoweather first")
    grid = defaultdict(list)   # (i, j) -> [(lat, lon, who, taken)]
    n = 0
    with gzip.open(f, "rt", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                la, lo = float(r["lat"]), float(r["lon"])
            except (TypeError, ValueError):
                continue
            grid[(int(math.floor(la / CELL)), int(math.floor(lo / CELL)))].append((la, lo, r.get("who") or "", r.get("taken") or ""))
            n += 1
    log.info(f"spotphotos: {n:,} photos in {len(grid):,} cells from {f.name}")
    return grid, idx.get("dump")


def _near(grid, la, lo, km):
    di = int(km / 111.0 / CELL) + 1
    dj = int(km / (111.0 * max(0.2, math.cos(math.radians(la)))) / CELL) + 1
    ci, cj = int(math.floor(la / CELL)), int(math.floor(lo / CELL))
    kx = 111.0 * math.cos(math.radians(la))
    for i in range(ci - di, ci + di + 1):
        for j in range(cj - dj, cj + dj + 1):
            for p in grid.get((i, j), ()):
                d = math.hypot((p[0] - la) * 111.0, (p[1] - lo) * kx)
                if d <= km:
                    yield d, p


_sun = {}


def _light(s, taken, tz):
    """'am' / 'pm' / 'night' / 'day' for a local capture time at this spot, or None."""
    if len(taken) < 16 or taken[11:16] == "00:00":
        return None
    try:
        lt = dt.datetime.fromisoformat(taken[:16]).replace(tzinfo=tz)
    except ValueError:
        return None
    k = (round(s["lat"], 1), round(s["lon"], 1), lt.date())
    if k not in _sun:
        _sun[k] = sun_times(s["lat"], s["lon"], lt.date())
    r, st = _sun[k]
    if not r:
        return None
    u = lt.astimezone(dt.timezone.utc)
    dr, ds = (u - r).total_seconds() / 60, (u - st).total_seconds() / 60
    return "am" if -45 <= dr <= 75 else "pm" if -75 <= ds <= 45 else "night" if dr < -90 or ds > 90 else "day"


def measure(grid, s):
    R = 0.9 if s.get("kind") == "peak" or "mountain" in (s.get("cats") or []) else 0.5
    inner, ring, area = set(), set(), set()
    cls = defaultdict(set)
    try:
        tz = ZoneInfo(tz_for(s))
    except Exception as e:
        soft_fail("spotphotos tz", e); tz = dt.timezone.utc
    for d, (la, lo, who, taken) in _near(grid, s["lat"], s["lon"], AREA_KM):
        area.add(who)
        if d <= R:
            inner.add(who)
            c = _light(s, taken, tz)
            if c:
                cls[c].add(who)
        else:
            ring.add(who)
    a_in, a_ring = math.pi * R * R, math.pi * (AREA_KM ** 2 - R * R)
    dens_ring = max(len(ring), 1) / a_ring
    lift = (len(inner) / a_in) / dens_ring if inner else 0.0
    w = max(1, len(inner))
    pct = lambda k: round(100 * len(cls[k]) / w)
    return [len(inner), round(min(lift, 999) * 10), pct("am"), pct("pm"), pct("night"), len(area)]


def run():
    grid, dump = _load()
    sp = _all_spots()
    out = {}
    for i, s in enumerate(sp):
        try:
            out[s["id"]] = measure(grid, s)
        except Exception as e:
            soft_fail(f"spotphotos {s.get('id')}", e)
        if i % 10000 == 0:
            log.info(f"spotphotos: {i:,}/{len(sp):,}")
    # A spot with no photographer in an area few people photograph says nothing: leave it out (the app treats it as
    # unknown). Kept: any photographer, or >= 20 photographers within 5 km (then none at the spot is a measurement).
    pub = {k: v for k, v in out.items() if v[0] > 0 or v[5] >= 20}
    write_json("spotphotos.json", {"gen": iso(utcnow()), "dump": dump, "fields": ["who", "lift_x10", "am_pct", "pm_pct", "night_pct", "area_who"], "spots": pub})
    log.info(f"spotphotos: {len(out):,} spots written")
    # spot check for the log: famous, odd leaders and obscure ones from the Nov 19 tests
    for s in sp:
        if any(k in s.get("name", "") for k in ("Multnomah", "Haystack", "Hug Point", "Blumenthal", "Freedom Tower", "Vista House", "Bonneville", "Control Tower", "Cadillac", "Mille Creek", "Jenny Lake", "Cape Florida")):
            log.info(f"  {s['name'][:40]:40} {s['id'][:22]:22} who/lift10/am/pm/night/area = {out.get(s['id'])}")
    return out
