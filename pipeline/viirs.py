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

LAADS_C = ["https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5200/VNP46A4", "https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/VNP46A4"]  # collection 2 first
TILES = ["h05v04", "h06v04"]  # 120-130 W and 110-120 W, 40-50 N
REF = {"home": (45.582, -122.353, 19.66), "capehorn": (45.60, -122.19, 21.21), "washougalrd": (45.69, -122.13, 21.56), "larch": (45.53, -122.088, 21.53)}


def fetch_tile(year, tile, token):
    p = CACHE / f"vnp46a4_{year}_{tile}.npy"
    if p.exists():
        return np.load(p)
    lst, LAADS = None, None
    for base in LAADS_C:
        try:
            lst = http(f"{base}/{year}/001.json", headers={"Authorization": f"Bearer {token}"}, tries=2).json()
            LAADS = base
            break
        except Exception as e:
            log.info("VNP46A4 %s %s: %s", base.split("/")[-2], year, e)
    if lst is None:
        raise RuntimeError(f"no VNP46A4 listing for {year}")
    items = lst.get("content", lst) if isinstance(lst, dict) else lst
    name = next(x["name"] for x in items if tile in x["name"])
    import h5py, io
    r = http(f"{LAADS}/{year}/001/{name}", headers={"Authorization": f"Bearer {token}"}, timeout=600)
    b = r.content
    if not b.startswith(b"\x89HDF"):
        raise RuntimeError(f"download of {name} returned {r.headers.get('content-type')} from {r.url[:220]} ({len(b)} bytes): {b[:160]!r}")
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
    for y in (year, year - 1, year - 2):
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


# ---------- national grid ----------
# Same physics as the per-spot model, run once a year over the lower 48 on a ~4.6 km grid with an FFT, then
# shipped at 1/8 degree so the app can rate the sky anywhere. Values are calibrated on the same reference SQMs.
NAT_H, NAT_V = range(5, 12), range(4, 7)        # VNP46A4 tiles: 130-60 W, 20-50 N
DS = 10                                          # 2400 px/tile -> 240 cells (1/24 degree)
ALPHA = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"   # 0.1 mag steps from 16.0


def _small_tile(year, tile, token):
    p = CACHE / f"vnp46a4s_{year}_{tile}.npy"
    if p.exists():
        return np.load(p)
    full = CACHE / f"vnp46a4_{year}_{tile}.npy"
    keep = full.exists()
    try:
        a = fetch_tile(year, tile, token)
    except StopIteration:      # all-ocean tile: no file in the listing
        a = np.zeros((2400, 2400), np.float32)
    a = np.where(a > 0.5, a, 0).reshape(240, DS, 240, DS).mean((1, 3)).astype(np.float32)
    np.save(p, a)
    if not keep and full.exists() and tile not in TILES:
        full.unlink()          # national tiles: keep only the downsampled copy in the cache
    return a


def _fftconv(a, k):
    sh = (a.shape[0] + k.shape[0] - 1, a.shape[1] + k.shape[1] - 1)
    out = np.fft.irfft2(np.fft.rfft2(a, sh) * np.fft.rfft2(k, sh), sh)
    r0, c0 = k.shape[0] // 2, k.shape[1] // 2
    return out[r0:r0 + a.shape[0], c0:c0 + a.shape[1]]


def national(force=False):
    old = read_json(__import__("pathlib").Path("feed") / "darkgrid.json", None)
    if old and not force and (utcnow() - __import__("datetime").datetime.fromisoformat(old["gen"].replace("Z", "+00:00"))).days < 150:
        return "fresh (annual data); skipped"
    tok = secret("EARTHDATA_TOKEN")
    if not tok:
        raise RuntimeError("EARTHDATA_TOKEN not set")
    year = utcnow().year - 1
    for y in (year, year - 1, year - 2):
        try:
            rows = [np.hstack([_small_tile(y, f"h{h:02d}v{v:02d}", tok) for h in NAT_H]) for v in NAT_V]
            break
        except Exception as e:
            log.warning("national VNP46A4 %s: %s", y, e)
    else:
        raise RuntimeError("no national VNP46A4 tiles")
    a = np.vstack(rows)                     # lat 50 -> 20, lon -130 -> -60, 1/24 degree
    step = 10 / 240
    lat = 50 - (np.arange(a.shape[0]) + 0.5) * step
    zen = np.zeros_like(a)
    for band_lat in (25, 35, 45):           # longitude spacing shrinks with latitude: one kernel per band
        ky = step * 111.2; kx = ky * math.cos(math.radians(band_lat))
        n = int(200 / kx) + 1; m = int(200 / ky) + 1
        X, Y = np.meshgrid(np.arange(-n, n + 1) * kx, np.arange(-m, m + 1) * ky)
        d = np.maximum(np.hypot(X, Y), 0.7); K = np.where(d < 200, d ** -2.3 * np.exp(-d / 150.0), 0)
        area = (ky * kx)                    # km^2 per cell (radiance is a cell mean)
        z = _fftconv(a * area, K)
        sel = np.abs(lat - band_lat) <= 5 if band_lat != 25 else lat < 30
        if band_lat == 45: sel = lat >= 40
        zen[sel] = z[sel]
    # calibrate on the reference SQMs, sampled from this grid
    def at(la, lo): return zen[int((50 - la) / step), int((lo + 130) / step)]
    cal = read_json(CONFIG / "sqm_readings.json", [])
    refs = [(c["lat"], c["lon"], c["sqm"]) for c in cal] if len(cal) >= 3 else list(REF.values())
    zs = [max(at(la, lo), 0) for la, lo, _ in refs]
    best = min(((sum((22.0 - 2.5 * math.log10(1 + 10 ** lc * z) - q) ** 2 for z, (_, _, q) in zip(zs, refs)), 10 ** lc) for lc in np.linspace(-6, 3, 361)))
    C = best[1]
    sqm = np.minimum(22.0 - 2.5 * np.log10(1 + C * np.maximum(zen, 0)), 22.0)
    # ship at 1/8 degree (3x3 mean of brightness, not of magnitudes)
    h3, w3 = sqm.shape[0] // 3 * 3, sqm.shape[1] // 3 * 3
    lum = (10 ** (-0.4 * sqm[:h3, :w3])).reshape(h3 // 3, 3, w3 // 3, 3).mean((1, 3))
    out = -2.5 * np.log10(lum)
    q = np.clip(np.round((out - 16.0) * 10), 0, 60).astype(int)
    d = "".join(ALPHA[v] for v in q.ravel())
    write_json("darkgrid.json", {"gen": iso(utcnow()), "year": y, "n": 50.0, "w": -130.0, "d": 0.125, "nx": q.shape[1], "ny": q.shape[0],
                                 "alphabet": ALPHA, "base": 16.0, "step": 0.1, "C": C, "rmse_mag": round(math.sqrt(best[0] / len(refs)), 2), "q": d,
                                 "note": "Modeled zenith sky brightness (SQM, mag/arcsec^2) from NASA VIIRS Black Marble annual radiance; rows north to south."})
    return f"{q.shape[1]}x{q.shape[0]} grid from {y}, rmse {best[0] ** .5 / len(refs) ** .5:.2f} mag"
