"""Night-sky darkness and glow direction from VIIRS (NASA Black Marble VNP46A4 annual composite).

Radiance (nW/cm2/sr, snow-free near-nadir composite, 15 arcsec) is MEASURED by satellite. Sky brightness at
each spot is MODELED: every lit pixel within 200 km contributes radiance x area x K(d), with
K(d) = d^-2.3 * exp(-d/150 km) (Walker/Garstang-style falloff). The single scale constant is fitted to
measured SQM readings: your own (from outcomes) once you have 3+, otherwise four reference values from the
World Atlas-based light pollution map, which are themselves modeled. Glow by direction sums the same
contributions into 16 compass sectors with a d^-2 horizon kernel.
Needs EARTHDATA_TOKEN (free NASA Earthdata login).
"""
import json, math, re
import numpy as np
from .common import http, spots, write_json, read_json, CACHE, CONFIG, log, utcnow, iso, r, secret

LAADS = "https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/VNP46A4"
TILES = ["h05v04", "h06v04"]  # 120-130 W and 110-120 W, 40-50 N
REF = {"home": (45.582, -122.353, 19.66), "capehorn": (45.60, -122.19, 21.21), "washougalrd": (45.69, -122.13, 21.56), "larch": (45.53, -122.088, 21.53)}


def fetch_tile(year, tile, token):
    p = CACHE / f"vnp46a4_{year}_{tile}.npy"
    if p.exists():
        return np.load(p)
    lst = http(f"{LAADS}/{year}/001.json", headers={"Authorization": f"Bearer {token}"}).json()
    items = lst.get("content", lst) if isinstance(lst, dict) else lst
    name = next(x["name"] for x in items if tile in x["name"])
    import h5py, io
    b = http(f"{LAADS}/{year}/001/{name}", headers={"Authorization": f"Bearer {token}"}, timeout=600).content
    with h5py.File(io.BytesIO(b), "r") as f:
        dsn = next(k for k in _walk(f) if k.endswith("NearNadir_Composite_Snow_Free"))
        a = f[dsn][()].astype(np.float32)
        fill = f[dsn].attrs.get("_FillValue", 65535)
        scale = float(np.atleast_1d(f[dsn].attrs.get("scale_factor", 0.1))[0])
    a = np.where(a == fill, 0, a * scale)
    np.save(p, a)
    return a


def _walk(f, pre=""):
    for k in f:
        path = f"{pre}/{k}"
        if hasattr(f[k], "keys"):
            yield from _walk(f[k], path)
        else:
            yield path


def mosaic(token):
    year = utcnow().year - 1
    arrs = None
    for y in (year, year - 1):
        try:
            arrs = [fetch_tile(y, t, token) for t in TILES]
            break
        except Exception as e:
            log.warning("VNP46A4 %s: %s", y, e)
    if arrs is None:
        raise RuntimeError("no VNP46A4 tiles")
    a = np.hstack(arrs)  # 2400 x 4800, lat 50->40, lon -130 -> -110
    # crop to 43.5-48 N, 125.5-118.5 W and downsample 3x (~1.4 x 0.95 km)
    res = 10 / 2400
    r0, r1 = int((50 - 48) / res), int((50 - 43.5) / res)
    c0, c1 = int((-125.5 + 130) / res), int((-118.5 + 130) / res)
    a = a[r0:r1, c0:c1]
    h, w = a.shape[0] // 3 * 3, a.shape[1] // 3 * 3
    a = a[:h, :w].reshape(h // 3, 3, w // 3, 3).mean((1, 3))
    return a, (48.0, -125.5, res * 3)


def contributions(a, geo, lat, lon, kexp=2.3, ext=150.0):
    top, left, step = geo
    rows = top - (np.arange(a.shape[0]) + 0.5) * step
    cols = left + (np.arange(a.shape[1]) + 0.5) * step
    LA, LO = np.meshgrid(rows, cols, indexing="ij")
    dy = (LA - lat) * 111.2
    dx = (LO - lon) * 111.2 * math.cos(math.radians(lat))
    d = np.hypot(dx, dy)
    area = (step * 111.2) ** 2 * np.cos(np.radians(LA))
    m = (d < 200) & (a > 0.5)
    d = np.maximum(d[m], 0.7)
    w = a[m] * area[m]
    zen = float(np.sum(w * d ** -kexp * np.exp(-d / ext)))
    az = (np.degrees(np.arctan2(dx[m], dy[m])) + 360) % 360
    hor = w * d ** -2.0 * np.exp(-d / ext)
    sectors = np.bincount(((az + 11.25) // 22.5).astype(int) % 16, weights=hor, minlength=16)
    return zen, sectors


def run():
    tok = secret("EARTHDATA_TOKEN")
    if not tok:
        raise RuntimeError("EARTHDATA_TOKEN not set")
    a, geo = mosaic(tok)
    # calibration: user's SQM readings (written by verify.py) take priority over reference values
    cal = read_json(CONFIG / "sqm_readings.json", [])
    refs = [(c["lat"], c["lon"], c["sqm"]) for c in cal] if len(cal) >= 3 else list(REF.values())
    zs = [contributions(a, geo, la, lo)[0] for la, lo, _ in refs]
    # fit SQM = 22.0 - 2.5 log10(1 + C z) by grid search on C
    best = None
    for lc in np.linspace(-6, 3, 361):
        C = 10 ** lc
        err = sum((22.0 - 2.5 * math.log10(1 + C * z) - q) ** 2 for z, (_, _, q) in zip(zs, refs))
        if best is None or err < best[0]:
            best = (err, C)
    C = best[1]
    rmse = math.sqrt(best[0] / len(refs))
    out = {}
    for s in spots():
        if not (44.5 < s["lat"] < 47.0 and -124.5 < s["lon"] < -119.5):  # mosaic covers 43.5-48 N, 125.5-118.5 W; keep 1 deg margin
            continue
        z, sec = contributions(a, geo, s["lat"], s["lon"])
        q = 22.0 - 2.5 * math.log10(1 + C * z)
        tot = sec.sum() or 1
        out[s["id"]] = {"sqm": r(min(q, 21.99), 2), "glow16": [int(round(100 * x / tot)) for x in sec], "darkest": int(np.argmin(sec)) * 22.5, "brightest": int(np.argmax(sec)) * 22.5}
    write_json("darksky.json", {"gen": iso(utcnow()), "calibration": {"C": C, "rmse_mag": round(rmse, 2), "n": len(refs), "source": "your SQM readings" if len(cal) >= 3 else "light-pollution-map reference values"},
                                "spots": out, "note": "VIIRS Black Marble radiance -> modeled zenith SQM and 16-sector horizon glow shares (% of total glow)."})
    return f"{len(out)} spots, calibration rmse {rmse:.2f} mag on {len(refs)} refs"
