"""What each place is for, learned from photos people already took there (Wikimedia Commons, keyless).

For every spot, geosearch Commons photos within ~500 m, read when each was taken (EXIF DateTimeOriginal, local
time), and classify it against that day's sunrise/sunset there: morning golden hour, evening golden hour, night or
daytime, plus the month. With enough photos (≥ 8) this gives each spot a learned best light (sunrise / sunset /
both / night / day), its busiest months, and a photo count. Starter spots in the app use these in place of their
generic guesses. Results are cached in data/photostats.json and refreshed every 120 days.

    python -m pipeline photostats      (also runs in the weekly job, within a time budget)
"""
import json, math, time, datetime as dt
from zoneinfo import ZoneInfo
from .common import http, read_json, write_json, spots, utcnow, iso, log, DATA, FEED
from .sunlite import sun_times, tz_for

CACHE = DATA / "photostats.json"
API = "https://commons.wikimedia.org/w/api.php"
H = {"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots; photo-timing statistics)"}


def _all_spots():
    out = [dict(s, state=s.get("state", "WA")) for s in spots()]
    idx = read_json(FEED / "seed" / "index.json", {"tiles": {}})
    for k in idx["tiles"]:
        out += read_json(FEED / "seed" / f"{k}.json", {"spots": []})["spots"]
    return out


def _photos(s):
    r = 900 if s.get("kind") in ("peak",) or any(c in (s.get("cats") or []) for c in ("mountain",)) else 500
    j = http(API, params={"action": "query", "format": "json", "generator": "geosearch", "ggscoord": f"{s['lat']}|{s['lon']}", "ggsradius": r,
             "ggslimit": 100, "ggsnamespace": 6, "prop": "imageinfo", "iiprop": "extmetadata", "iiextmetadatafilter": "DateTimeOriginal"}, headers=H, timeout=40).json()
    out = []
    for pg in (j.get("query") or {}).get("pages", {}).values():
        m = ((pg.get("imageinfo") or [{}])[0].get("extmetadata") or {}).get("DateTimeOriginal", {}).get("value", "")
        m = m.split("<")[0].strip()[:19].replace(":", "-", 2)
        try:
            out.append(dt.datetime.fromisoformat(m.replace(" ", "T")))
        except ValueError:
            pass
    return out


def classify(s, times):
    tz = ZoneInfo(tz_for(s))
    c = {"am": 0, "pm": 0, "night": 0, "day": 0}
    months = [0] * 12
    for t in times:
        if t.hour == 0 and t.minute == 0 and t.second == 0:
            continue   # date-only stamps carry no time of day
        lt = t.replace(tzinfo=tz)
        r, st = sun_times(s["lat"], s["lon"], lt.date())
        if not r:
            continue
        u = lt.astimezone(dt.timezone.utc)
        dr, ds = (u - r).total_seconds() / 60, (u - st).total_seconds() / 60
        k = "am" if -45 <= dr <= 75 else "pm" if -75 <= ds <= 45 else "night" if dr < -90 or ds > 90 else "day"
        c[k] += 1
        months[lt.month - 1] += 1
    n = sum(c.values())
    if n < 8:
        return {"n": n}
    gold = c["am"] + c["pm"]
    light = "night" if c["night"] / n >= 0.35 else ("both" if min(c["am"], c["pm"]) >= 0.35 * gold else "sunrise" if c["am"] > c["pm"] else "sunset") if gold / n >= 0.25 else "day"
    order = sorted(range(12), key=lambda i: -months[i])
    top, acc = [], 0
    for i in order:
        if acc >= 0.8 * n:
            break
        top.append(i + 1); acc += months[i]
    return {"n": n, "light": light, "share": {k: round(v / n, 2) for k, v in c.items()}, "months": sorted(top) if len(top) <= 8 else None}


def run(budget_min=150):
    cache = read_json(CACHE, {})
    t0, done = time.time(), 0
    fresh = (utcnow() - dt.timedelta(days=120)).isoformat()
    todo = [s for s in _all_spots() if (cache.get(s["id"]) or {}).get("at", "") < fresh]
    for s in todo:
        if time.time() - t0 > budget_min * 60:
            break
        try:
            cache[s["id"]] = {**classify(s, _photos(s)), "at": iso(utcnow())}
            done += 1
        except Exception as e:
            log.warning("photostats %s: %s", s["id"], e)
        time.sleep(0.3)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, separators=(",", ":")))
    learned = {k: {x: v[x] for x in ("n", "light", "months") if v.get(x) is not None} for k, v in cache.items() if v.get("light")}
    write_json("photostats.json", {"gen": iso(utcnow()), "spots": learned,
                                   "note": "Learned from when Wikimedia Commons photos within ~500 m were taken (≥ 8 photos)."})
    return f"{done} spots checked this run, {len(todo) - done} left; {len(learned)} with learned light"
