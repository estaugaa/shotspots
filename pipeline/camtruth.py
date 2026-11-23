"""Webcams as ground truth for the score, every day, without waiting for outing logs.

Public road cameras (Oregon TripCheck, Caltrans; no keys) are photographed around every sunrise and sunset. For each frame:
  sky_warm  share of the sky band (upper image) in warm, saturated colour (red/orange/pink): did the sky light up?
  land_warm share of the land band (lower image) in warm colour: was there golden light on the land?
  sky_blue, sky_grey, sky_v: blue sky / grey cloud / brightness, for sanity
At the same time the forecast cloud layers for that spot and for a point 60 km toward the sun are saved, so the app's
sky formula can be recomputed later with any weights (fit()).
fit(): over the last 30 days, how well does the formula's sky score rank the real colour (Spearman), what the best
weights would be (grid search), and how much golden light the land gets on clear vs cloudy evenings.
-> data/archive/camtruth/<month>.csv.gz (kept indefinitely), feed/camtruth.json. MEASURED (camera pixels) vs MODELED (forecast + formula).
Caveats: road cameras point along roads, not always toward the sun; overlays and headlights are cropped out roughly.
Since Nov 23 also ALERTCalifornia's ridge-top cameras (UC San Diego, CC BY-NC-ND 4.0, credit "ALERTCalifornia | UC San
Diego"): they publish each camera's live heading and tilt, so only frames looking toward the sun (within 50 degrees) and
near the horizon are taken; face = degrees between the camera's heading and the sun. Only numbers are kept from their
frames (no thumbnails: no derivatives, and the data branch is public). Road-camera frames are all thumbnailed (14 days)
so pipeline/imagerate.py can rate them.
"""
import io, json, math, time, csv, colorsys, hashlib, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import requests
from .common import soft_fail, DATA, FEED, log, write_json, iso, utcnow, read_json
from .sunlite import sun_times, sun_az

D = DATA / "camtruth"; INV = DATA / "cams_inventory.json"
H = {"User-Agent": "ShotSpots/1.0 (photo-planning research; github.com/estaugaa/shotspots)"}
FIELDS = ["date", "cam", "src", "lat", "lon", "event", "min", "sky_warm", "land_warm", "sky_blue", "sky_grey", "sky_v",
          "low", "mid", "high", "pop", "p_low", "p_mid"]
NUM = FIELDS[6:]
FIELDS = FIELDS + ["t", "mv", "h", "face"]   # capture time (UTC); colour-measure version; image hash (frozen feeds repeat it); degrees off the sun (ridge cameras)
AC = "https://cameras.alertcalifornia.org/public-camera-data/"
THUMB_DAYS = 14
MV = 2   # Nov 21: v1 counted LED signs, tail lights and street lights as sunset colour


def _archive(rows):
    """Frames go to data/archive/camtruth/<month>.csv.gz, kept indefinitely. The daily data/camtruth/<date>.csv files
    this replaced are moved in once, then removed."""
    from . import archive
    old = sorted(D.glob("20*.csv"))
    for p in old:
        with open(p) as fh: rows = list(csv.DictReader(fh)) + rows
    archive.append("camtruth", FIELDS, rows, lambda r: r["date"], lambda r: (r["date"], r["cam"], r["event"]))
    for p in old: p.unlink()


def inventory(force=False):
    inv = read_json(INV, None)
    if inv and not force and inv.get("at", "") > iso(utcnow() - dt.timedelta(days=7)): return inv["cams"]
    cams = []
    try:   # Oregon TripCheck
        t = requests.get("https://tripcheck.com/Scripts/map/data/cctvinventory.js", headers=H, timeout=60).text
        for f in json.loads(t[t.index("{"):t.rindex("}") + 1]).get("features", []):
            a = f.get("attributes") or {}; g = f.get("geometry") or {}
            la, lo, fn = a.get("latitude") or g.get("y"), a.get("longitude") or g.get("x"), a.get("filename")
            if la and fn: cams.append({"id": f"or{a.get('cameraId')}", "src": "or", "lat": round(float(la), 4), "lon": round(float(lo), 4), "url": f"https://tripcheck.com/RoadCams/cams/{fn}"})
    except Exception as e:
        log.warning("camtruth TripCheck: %s", e)
    for d in range(1, 13):   # Caltrans districts
        try:
            j = requests.get(f"https://cwwp2.dot.ca.gov/data/d{d}/cctv/cctvStatusD{d:02d}.json", headers=H, timeout=60).json()
            for x in j.get("data", []):
                c = x.get("cctv") or {}; loc = c.get("location") or {}; u = (((c.get("imageData") or {}).get("static") or {}).get("currentImageURL"))
                if u and c.get("inService") == "true" and loc.get("latitude"):
                    cams.append({"id": f"ca{c.get('index') or loc.get('locationName')}", "src": "ca", "lat": round(float(loc["latitude"]), 4), "lon": round(float(loc["longitude"]), 4), "url": u})
        except Exception as e:
            log.warning("camtruth Caltrans d%d: %s", d, e)
        time.sleep(0.5)
    try:   # ALERTCalifornia ridge-top cameras (heading checked live at capture)
        for f in requests.get(AC + "all_cameras-v3.json", headers=H, timeout=60).json().get("features", []):
            pr, (lo, la) = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates", [None, None])[:2]
            if pr.get("id") and la:
                cams.append({"id": f"ac{pr['id']}", "src": "ac", "lat": round(float(la), 4), "lon": round(float(lo), 4), "url": f"{AC}{pr['id']}/latest-thumb.jpg"})
    except Exception as e:
        log.warning("camtruth ALERTCalifornia: %s", e)
    write_json(INV, {"at": iso(utcnow()), "cams": cams})
    return cams


def metrics(img_bytes):
    from PIL import Image
    from PIL import ImageFilter, ImageStat
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB"); im.thumbnail((160, 120))
    st = ImageStat.Stat(im.convert("L"))
    if st.stddev[0] < 14 or st.mean[0] > 225: return None   # blank, or an "image unavailable" placeholder
    W, Hh = im.size; px = im.load(); pb = im.filter(ImageFilter.BoxBlur(3)).load()
    # Does the "sky band" show sky? Road cameras often frame hills or buildings there. Sky at dawn/dusk is clearly brighter
    # than the road (>= 25 levels) and not featureless (fog and headlight glare are, texture < 4). Nov 21: on 13 hand-checked
    # frames this kept all 4 real sunsets and dropped 8 of 9 impostors (a desert hillside got through).
    g = im.convert("L"); ga, gb = g.load(), g.filter(ImageFilter.BoxBlur(2)).load()
    xs = range(int(W * 0.04), int(W * 0.96)); sr = range(int(Hh * 0.12), int(Hh * 0.40)); lr = range(int(Hh * 0.55), int(Hh * 0.86))
    tex = sum(abs(ga[x, y] - gb[x, y]) for y in sr for x in xs) / (len(xs) * len(sr))
    sky_minus_land = sum(ga[x, y] for y in sr for x in xs) / (len(xs) * len(sr)) - sum(ga[x, y] for y in lr for x in xs) / (len(xs) * len(lr))
    if sky_minus_land < 25 or tex < 4: return None
    # Sunset colour is a broad, smooth glow. Point lights, LED signs and road paint are small and sharp: a pixel counts as
    # warm only if it is close to its blurred neighbourhood (Nov 21 review: a "WATCH FOR FLOODING" sign scored 88)
    def smooth(x, y): a, b = px[x, y], pb[x, y]; return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])) < 36
    def band(y0, y1):
        warm = blue = grey = n = 0; vs = 0.0
        for y in range(int(Hh * y0), int(Hh * y1)):
            for x in range(int(W * 0.04), int(W * 0.96)):
                r, g, b = (c / 255 for c in px[x, y]); h, s_, v = colorsys.rgb_to_hsv(r, g, b); hd = h * 360; n += 1; vs += v
                if 0.18 <= s_ <= 0.62 and v >= 0.4 and (8 <= hd <= 50 or 290 <= hd <= 345) and smooth(x, y): warm += 1   # lit sky glow, not red lights, neon or brown hills
                elif s_ >= 0.2 and 180 <= hd <= 250: blue += 1
                elif s_ < 0.12 and v >= 0.25: grey += 1
        return warm / max(1, n), blue / max(1, n), grey / max(1, n), vs / max(1, n)
    sw, sb, sg, sv = band(0.12, 0.40)   # skip the title/overlay strip at the top
    lw, _, _, _ = band(0.55, 0.86)      # skip the caption strip at the bottom
    return round(sw * 100, 1), round(lw * 100, 1), round(sb * 100, 1), round(sg * 100, 1), round(sv, 3)


def _thumbs(got, now):
    """Small thumbnails of every road-camera frame (kept THUMB_DAYS), for checking by eye and for imagerate.py. None of the
    ridge cameras' frames (their licence allows no derivatives; the data branch is public)."""
    import re as _re, shutil
    from PIL import Image
    td = D / "thumbs" / str(now.date()); td.mkdir(parents=True, exist_ok=True)
    for old in (D / "thumbs").glob("20*"):
        if old.name < str(now.date() - dt.timedelta(days=THUMB_DAYS)): shutil.rmtree(old, ignore_errors=True)
    for (c, ev, m, key), mt, img in got:
        if c["src"] != "ac":
            try:
                im = Image.open(io.BytesIO(img)).convert("RGB"); im.thumbnail((200, 150))
                im.save(td / f"{_re.sub(r'[^A-Za-z0-9]', '', c['id'])}_{ev}_{m:+d}_sw{int(mt[0])}.jpg", quality=65)
            except Exception as e:
                log.info("thumb %s: %s", c["id"], e)


def _forecast(pts):
    """Current-hour low/mid/high cloud and rain chance for many points (Open-Meteo, 50 a request)."""
    out = []
    for i in range(0, len(pts), 50):
        ch = pts[i:i + 50]
        p = {"latitude": ",".join(f"{a:.3f}" for a, _ in ch), "longitude": ",".join(f"{b:.3f}" for _, b in ch),
             "current": "cloud_cover_low,cloud_cover_mid,cloud_cover_high,precipitation_probability", "timezone": "UTC"}
        j = None
        for k in range(3):
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params=p, timeout=60)
                if r.ok: j = r.json(); break
                if r.status_code == 429: time.sleep(61)
            except Exception: time.sleep(5)
        j = j if isinstance(j, list) else [j] if j else [None] * len(ch)
        for x in j:
            c = (x or {}).get("current") or {}
            out.append((c.get("cloud_cover_low"), c.get("cloud_cover_mid"), c.get("cloud_cover_high"), c.get("precipitation_probability")))
        time.sleep(1.5)
    return out


def _toward(lat, lon, az, km=60):
    d = km / 6371; a = math.radians(az); la1, lo1 = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(a))
    lo2 = lo1 + math.atan2(math.sin(a) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2))
    return math.degrees(la2), math.degrees(lo2)


def _ridge_facing(due, now):
    """Keep ALERTCalifornia frames only where the camera looks toward the sun (within 50 degrees), near the horizon (tilt
    -15..+10) and its picture is fresh (last frame within 15 minutes); heading and tilt are read live (the cameras pan)."""
    try:
        live = {f"ac{f['properties']['id']}": f["properties"] for f in requests.get(AC + "all_cameras-v3.json", headers=H, timeout=60).json().get("features", [])}
    except Exception as e:
        soft_fail("camtruth: ALERTCalifornia headings", e)
        return [d for d in due if d[0]["src"] != "ac"]
    out = []
    for c, ev, m, key in due:
        if c["src"] != "ac":
            out.append((c, ev, m, key)); continue
        p = live.get(c["id"]) or {}
        az, tilt, ts = p.get("az_current"), p.get("tilt_current"), p.get("last_frame_ts") or 0
        if az is None or tilt is None or not (-15 <= tilt <= 10) or now.timestamp() - ts > 900:
            continue
        off = abs((az - sun_az(c["lat"], c["lon"], now) + 180) % 360 - 180)
        if off <= 50:
            out.append((dict(c, face=round(off)), ev, m, key))
    return out


def capture(max_n=400):
    cams = inventory(); now = utcnow(); state = read_json(D / "state.json", {}) or {}
    due = []
    for c in cams:
        evs = []
        for day in (now.date() - dt.timedelta(days=1), now.date()):   # western sunsets fall after midnight UTC
            evs += list(zip(("sunrise", "sunset"), sun_times(c["lat"], c["lon"], day) or (None, None)))
        for ev, t in evs:
            if not t: continue
            m = (now - t).total_seconds() / 60
            ok = (-25 <= m <= 10) if ev == "sunrise" else (-5 <= m <= 25)   # colour comes before sunrise / after sunset
            key = f"{c['id']}|{t.date()}|{ev}"
            if ok and key not in state: due.append((c, ev, round(m), key))
    if any(c["src"] == "ac" for c, *_ in due):
        due = _ridge_facing(due, now)
    due.sort(key=lambda d: d[0]["src"] != "ac")   # sun-facing ridge cameras first
    due = due[:max_n]
    if not due: return 0
    def grab(item):
        c, ev, m, key = item
        try:
            r = requests.get(c["url"], headers=H, timeout=25)
            if not r.ok or not r.headers.get("content-type", "").startswith("image"): return None
            mt = metrics(r.content)
            return (item, mt, r.content) if mt else None
        except Exception as e:
            soft_fail("camtruth: webcam fetch or metrics failed", e)
            return None
    with ThreadPoolExecutor(12) as ex: got = [g for g in ex.map(grab, due) if g]
    got = [(it, mt, img) for it, mt, img in got if mt[4] >= 0.18]   # too dark to judge: past dusk, the colour is mostly artificial light
    _thumbs(got, now)
    got = [(it, mt, hashlib.md5(img).hexdigest()[:10]) for it, mt, img in got]
    pts = []
    for (c, ev, m, key), _, _h in got:
        az = sun_az(c["lat"], c["lon"], now)   # the probe point toward the sun (was a fixed 120 / 240 degrees)
        pts += [(c["lat"], c["lon"]), _toward(c["lat"], c["lon"], az)]
    fc = _forecast(pts)
    rows = []
    for i, ((c, ev, m, key), mt, hh) in enumerate(got):
        here, probe = fc[2 * i] if 2 * i < len(fc) else (None,) * 4, fc[2 * i + 1] if 2 * i + 1 < len(fc) else (None,) * 4
        rows.append(dict(zip(FIELDS, [now.date(), c["id"], c["src"], c["lat"], c["lon"], ev, m, *mt, here[0], here[1], here[2], here[3], probe[0], probe[1], iso(now), MV, hh, c.get("face", "")])))
        state[key] = 1
    _archive(rows)
    for (c, ev, m, key) in due: state.setdefault(key, 0)   # tried (no image or too dark): don't retry this event
    cutoff = str(now.date() - dt.timedelta(days=2)); state = {k: v for k, v in state.items() if k.split("|")[1] >= cutoff}
    write_json(D / "state.json", state)
    return len(got)


def sky_q(low, mid, high, pop, p_low, p_mid, prm):
    """The app's sky colour score (app/app.js skyCalc), with weights prm."""
    canvas = max(mid, high * 0.9); cirrus = mid < 30 and high >= 70; fl = prm["canvasFloor"]
    f = fl if canvas < 10 else fl + (1 - fl) * min(1, (canvas - 10) / 40) if canvas <= 70 else 0.85 if cirrus else max(0.2, 1 - (canvas - 70) / 30 * 0.8)
    lowF = prm["lowDeck"] if low >= 75 else prm["lowBroken"] if low >= 45 else 1
    block = max(p_low, p_mid * 0.6) if p_low is not None else None
    g = 1 if block is None or block <= 30 else 0.72 if block <= 60 else 0.38
    q = 100 * f * lowF * g
    return 8 if (pop or 0) >= 60 else q


def _spearman(a, b):
    def rk(x):
        o = sorted(range(len(x)), key=lambda i: x[i]); r = [0.0] * len(x); i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and x[o[j + 1]] == x[o[i]]: j += 1
            for k in range(i, j + 1): r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = rk(a), rk(b); n = len(a)
    if n < 3: return None
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)); va = sum((x - ma) ** 2 for x in ra); vb = sum((y - mb) ** 2 for y in rb)
    return round(cov / math.sqrt(va * vb), 3) if va and vb else None


def fit():
    rows = []
    from . import archive
    _archive([])
    for r in archive.read("camtruth", str(utcnow().date() - dt.timedelta(days=30)), "date"):
        try:
            v = {k: archive.num(r.get(k)) for k in NUM}
            if None in (v["low"], v["mid"], v["high"]) or r.get("mv") != str(MV): continue   # only the current colour measure
            v["h"] = r.get("h")
            v["event"] = r["event"]; v["cam"] = r["cam"]; v["src"] = r.get("src") or ""; v["face"] = archive.num(r.get("face")); rows.append(v)
        except Exception as e:
            soft_fail("camtruth: webcam row skipped", e)
    seen = {}
    for v in rows: seen[(v["cam"], v["h"])] = seen.get((v["cam"], v["h"]), 0) + 1
    rows = [v for v in rows if seen[(v["cam"], v["h"])] == 1]   # a frame seen twice is a frozen or dead feed
    out = {"gen": iso(utcnow()), "n": len(rows), "measure": MV}
    if len(rows) < 30:
        write_json("camtruth.json", {**out, "note": "not enough frames yet"}); return out
    # cameras that show sky: some blue or grey sky in the sky band
    sky = [r for r in rows if r["sky_blue"] + r["sky_grey"] >= 25]
    # each camera against its own history (tinted lenses, streetlights, cameras that never see the horizon cancel out):
    # rel = this frame's warm colour minus that camera's median; used once a camera has 3+ frames
    from statistics import median
    per = {}
    for r in sky: per.setdefault(r["cam"], []).append(r["sky_warm"])
    rel = [dict(r, sky_warm=r["sky_warm"] - median(per[r["cam"]])) for r in sky if len(per[r["cam"]]) >= 3]
    out["n_relative"] = len(rel)
    out["n_sky"] = len(sky)
    DEF = {"canvasFloor": 0.32, "lowBroken": 0.85, "lowDeck": 0.4}
    def score(prm, rs): return _spearman([sky_q(r["low"], r["mid"], r["high"], r["pop"], r["p_low"], r["p_mid"], prm) for r in rs], [r["sky_warm"] for r in rs])
    out["spearman_default"] = score(DEF, sky)
    out["spearman_default_relative"] = score(DEF, rel) if len(rel) >= 30 else None
    out["spearman_old"] = score({"canvasFloor": 0.32, "lowBroken": 0.7, "lowDeck": 0.3}, sky)
    best = (None, -9)
    for cf in (0.2, 0.32, 0.45, 0.6):
        for lb in (0.5, 0.7, 0.85, 1.0):
            for ld in (0.2, 0.3, 0.4, 0.6):
                r = score({"canvasFloor": cf, "lowBroken": lb, "lowDeck": ld}, sky)
                if r is not None and r > best[1]: best = ({"canvasFloor": cf, "lowBroken": lb, "lowDeck": ld}, r)
    out["best"] = {"params": best[0], "spearman": best[1]}
    # golden light on the land: clear vs cloudy (justifies the "clear golden light" credit)
    def cls(r):
        cc = max(r["low"], r["mid"], r["high"])
        return "clear (<=30%)" if cc <= 30 else "partly (31-70%)" if cc <= 70 else "cloudy (>70%)"
    by = {}
    for r in sky: by.setdefault(cls(r), []).append(r)
    out["by_sky"] = {k: {"n": len(v), "sky_warm": round(sum(x["sky_warm"] for x in v) / len(v), 1), "land_warm": round(sum(x["land_warm"] for x in v) / len(v), 1)} for k, v in sorted(by.items())}
    # does colour rise with the formula's sky score? mean sky_warm by score band
    qs = [(sky_q(r["low"], r["mid"], r["high"], r["pop"], r["p_low"], r["p_mid"], DEF), r["sky_warm"]) for r in sky]
    bands = {}
    for q, sw in qs: bands.setdefault(min(4, int(q // 20)), []).append(sw)
    out["colour_by_score"] = {f"{b * 20}-{b * 20 + 19}": {"n": len(v), "sky_warm": round(sum(v) / len(v), 1)} for b, v in sorted(bands.items())}
    # by camera type, and ridge cameras looking toward the sun (the closest thing to a photographer's view)
    out["by_source"] = {src: {"n": len(g), "spearman": score(DEF, g) if len(g) >= 30 else None} for src in sorted({r["src"] for r in sky}) for g in [[r for r in sky if r["src"] == src]]}
    face = [r for r in sky if r.get("face") is not None and r["face"] <= 50]
    out["sun_facing"] = {"n": len(face), "spearman": score(DEF, face) if len(face) >= 30 else None,
                         "colour_by_score": {f"{b * 20}-{b * 20 + 19}": {"n": len(v), "sky_warm": round(sum(v) / len(v), 1)} for b, v in sorted(_bands(face, DEF).items())}}
    out["credit"] = "ridge cameras: ALERTCalifornia | UC San Diego (CC BY-NC-ND 4.0)"
    write_json("camtruth.json", out)
    return out


def _bands(rs, prm):
    b = {}
    for r in rs: b.setdefault(min(4, int(sky_q(r["low"], r["mid"], r["high"], r["pop"], r["p_low"], r["p_mid"], prm) // 20)), []).append(r["sky_warm"])
    return b


def run():
    n = capture()
    out = fit()
    return f"{n} frames captured now; {out.get('n', 0)} frames in the last 30 days ({out.get('n_sky', 0)} showing sky); Spearman default {out.get('spearman_default')}, old {out.get('spearman_old')}, best {(out.get('best') or {}).get('spearman')} with {(out.get('best') or {}).get('params')}"
