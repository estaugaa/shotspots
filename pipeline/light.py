"""Light on the subject (MODELED from 3DEP terrain + DE440).

daily():  next 14 days per spot -> open-horizon vs terrain sunrise/sunset, intervals when the sun actually
          reaches the spot, terrain moonrise/moonset with illumination, Milky Way core window over terrain,
          and alpenglow windows on the big volcanoes.
plan_year(): next 365 days -> when sun, moon, Milky Way core, Orion, the Pleiades or Cygnus line up with a
          landmark that terrain doesn't hide from the spot. Written to feed/planner.json.
"""
import datetime as dt, math
from zoneinfo import ZoneInfo
import numpy as np
from . import ephem, terrain
from .common import spots, landmarks, write_json, log, iso, utcnow, r

LA = ZoneInfo("America/Los_Angeles")
STEP = 120  # seconds


def _runs(mask):
    """Start/stop indices of True runs."""
    m = np.concatenate([[False], mask, [False]]).astype(np.int8)
    d = np.diff(m)
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0] - 1))


def _geo(t0, t1, step, bodies):
    u, t = ephem.times_utc(t0, t1, step)
    g = ephem.gast_deg(t)
    out = {"u": u, "gast": g}
    for b in bodies:
        out[b] = ephem.radec(b, t)
    if "moon" in bodies:
        out["illum"] = ephem.moon_illum(t)
    return out


def local_midnights(days):
    now = dt.datetime.now(LA)
    d0 = dt.datetime(now.year, now.month, now.day, tzinfo=LA)
    return [d0 + dt.timedelta(days=k) for k in range(days + 1)]


def daily(days=14):
    H = terrain.load()
    mids = local_midnights(days)
    t0, t1 = mids[0].timestamp(), mids[-1].timestamp()
    G = _geo(t0, t1, STEP, ["sun", "moon", "mwcore"])
    u = G["u"]
    day_idx = np.searchsorted([m.timestamp() for m in mids], u, side="right") - 1
    out = {"gen": iso(utcnow()), "step": STEP, "t0": int(t0), "days": [m.date().isoformat() for m in mids[:-1]], "spots": {}, "alpen": {}, "elev": {}}
    # alpenglow on volcano summits (global, per peak per day)
    for lm in landmarks():
        if lm["kind"] != "peak":
            continue
        sa, _ = ephem.altaz(*G["sun"][:2], G["gast"], lm["lat"], lm["lon"])
        sa = ephem.refract(sa)
        dip = math.degrees(math.acos(6371000 / (6371000 + lm["elev"])))
        lit = sa > -dip
        pink = lit & (sa < 2.0)
        rows = []
        for k in range(days):
            sel = day_idx == k
            idx = np.where(sel)[0]
            if not len(idx):
                continue
            noon = idx[len(idx) // 2]
            am = [ (a, b) for a, b in _runs(pink & sel) if a < noon]
            pm = [ (a, b) for a, b in _runs(pink & sel) if a >= noon]
            rows.append([int(u[am[0][0]] // 60) if am else None, int(u[am[0][1]] // 60) if am else None,
                         int(u[pm[-1][0]] // 60) if pm else None, int(u[pm[-1][1]] // 60) if pm else None])
        out["alpen"][lm["name"]] = rows
    for s in spots():
        h = H.get(s["id"])
        if not h:
            continue
        lat, lon = s["lat"], s["lon"]
        sa, saz = ephem.altaz(*G["sun"][:2], G["gast"], lat, lon)
        sa = ephem.refract(sa)
        hz_s = terrain.horizon_alt(h, saz)
        ma, maz = ephem.altaz(G["moon"][0], G["moon"][1], G["gast"], lat, lon, G["moon"][2])
        ma = ephem.refract(ma)
        hz_m = terrain.horizon_alt(h, maz)
        ca, caz = ephem.altaz(*G["mwcore"][:2], G["gast"], lat, lon)
        hz_c = terrain.horizon_alt(h, caz)
        open_up = sa > -0.833
        terr_up = sa + 0.27 > hz_s           # any part of the disc above the terrain
        lit = sa > hz_s                       # sun centre above terrain: direct light on the spot
        moon_up = ma + 0.26 > hz_m
        core_ok = (ca > hz_c + 3) & (sa < -15)
        rows = []
        for k in range(days):
            sel = day_idx == k
            idx = np.where(sel)[0]
            if not len(idx):
                continue
            def first(m):
                w = np.where(m & sel)[0]
                return int(u[w[0]] // 60) if len(w) else None
            def last(m):
                w = np.where(m & sel)[0]
                return int(u[w[-1]] // 60) if len(w) else None
            lit_iv = [[int(u[a] // 60), int(u[b] // 60)] for a, b in _runs(lit & sel) if b - a >= 2]
            mr = [(a, b) for a, b in _runs(moon_up & sel)]
            core = [[int(u[a] // 60), int(u[b] // 60)] for a, b in _runs(core_ok & sel) if b - a >= 5]
            # sun azimuth at open sunrise/sunset for backlight calculations
            fo, lo_ = first(open_up), last(open_up)
            rows.append({
                "or": fo, "os": lo_, "tr": first(terr_up), "ts": last(terr_up), "lit": lit_iv,
                "mr": int(u[mr[0][0]] // 60) if mr and mr[0][0] > idx[0] else None,
                "ms": int(u[mr[0][1]] // 60) if mr and mr[0][1] < idx[-1] else None,
                "mi": r(float(G["illum"][idx[len(idx) // 2]]) * 100, 0),
                "core": core,
                "saz": [r(float(saz[np.where(open_up & sel)[0][0]]), 1) if fo else None, r(float(saz[np.where(open_up & sel)[0][-1]]), 1) if lo_ else None],
            })
        out["spots"][s["id"]] = rows
        out["elev"][s["id"]] = h["elev"]
    write_json("light.json", out)
    return f"{len(out['spots'])} spots x {days} days; terrain-aware sun, moon and Milky Way core"


# ---------------- yearly alignment planner ----------------
def plan_year(days=365):
    H = terrain.load()
    far = terrain.far_grid()
    now = utcnow()
    t0 = now.timestamp()
    t1 = t0 + days * 86400
    G = _geo(t0, t1, STEP, ["sun", "moon", "mwcore", "orion", "pleiades", "cygnus"])
    u = G["u"]
    lms = landmarks()
    events = {}
    for s in spots():
        h = H.get(s["id"])
        if not h:
            continue
        lat, lon = s["lat"], s["lon"]
        vis = []
        for lm in lms:
            v = terrain.landmark_view(h, lat, lon, h["elev"], lm, far)
            if v["dkm"] < 1.0 or not v["visible"] or v["alt"] < -1.5:
                continue
            vis.append((lm, v))
        if not vis:
            continue
        cache = {}
        def aa(b):
            if b not in cache:
                ra, dec, dist = G[b]
                a, z = ephem.altaz(ra, dec, G["gast"], lat, lon, dist if b == "moon" else None)
                cache[b] = (ephem.refract(a), z)
            return cache[b]
        sun_alt, _ = aa("sun")
        ev = []
        for lm, v in vis:
            for b in ["sun", "moon", "mwcore", "orion", "pleiades", "cygnus"]:
                a, z = aa(b)
                dz = np.abs((z - v["az"] + 540) % 360 - 180)
                if b == "sun":
                    m = (dz < 0.6) & (a > v["alt"] - 0.5) & (a < v["alt"] + 1.2)
                elif b == "moon":
                    m = (dz < 0.8) & (a > v["alt"] - 0.4) & (a < v["alt"] + 2.5) & (G["illum"] > 0.25) & (sun_alt < 2) & (sun_alt > -14)
                else:
                    m = (dz < 3.0) & (a > v["alt"] + 0.5) & (a < v["alt"] + 12) & (sun_alt < -15)
                for i0, i1 in _runs(m):
                    k = i0 + int(np.argmin(dz[i0:i1 + 1]))
                    e = {"t": int(u[k] // 60), "dur": int((i1 - i0 + 1) * STEP / 60), "obj": b, "lm": lm["name"], "laz": r(v["az"], 1), "lalt": r(v["alt"], 2),
                         "alt": r(float(a[k]), 1), "daz": r(float((z[k] - v["az"] + 540) % 360 - 180), 2), "dkm": r(v["dkm"], 1)}
                    if b == "moon":
                        e["illum"] = r(float(G["illum"][k]) * 100, 0)
                        e["sun"] = r(float(sun_alt[k]), 1)
                    # 35mm-equivalent focal length on the X-T5 (APS-C 1.5x) to fill ~1/3 of the frame width with the landmark+object
                    span = max(1.5, abs(float(a[k]) - v["alt"]) * 3 + 1.0)
                    e["fl"] = int(min(300, max(16, 23.6 / (2 * math.tan(math.radians(span) / 2)))))
                    ev.append(e)
        # keep one event per object/landmark per night
        ev.sort(key=lambda e: e["t"])
        seen, keep = set(), []
        for e in ev:
            k = (e["obj"], e["lm"], e["t"] // (60 * 12))
            if k in seen:
                continue
            seen.add(k)
            keep.append(e)
        if keep:
            events[s["id"]] = keep[:200]
    write_json("planner.json", {"gen": iso(now), "events": events})
    return f"{sum(len(v) for v in events.values())} alignments at {len(events)} spots over {days} days"
