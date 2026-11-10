"""'Go now' alerts for subscribers anywhere in the US (the home-area rules in alerts.py stay as they are).

Each push subscription can carry a rough location (rounded to ~5 km), travel mode and limit, and which alerts it
wants. Every 30-minute run checks, per subscriber:
  color  strong sunrise/sunset: a 25-75 % mid/high cloud canvas at the event, little low cloud overhead, and a clear
         path toward the sun (low cloud along 40-260 km of the sun's bearing; thick mid cloud far out). Within 3 h the
         latest GOES scan of that path is blended in, and an alert goes out 45-120 min before the event.
  dark   clear dark night: cloud <= 20 % from end of twilight to 1 am, moon down or under 30 % lit, and a starter or
         researched spot with sky >= 21.0 mag/arcsec^2 within reach. Sent 2-6 pm local the same day.
The best reachable spot that opens toward the light is named in the alert. At most 2 'go now' alerts per device per
7 days, so they stay worth acting on. Feedback ('Went' / 'Missed it') comes back through the outcome form.
"""
import datetime as dt, json, math
from pathlib import Path
from .common import FEED, DATA, http, log, read_json, utcnow, spots
from .sunlite import sun_times

KM = [40, 80, 130, 190, 260]
WEEK_MAX = 2


def _km(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def _dest(lat, lon, az, d):
    R, p = 6371.0, math.pi / 180
    la, lo, b, dr = lat * p, lon * p, az * p, d / R
    la2 = math.asin(math.sin(la) * math.cos(dr) + math.cos(la) * math.sin(dr) * math.cos(b))
    lo2 = lo + math.atan2(math.sin(b) * math.sin(dr) * math.cos(la), math.cos(dr) - math.sin(la) * math.sin(la2))
    return la2 / p, lo2 / p


def _sun_az(lat, day, kind):
    n = day.timetuple().tm_yday; g = 2 * math.pi / 365 * (n - 1)
    decl = 0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
    a = math.degrees(math.acos(max(-1, min(1, math.sin(decl) / math.cos(math.radians(lat))))))
    return a if kind == "sunrise" else 360 - a


def _drive_min(d):   # same shape as the app's estimate
    return 6 + min(d, 10) * 1.25 / 55 * 60 + max(0, d - 10) * 1.15 / 95 * 60


def _travel_min(sub, d):
    return d * 1.3 / 4.8 * 60 if sub.get("travel") == "walk" else _drive_min(d)


def _candidates(sub):
    """Researched spots plus starter spots near the subscriber (from the seed tiles on disk)."""
    lat, lon = sub["lat"], sub["lon"]
    out = [s for s in spots() if _km(lat, lon, s["lat"], s["lon"]) < 200]
    for la in range(math.floor(lat) - 2, math.floor(lat) + 3):
        for lo in range(math.floor(lon) - 2, math.floor(lon) + 3):
            f = FEED / "seed" / f"{la}_{lo}.json"
            if f.exists():
                out += [dict(x, seed=True) for x in json.loads(f.read_text()).get("spots", [])]
    lim = sub.get("limit") or 60
    return [s for s in out if _travel_min(sub, _km(lat, lon, s["lat"], s["lon"])) <= lim and not s.get("closed")]


def _grid():
    g = read_json(FEED / "goes_grid.json", None)
    if not g or not g.get("d9"):
        return None
    age = (utcnow() - dt.datetime.fromisoformat(g["obs"].replace("Z", "+00:00"))).total_seconds() / 60
    return g if age < 50 else None


def _grid_at(g, lat, lon):
    x, y = int((lon - g["w"]) / g["d"]), int((g["n"] - lat) / g["d"])
    if x < 0 or y < 0 or x >= g["nx"] or y >= g["ny"]:
        return None
    return int(g["d9"][y * g["nx"] + x]) * 10 + 5


def _dark_at(lat, lon):
    g = read_json(FEED / "darkgrid.json", None)
    if not g:
        return None
    x, y = int((lon - g["w"]) / g["d"]), int((g["n"] - lat) / g["d"])
    if x < 0 or y < 0 or x >= g["nx"] or y >= g["ny"]:
        return None
    return g["base"] + g["alphabet"].index(g["q"][y * g["nx"] + x]) * g["step"]


def _forecast(pts):
    q = {"latitude": ",".join(f"{p[0]:.2f}" for p in pts), "longitude": ",".join(f"{p[1]:.2f}" for p in pts),
         "hourly": "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high", "forecast_days": 2, "timeformat": "unixtime", "timezone": "auto"}
    j = http("https://api.open-meteo.com/v1/forecast", params=q, timeout=60).json()
    return j if isinstance(j, list) else [j]


def _at(h, t):
    i = min(range(len(h["time"])), key=lambda k: abs(h["time"][k] - t))
    return i if abs(h["time"][i] - t) <= 5400 else None


def _best_spot(cands, kind, sub):
    side = kind
    def score(s):
        d = _km(sub["lat"], sub["lon"], s["lat"], s["lon"])
        lt = s.get("light")
        if lt not in (side, "both"):
            return None
        q = (3 if not s.get("seed") else max(-2, min(4, (math.log2(max(1, s.get("score") or 1)) - 2.3) * 1.6))) + (2 if s.get("hz") else 0)
        q -= 6 if s.get("kind") in ("bridge", "landmark", "refuge", "hotspot") else 0
        return q - _travel_min(sub, d) * 0.03
    best = max(((score(s), s) for s in cands if score(s) is not None), key=lambda x: x[0], default=(None, None))[1]
    return best


def color_alerts(sub, now):
    """Strong sunrise/sunset in the next 45-120 minutes."""
    out = []
    lat, lon = sub["lat"], sub["lon"]
    for k in range(2):
        day = (now + dt.timedelta(days=k)).date()
        rise, sett = sun_times(lat, lon, day)
        for kind, t in (("sunrise", rise), ("sunset", sett)):
            if not t:
                continue
            lead = (t - now).total_seconds() / 60
            if not 45 <= lead <= 120:
                continue
            az = _sun_az(lat, day, kind)
            pts = [(lat, lon)] + [_dest(lat, lon, az, d) for d in KM]
            try:
                fc = _forecast(pts)
            except Exception as e:
                log.warning("go-now forecast: %s", e); return out
            ts = t.timestamp()
            h0 = fc[0]["hourly"]; i = _at(h0, ts)
            if i is None:
                continue
            low, mid, high = h0["cloud_cover_low"][i], h0["cloud_cover_mid"][i], h0["cloud_cover_high"][i]
            canvas = max(mid, high * 0.9)
            block = 0
            for d, r in zip(KM, fc[1:]):
                j = _at(r["hourly"], ts)
                if j is not None:
                    block = max(block, r["hourly"]["cloud_cover_low"][j], r["hourly"]["cloud_cover_mid"][j] * 0.6 if d >= 130 else 0)
            g = _grid(); sat = None
            if g and lead <= 180:
                v = [_grid_at(g, la, lo) for la, lo in pts[1:]]
                if all(x is not None for x in v):
                    sat = max(x * (0.6 if d >= 190 else 1) for x, d in zip(v, KM))
                    block = round(0.6 * sat + 0.4 * block)
            if not (25 <= canvas <= 80 and low < 40 and block <= 25 and (sat is None or sat <= 30)):
                continue
            cands = _candidates(sub)
            s = _best_spot(cands, kind, sub)
            local = t + dt.timedelta(seconds=fc[0].get("utc_offset_seconds", 0))
            where, leave = "", ""
            if s:
                tm = _travel_min(sub, _km(lat, lon, s["lat"], s["lon"]))
                go = local - dt.timedelta(minutes=tm + (20 if kind == "sunset" else 30))
                where = f" at {s['name']} ({round(tm)} min {'walk' if sub.get('travel') == 'walk' else 'drive'})"
                leave = f" Leave by {go.strftime('%-I:%M %p')}."
            sat_txt = " The latest satellite scan shows the path toward the sun open." if sat is not None else ""
            out.append({"key": f"gonow-{kind}-{day.isoformat()}", "title": f"Strong {kind} likely{where}",
                        "body": f"{kind.capitalize()} {local.strftime('%-I:%M %p')}: {round(canvas)}% high/mid cloud to catch color, clear toward the {'east' if kind == 'sunrise' else 'west'}.{sat_txt}{leave}",
                        "spot": s and s.get("id"), "urgent": True})
    return out


def dark_alerts(sub, now, local_hour):
    """Clear dark night tonight, sent once between 2 and 6 pm local."""
    if not 14 <= local_hour < 18:
        return []
    lat, lon = sub["lat"], sub["lon"]
    day = now.date() if local_hour >= 0 else now.date()
    _, sett = sun_times(lat, lon, day)
    if not sett:
        return []
    t0, t1 = sett + dt.timedelta(minutes=95), sett + dt.timedelta(hours=7)
    try:
        h = _forecast([(lat, lon)])[0]["hourly"]
    except Exception:
        return []
    cc = [c for tt, c in zip(h["time"], h["cloud_cover"]) if t0.timestamp() <= tt <= t1.timestamp()]
    if not cc or max(cc) > 30 or sum(cc) / len(cc) > 20:
        return []
    try:
        from . import ephem
        import numpy as np
        u = np.array([t0.timestamp(), (t0.timestamp() + t1.timestamp()) / 2, t1.timestamp()])
        t = ephem.ts_unix(u); ra, dec, dist = ephem.radec("moon", t)
        alt, _ = ephem.altaz(ra, dec, ephem.gast_deg(t), lat, lon, dist)
        illum = float(ephem.moon_illum(t[1]))
        if illum > 0.3 and (alt > 0).sum() >= 2:
            return []
    except Exception as e:
        log.warning("go-now moon: %s", e)
    dark = []
    for s in _candidates(sub):
        q = _dark_at(s["lat"], s["lon"])
        if q and q >= 21.0 and (not s.get("seed") or s.get("kind") in ("viewpoint", "arch", "beach", "lighthouse", "hotspring", "lake", "pass", "lookout")):
            dark.append((q - _travel_min(sub, _km(lat, lon, s["lat"], s["lon"])) * 0.004, q, s))
    if not dark:
        return []
    _, q, s = max(dark, key=lambda x: x[0])
    tm = _travel_min(sub, _km(lat, lon, s["lat"], s["lon"]))
    return [{"key": f"gonow-dark-{day.isoformat()}", "title": f"Clear, dark night tonight at {s['name']}",
             "body": f"Clear skies after twilight with the moon out of the way. {s['name']} ({round(tm)} min) has a {q:.1f} mag/arcsec² sky: the Milky Way should be easy to see.",
             "spot": s.get("id"), "urgent": False}]


def run(subs, sent):
    """subs: {endpoint: {...sub fields incl. lat, lon, travel, limit, kinds}}. Returns [(endpoint, message)]."""
    now = utcnow()
    st = sent.setdefault("gonow", {})
    msgs = []
    for ep, v in subs.items():
        if v.get("lat") is None:
            continue
        from .alerts import h8
        me = st.setdefault(h8(ep), {"keys": {}, "times": []})
        me["times"] = [x for x in me["times"] if x > (now - dt.timedelta(days=7)).isoformat()]
        if len(me["times"]) >= WEEK_MAX:
            continue
        kinds = set(v.get("kinds") or ["color", "dark"])
        off = v.get("utc_offset") or -8 * 3600
        local_hour = (now + dt.timedelta(seconds=off)).hour
        cands = (color_alerts(v, now) if "color" in kinds else []) + (dark_alerts(v, now, local_hour) if "dark" in kinds else [])
        for a in cands:
            if a["key"] in me["keys"] or len(me["times"]) >= WEEK_MAX:
                continue
            me["keys"][a["key"]] = now.isoformat(); me["times"].append(now.isoformat())
            url = f"./#spot={a['spot']}" if a.get("spot") else "./"
            msgs.append((ep, {"title": a["title"], "body": a["body"], "tag": a["key"], "url": url, "urgent": a["urgent"],
                              "actions": [{"action": "went", "title": "Went"}, {"action": "missed", "title": "Missed it"}], "key": a["key"]}))
        me["keys"] = {k: t for k, t in me["keys"].items() if t > (now - dt.timedelta(days=14)).isoformat()}
    return msgs
