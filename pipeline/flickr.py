"""Originality from Flickr (MEASURED: what other people uploaded; ESTIMATED: what that implies).

For each spot: geotagged photos within ~400 m (10 years). We report
  - where people stand: 40 m grid cells ranked by photo count
  - when they shoot: share of photos by light window (sun altitude at the capture time) and by month
  - under-shot windows: windows whose share of photos is far below the share of good light the spot gets
  - quiet months: in-season months with almost no uploads
Direction of view is only known when a photo's EXIF carries GPSImgDirection, which is rare; we do not guess it.
Needs FLICKR_KEY.
"""
import datetime as dt, math, json
import numpy as np
from zoneinfo import ZoneInfo
from .common import http, spots, landmarks, write_json, CACHE, log, utcnow, iso, r, secret, km, bearing
from . import ephem

LA = ZoneInfo("America/Los_Angeles")
API = "https://api.flickr.com/services/rest/"


def search(key, s, rad_km=0.4, pages=4, extra=None):
    d = rad_km / 111.2
    dl = d / math.cos(math.radians(s["lat"]))
    out = []
    for p in range(1, pages + 1):
        params = {"method": "flickr.photos.search", "api_key": key, "bbox": f'{s["lon"]-dl},{s["lat"]-d},{s["lon"]+dl},{s["lat"]+d}',
                  "has_geo": 1, "extras": "geo,date_taken,url_q,owner_name", "per_page": 250, "page": p, "format": "json", "nojsoncallback": 1,
                  "min_taken_date": f"{utcnow().year-10}-01-01", "content_types": 0, "sort": "date-taken-desc"}
        params.update(extra or {})
        j = http(API, params=params).json()
        ph = j.get("photos", {}).get("photo", [])
        out += ph
        if p >= int(j.get("photos", {}).get("pages", 1)):
            break
    return out


def window_kind(sun_alt):
    if sun_alt < -12:
        return "night"
    if sun_alt < -4:
        return "blue"
    if sun_alt < 8:
        return "golden"
    return "day"


def run():
    key = secret("FLICKR_KEY")
    if not key:
        raise RuntimeError("FLICKR_KEY not set")
    ts, eph = ephem.load()
    out = {}
    for s in spots():
        try:
            ph = search(key, s)
        except Exception as e:
            log.warning("flickr %s: %s", s["id"], e)
            continue
        if len(ph) < 15:
            out[s["id"]] = {"n": len(ph)}
            continue
        t_local, lat, lon = [], [], []
        for p in ph:
            try:
                t = dt.datetime.strptime(p["datetaken"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=LA)
            except Exception:
                continue
            t_local.append(t); lat.append(float(p["latitude"])); lon.append(float(p["longitude"]))
        u = np.array([t.timestamp() for t in t_local])
        tt = ephem.ts_unix(u)
        ra, dec, _ = ephem.radec("sun", tt)
        alt, _ = ephem.altaz(ra, dec, ephem.gast_deg(tt), s["lat"], s["lon"])
        kinds = [window_kind(a) for a in alt]
        share = {k: round(100 * kinds.count(k) / len(kinds)) for k in ("golden", "blue", "night", "day")}
        months = np.bincount([t.month - 1 for t in t_local], minlength=12)
        # opportunity share: fraction of daylight-ish hours in each window kind over a year (rough baseline)
        base = {"golden": 14, "blue": 8, "night": 0, "day": 78} if "night" not in s["cats"] else {"golden": 10, "blue": 6, "night": 30, "day": 54}
        under = [k for k in ("blue", "night", "golden") if base[k] >= 6 and share[k] < base[k] * 0.5]
        # standing cells (40 m)
        cy = np.round((np.array(lat) - s["lat"]) * 111200 / 40).astype(int)
        cx = np.round((np.array(lon) - s["lon"]) * 111200 * math.cos(math.radians(s["lat"])) / 40).astype(int)
        cells = {}
        for a, b in zip(cy, cx):
            cells[(a, b)] = cells.get((a, b), 0) + 1
        top = sorted(cells.items(), key=lambda kv: -kv[1])[:5]
        stand = [{"lat": r(s["lat"] + a * 40 / 111200, 5), "lon": r(s["lon"] + b * 40 / (111200 * math.cos(math.radians(s["lat"]))), 5), "n": n} for (a, b), n in top]
        quiet_months = [m + 1 for m in range(12) if s.get("months") and (m + 1) in s["months"] and months[m] <= max(1, months.sum() * 0.03)]
        out[s["id"]] = {"n": len(t_local), "share": share, "months": months.tolist(), "stand": stand, "under": under, "quiet_months": quiet_months,
                        "top_share": round(100 * top[0][1] / len(t_local)) if top else None}
    write_json("originality.json", {"gen": iso(utcnow()), "spots": out,
                                    "note": "Flickr geotagged photos within 400 m, last 10 years. Standing spots are 40 m cells; view direction is not inferred."})
    return f"{len(out)} spots"


def same_day(key, lat, lon, date):
    """Photos taken near a point on a date (for outcome verification)."""
    s = {"lat": lat, "lon": lon}
    ph = search(key, s, rad_km=1.5, pages=1, extra={"min_taken_date": f"{date} 00:00:00", "max_taken_date": f"{date} 23:59:59", "sort": "date-taken-asc"})
    return [{"t": p.get("datetaken"), "url": f'https://www.flickr.com/photos/{p["owner"]}/{p["id"]}', "thumb": p.get("url_q")} for p in ph[:12]]


def top_photos(per_spot=8):
    """Most interesting Flickr photos within 500 m of each spot (link + thumbnail + owner), for the spot page.
    Shown with credit and a link back to Flickr, as the Flickr API terms require."""
    from .common import secret, spots, write_json, http, utcnow, iso
    key = secret("FLICKR_KEY")
    if not key:
        return "no FLICKR_KEY"
    out = {}
    for s in spots():
        try:
            j = http("https://api.flickr.com/services/rest/", params={"method": "flickr.photos.search", "api_key": key, "lat": s["lat"], "lon": s["lon"],
                     "radius": 0.5, "radius_units": "km", "sort": "interestingness-desc", "content_type": 1, "media": "photos", "safe_search": 1,
                     "extras": "owner_name,url_m,url_b,license", "per_page": per_spot, "format": "json", "nojsoncallback": 1}, timeout=30).json()
        except Exception:
            continue
        ph = [p for p in j.get("photos", {}).get("photo", []) if p.get("url_m")]
        if ph:
            out[s["id"]] = [{"thumb": p["url_m"], "big": p.get("url_b") or p["url_m"], "page": f"https://www.flickr.com/photos/{p['owner']}/{p['id']}", "title": p.get("title", ""), "by": p.get("ownername", "")} for p in ph]
    write_json("photos.json", {"gen": iso(utcnow()), "spots": out})
    return f"Flickr top photos for {len(out)} spots"
