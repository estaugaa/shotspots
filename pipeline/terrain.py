"""Terrain horizons from USGS 3DEP (best-available DEM: 1 m / 1/3" lidar-derived where it exists).

Three resolution tiers per spot so near ridges are sharp and far volcanoes are still in view:
  near: 6 km box  @ ~6 m   (canyon walls, lidar detail)
  mid : 40 km box @ ~40 m
  far : one regional mosaic @ ~110 m covering 44.3–47.3 N, 124.6–119.9 W
Horizon altitude per 0.5° of azimuth includes Earth curvature and standard refraction (k = 0.13).
Note: 3DEP is BARE EARTH. Trees and buildings are not in the horizon (a DSM from lidar point clouds would be needed).
"""
import math, io, json
import numpy as np
from .common import http, CACHE, spots, write_json, log, km, r, FEED

SVC = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
R_EARTH = 6371000.0
K_REFR = 0.13
AZ = np.arange(0, 360, 0.5)
FAR_BOX = (-124.6, 44.3, -119.9, 47.3)


class Grid:
    """Regular lat/lon grid (row 0 = north edge)."""
    def __init__(self, z, bbox):
        self.z = z.astype(np.float32)
        self.x0, self.y0, self.x1, self.y1 = bbox
        self.h, self.w = z.shape
        self.dx = (self.x1 - self.x0) / self.w
        self.dy = (self.y1 - self.y0) / self.h

    def contains(self, lat, lon):
        return (lon > self.x0) & (lon < self.x1) & (lat > self.y0) & (lat < self.y1)

    def sample(self, lat, lon):
        c = (np.asarray(lon) - self.x0) / self.dx - 0.5
        rr = (self.y1 - np.asarray(lat)) / self.dy - 0.5
        c0 = np.clip(np.floor(c).astype(int), 0, self.w - 2)
        r0 = np.clip(np.floor(rr).astype(int), 0, self.h - 2)
        fc = np.clip(c - c0, 0, 1)
        fr = np.clip(rr - r0, 0, 1)
        z = self.z
        a = z[r0, c0] * (1 - fc) + z[r0, c0 + 1] * fc
        b = z[r0 + 1, c0] * (1 - fc) + z[r0 + 1, c0 + 1] * fc
        return a * (1 - fr) + b * fr


def fetch_dem(bbox, size, name):
    """Download a DEM chunk as float32 GeoTIFF in EPSG:4326. Cached in .cache/dem/."""
    p = CACHE / "dem" / f"{name}.npy"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return Grid(np.load(p), bbox)
    import rasterio
    params = {"bbox": ",".join(f"{v:.6f}" for v in bbox), "bboxSR": 4326, "imageSR": 4326,
              "size": f"{size[0]},{size[1]}", "format": "tiff", "pixelType": "F32",
              "interpolation": "RSP_BilinearInterpolation", "noData": -9999, "f": "image"}
    resp = http(SVC, params=params, timeout=180)
    with rasterio.MemoryFile(resp.content) as mf, mf.open() as ds:
        z = ds.read(1).astype(np.float32)
    z[(z < -500) | (z > 9000)] = 0.0  # ocean / nodata -> sea level
    np.save(p, z)
    return Grid(z, bbox)


def far_grid():
    p = CACHE / "dem" / "far_full.npy"
    if p.exists():
        return Grid(np.load(p), FAR_BOX)
    # tile the regional mosaic in 4x3 chunks of 1000 px (~110 m)
    nx, ny, px = 4, 3, 1000  # ~110-130 m regional mosaic
    x0, y0, x1, y1 = FAR_BOX
    rows = []
    for j in range(ny):
        row = []
        for i in range(nx):
            bb = (x0 + (x1 - x0) * i / nx, y1 - (y1 - y0) * (j + 1) / ny, x0 + (x1 - x0) * (i + 1) / nx, y1 - (y1 - y0) * j / ny)
            row.append(fetch_dem(bb, (px, px), f"far_{i}_{j}").z)
        rows.append(np.hstack(row))
    z = np.vstack(rows)
    np.save(p, z)
    return Grid(z, FAR_BOX)


def spot_grids(lat, lon, sid):
    def box(half_km):
        dlat = half_km / 111.2
        dlon = half_km / (111.2 * math.cos(math.radians(lat)))
        return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)
    near = fetch_dem(box(3), (600, 600), f"near_{sid}")    # ~10 m
    mid = fetch_dem(box(20), (500, 500), f"mid_{sid}")     # ~80 m
    return near, mid


def destination(lat, lon, az_deg, d_m):
    """Vectorised great-circle destination."""
    d = np.asarray(d_m) / R_EARTH
    th = np.radians(az_deg)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = np.arcsin(np.sin(p1) * np.cos(d) + np.cos(p1) * np.sin(d) * np.cos(th))
    l2 = l1 + np.arctan2(np.sin(th) * np.sin(d) * np.cos(p1), np.cos(d) - np.sin(p1) * np.sin(p2))
    return np.degrees(p2), np.degrees(l2)


DIST = np.unique(np.concatenate([np.arange(15, 600, 15), np.geomspace(600, 160000, 420)]))


def apparent_alt(h_obs, h_tgt, d):
    """Apparent elevation angle (deg) of a point h_tgt at distance d, curvature + refraction."""
    return np.degrees(np.arctan2(h_tgt - h_obs, d) - d * (1 - K_REFR) / (2 * R_EARTH))


def horizon(lat, lon, grids, h_extra=1.7, dist=DIST):
    """Return (alt[az], dist_of_blocker[az], obs_elev). grids = [near, mid, far] (finest first)."""
    near = grids[0]
    h0 = float(near.sample(np.array([lat]), np.array([lon]))[0]) + h_extra
    out = np.full(AZ.shape, -5.0, dtype=np.float32)
    bd = np.zeros(AZ.shape, dtype=np.float32)
    for i, az in enumerate(AZ):
        la, lo = destination(lat, lon, az, dist)
        z = np.full(dist.shape, np.nan, dtype=np.float32)
        for g in grids:  # finest grid that contains the point wins
            m = np.isnan(z) & g.contains(la, lo)
            if m.any():
                z[m] = g.sample(la[m], lo[m])
        z = np.nan_to_num(z, nan=0.0)
        a = apparent_alt(h0, z, dist)
        k = int(np.argmax(a))
        out[i] = a[k]
        bd[i] = dist[k]
    return out, bd, h0


def run(only=None, budget_min=40):
    """Compute horizons for every spot. Results persist in data/horizons.json (committed), so a run that hits its
    time budget simply continues where it left off next time. Downloads run 6 at a time."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    from .common import DATA
    store = DATA / "horizons.json"
    old = json.load(open(store)) if store.exists() else {}
    t0 = time.time()
    far = far_grid()
    todo = []
    for s in spots():
        if only and s["id"] not in only:
            continue
        key = f'{s["lat"]:.5f},{s["lon"]:.5f}'
        if s["id"] in old and old[s["id"]].get("key") == key:
            continue
        todo.append((s, key))
    n = 0

    def fetch(item):
        s, _ = item
        return item, spot_grids(s["lat"], s["lon"], s["id"])

    with ThreadPoolExecutor(6) as ex:
        for (s, key), grids in ex.map(lambda it: _safe(fetch, it), todo):
            if grids is None:
                continue
            near, mid = grids
            alt, bd, h0 = horizon(s["lat"], s["lon"], [near, mid, far])
            old[s["id"]] = {"key": key, "elev": round(h0 - 1.7, 1), "alt": [round(float(x), 2) for x in alt], "bkm": [round(float(x) / 1000, 2) for x in bd]}
            n += 1
            if n % 20 == 0:
                json.dump(old, open(store, "w"), separators=(",", ":"))
            if time.time() - t0 > budget_min * 60:
                log.warning("terrain: time budget reached after %d spots; continuing next run", n)
                break
    json.dump(old, open(store, "w"), separators=(",", ":"))
    write_json("horizons.json", {k: {"elev": v["elev"], "alt": [round(max(v["alt"][2 * i], v["alt"][2 * i + 1]), 1) for i in range(360)]} for k, v in old.items()})
    left = len(todo) - n
    return f"{len(old)} spots done ({n} new this run, {max(0, left)} still to do); bare-earth 3DEP, trees not modeled"


def _safe(fn, item):
    try:
        return fn(item)
    except Exception as e:
        log.warning("horizon %s failed: %s", item[0]["id"], e)
        return item, None


def load():
    from .common import DATA
    p = DATA / "horizons.json"
    return json.load(open(p)) if p.exists() else {}


def horizon_alt(h, az):
    """Interpolate horizon altitude at azimuth(s) from a 0.5-degree profile."""
    a = np.asarray(h["alt"], dtype=np.float32)
    x = (np.asarray(az) % 360) / 0.5
    i0 = np.floor(x).astype(int) % len(a)
    f = x - np.floor(x)
    return a[i0] * (1 - f) + a[(i0 + 1) % len(a)] * f


def landmark_view(h, obs_lat, obs_lon, obs_elev, lm, far):
    """Apparent alt/az of a landmark's top from a spot, and whether terrain hides it."""
    from .common import bearing
    d = km(obs_lat, obs_lon, lm["lat"], lm["lon"]) * 1000
    elev = lm.get("elev") or float(far.sample(np.array([lm["lat"]]), np.array([lm["lon"]]))[0])
    az = bearing(obs_lat, obs_lon, lm["lat"], lm["lon"])
    alt = float(apparent_alt(obs_elev + 1.7, elev, d))
    hz = float(horizon_alt(h, az))
    return {"az": az, "alt": alt, "dkm": d / 1000, "visible": alt >= hz - 0.05, "show": alt - hz}
