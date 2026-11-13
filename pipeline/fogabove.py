"""Fog-above finder for any viewpoint or summit. For the next two sunrises, reads the forecast cloud cover and height
at each pressure level (Open-Meteo, GFS/HRRR; keyless), finds the top of a low fog or stratus layer that starts near
the ground, and flags every viewpoint or peak that stands above it with clear air overhead — a sea of fog below.
Spot elevations come from Open-Meteo's terrain service (cached). Writes feed/fogabove.json; the app and alerts use it.
"""
import json, math, datetime as dt
from .common import http, read_json, write_json, spots, utcnow, iso, log, DATA, FEED
from .sunlite import sun_times

LEV = [1000, 975, 950, 925, 900, 850, 800, 700]
ELEV = DATA / "elev.json"
VIEW_CATS = {"vista", "mountain"}
FOG_SPOTS = {"cape-horn-lookout", "womens-forum", "vista-house", "jonsrud", "angels-rest", "larch-mtn"}


def _candidates():
    out = [s for s in spots() if VIEW_CATS & set(s.get("cats", [])) or s["id"] in FOG_SPOTS]
    idx = read_json(FEED / "seed" / "index.json", {"tiles": {}})
    # starter spots only in tiles near the researched spots: nationwide it is tens of thousands of points and the
    # hourly run never finishes (it timed out from Nov 9 to 13 and took birds + HRRR down with it)
    near = {f"{la}_{lo}" for r in out for la in range(int(r["lat"] // 1) - 1, int(r["lat"] // 1) + 2) for lo in range(int(r["lon"] // 1) - 1, int(r["lon"] // 1) + 2)}
    for k in idx["tiles"]:
        if k not in near: continue
        out += [s for s in read_json(FEED / "seed" / f"{k}.json", {"spots": []})["spots"] if s.get("kind") in ("viewpoint", "peak")]
    return out


def _elev(sp):
    cache = read_json(ELEV, {})
    need = [s for s in sp if s["id"] not in cache]
    for i in range(0, len(need), 100):
        ch = need[i:i + 100]
        try:
            j = http("https://api.open-meteo.com/v1/elevation", params={"latitude": ",".join(str(s["lat"]) for s in ch), "longitude": ",".join(str(s["lon"]) for s in ch)}, timeout=60).json()
            for s, e in zip(ch, j.get("elevation", [])):
                cache[s["id"]] = e
        except Exception as e:
            log.warning("elevation: %s", e)
    ELEV.write_text(json.dumps(cache, separators=(",", ":")))
    return cache


def judge(z_spot, z, cc, vis=None, ground=None):
    """z, cc: heights (m) and cloud cover (%) per level, bottom up; vis: surface visibility (m) at the cell; ground: cell
    elevation (m). Returns (top_m, p) or None. Valley fog is often thinner than the gap between pressure levels, so a
    foggy surface (visibility < 1.5 km) under clear upper levels counts as a shallow (~250 m) layer."""
    lv = [(zz, c) for zz, c in zip(z, cc) if zz is not None and c is not None]
    if len(lv) < 4:
        return None
    if vis is not None and vis < 1500 and ground is not None:
        top = ground + 250
        above = [c for zz, c in lv if zz > z_spot]
        if z_spot - top >= 100 and not (above and max(above[:3]) > 40):
            return round(top), 60
    # the layer must start at the lowest levels below the spot
    low = [i for i, (zz, c) in enumerate(lv) if zz < z_spot - 100]
    if not low or lv[low[0]][1] < 70:
        return None
    top_i = low[0]
    while top_i + 1 < len(lv) and lv[top_i + 1][1] >= 70:
        top_i += 1
    top = lv[top_i][0] if top_i + 1 >= len(lv) else (lv[top_i][0] + lv[top_i + 1][0]) / 2
    margin = z_spot - top
    above = [c for zz, c in lv if zz > z_spot]
    if margin < 60 or (above and max(above[:3]) > 40):
        return None
    return round(top), (82 if margin >= 200 else 68)


def run():
    sp = _candidates()
    el = _elev(sp)
    cells = {}
    for s in sp:
        if el.get(s["id"]) is None:
            continue
        cells.setdefault((round(s["lat"], 1), round(s["lon"], 1)), []).append(s)
    keys = list(cells)
    hourly = ",".join([f"cloud_cover_{l}hPa" for l in LEV] + [f"geopotential_height_{l}hPa" for l in LEV] + ["visibility"])
    today = utcnow().date()
    found, n_cells = {}, 0
    for i in range(0, len(keys), 40):
        ch = keys[i:i + 40]
        try:
            j = http("https://api.open-meteo.com/v1/forecast", params={"latitude": ",".join(str(k[0]) for k in ch), "longitude": ",".join(str(k[1]) for k in ch),
                     "hourly": hourly, "models": "gfs_seamless", "forecast_days": 3, "timezone": "GMT"}, timeout=120).json()
        except Exception as e:
            log.warning("fogabove forecast: %s", e)
            continue
        for k, r in zip(ch, j if isinstance(j, list) else [j]):
            n_cells += 1
            h = r.get("hourly") or {}
            times = h.get("time", [])
            for d in (today, today + dt.timedelta(days=1), today + dt.timedelta(days=2)):
                rise, _ = sun_times(k[0], k[1], d)
                if not rise or rise < utcnow():
                    continue
                key = (rise + dt.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:00")
                if key not in times:
                    continue
                ti = times.index(key)
                z = [h.get(f"geopotential_height_{l}hPa", [None] * len(times))[ti] for l in LEV]
                cc = [h.get(f"cloud_cover_{l}hPa", [None] * len(times))[ti] for l in LEV]
                vis = (h.get("visibility") or [None] * len(times))[ti]
                for s in cells[k]:
                    res = judge(el[s["id"]], z, cc, vis, r.get("elevation"))
                    if res:
                        found.setdefault(s["id"], []).append({"t": iso(rise), "top": res[0], "elev": round(el[s["id"]]), "p": res[1]})
    write_json("fogabove.json", {"gen": iso(utcnow()), "spots": found, "note": "Viewpoints above a forecast low fog/stratus layer at sunrise (GFS/HRRR via Open-Meteo)."})
    return f"{len(sp)} viewpoints in {n_cells} cells; {len(found)} above the fog in the next two sunrises"
