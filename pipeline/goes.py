"""GOES-18 right now (MEASURED by satellite, classified by NOAA algorithms).

Uses two NOAA Level-2 CONUS products from the public AWS bucket (no account):
  ABI-L2-ACMC  clear-sky mask (BCM: 0 clear, 1 cloudy)
  ABI-L2-ACHAC cloud-top height (HT, metres)
Low cloud / fog = cloudy with cloud top below 1500 m. Writes per-spot fractions in a 3x3 pixel block
(~6 km), a PNG overlay for the map, and appends a compact history line used by verify.py.
"""
import datetime as dt, io, re, json, math
import numpy as np
from .common import http, spots, write_json, FEED, DATA, CACHE, log, utcnow, iso, soft_fail

BUCKET = "https://noaa-goes18.s3.amazonaws.com"
EAST = "https://noaa-goes19.s3.amazonaws.com"   # GOES-East: the gap grid east of SPLIT_LON (Nov 24; was western US only)
SPLIT_LON = -105.0
BBOX = (-124.4, 44.6, -120.0, 46.8)


def latest_key(product, bucket=BUCKET):
    now = utcnow()
    for back in range(0, 4):
        t = now - dt.timedelta(hours=back)
        pre = f"{product}/{t:%Y}/{t.timetuple().tm_yday:03d}/{t:%H}/"
        x = http(bucket + "/", params={"list-type": 2, "prefix": pre}).text
        keys = re.findall(r"<Key>([^<]+\.nc)</Key>", x)
        if keys:
            return sorted(keys)[-1]
    raise RuntimeError(f"no {product} files in last 4 h")


def open_nc(key, bucket=BUCKET):
    import xarray as xr
    b = http(f"{bucket}/{key}", timeout=180).content
    return xr.open_dataset(io.BytesIO(b), engine="h5netcdf")


def scan_angles(ds, lat, lon):
    p = ds["goes_imager_projection"].attrs
    req, rpol = p["semi_major_axis"], p["semi_minor_axis"]
    H = p["perspective_point_height"] + req
    lon0 = math.radians(p["longitude_of_projection_origin"])
    la, lo = np.radians(lat), np.radians(lon)
    e2 = (req ** 2 - rpol ** 2) / req ** 2
    phc = np.arctan((rpol ** 2 / req ** 2) * np.tan(la))
    rc = rpol / np.sqrt(1 - e2 * np.cos(phc) ** 2)
    sx = H - rc * np.cos(phc) * np.cos(lo - lon0)
    sy = -rc * np.cos(phc) * np.sin(lo - lon0)
    sz = rc * np.sin(phc)
    y = np.arctan(sz / sx)
    x = np.arcsin(-sy / np.sqrt(sx ** 2 + sy ** 2 + sz ** 2))
    return x, y


def to_index(ds, lat, lon):
    x, y = scan_angles(ds, np.asarray(lat, float), np.asarray(lon, float))
    xs, ys = ds["x"].values, ds["y"].values
    ix = np.clip(np.round((x - xs[0]) / (xs[1] - xs[0])).astype(int), 0, len(xs) - 1)
    iy = np.clip(np.round((y - ys[0]) / (ys[1] - ys[0])).astype(int), 0, len(ys) - 1)
    return iy, ix


def run():
    km_ = latest_key("ABI-L2-ACMC")
    kh = latest_key("ABI-L2-ACHAC")
    m = open_nc(km_)
    h = open_nc(kh)
    bcm = m["BCM"].values
    ht = h["HT"].values
    tstamp = m.attrs.get("time_coverage_end") or iso(utcnow())
    pts = [p for p in spots() if -170 < p["lon"] < -100 and -60 < p["lat"] < 60]  # GOES-18 (West) usable disk
    iy, ix = to_index(m, [p["lat"] for p in pts], [p["lon"] for p in pts])
    hy, hx = to_index(h, [p["lat"] for p in pts], [p["lon"] for p in pts])
    out = {}
    hist = []
    for k, p in enumerate(pts):
        b = bcm[max(0, iy[k] - 1):iy[k] + 2, max(0, ix[k] - 1):ix[k] + 2].astype(float)
        hh = ht[max(0, hy[k] - 1):hy[k] + 2, max(0, hx[k] - 1):hx[k] + 2].astype(float)
        cloud = float(np.nanmean(b == 1)) if b.size else None
        low = float(np.nanmean((hh < 1500) & np.isfinite(hh))) if hh.size else 0.0
        top = float(np.nanmedian(hh)) if np.isfinite(hh).any() else None
        out[p["id"]] = [round(100 * cloud) if cloud is not None else None, round(100 * low), None if top is None else int(top)]
        hist.append(str(min(9, int((cloud or 0) * 9.99))) + str(min(9, int(low * 9.99))))
    # map overlay
    lats = np.linspace(BBOX[3], BBOX[1], 220)
    lons = np.linspace(BBOX[0], BBOX[2], 440)
    LO, LA = np.meshgrid(lons, lats)
    gy, gx = to_index(m, LA.ravel(), LO.ravel())
    hy2, hx2 = to_index(h, LA.ravel(), LO.ravel())
    cb = bcm[gy, gx].reshape(LA.shape)
    ch = ht[hy2, hx2].reshape(LA.shape)
    img = np.zeros(LA.shape + (4,), np.uint8)
    lowm = (cb == 1) & (ch < 1500)
    midm = (cb == 1) & ~lowm
    img[lowm] = (255, 255, 255, 190)   # fog / low stratus: white
    img[midm] = (120, 140, 170, 110)   # higher cloud: grey-blue
    from PIL import Image
    Image.fromarray(img, "RGBA").save(FEED / "goes_lowcloud.png", optimize=True)
    # gap grid for the sunset/sunrise check: tenths of each 0.25° cell covered by cloud topping out below 4 km
    # (the layer that blocks low-angle light). One digit per cell. GOES-18 west of SPLIT_LON, GOES-19 (East) east of
    # it, so the lower 48 are covered (Nov 24: was the western US only). If the East scan can't be read, the grid is
    # the western one as before.
    east = None
    try:
        me, he = open_nc(latest_key("ABI-L2-ACMC", EAST), EAST), open_nc(latest_key("ABI-L2-ACHAC", EAST), EAST)
        east = (me, he, me["BCM"].values, he["HT"].values)
    except Exception as e:
        soft_fail("goes: GOES-East scan (grid stays western)", e)
    try:
        G = {"w": -130.0, "s": 24.0 if east else 30.0, "e": -65.0 if east else -100.0, "n": 50.0, "d": 0.25, "sub": 4}
        nx, ny, sub = int((G["e"] - G["w"]) / G["d"]), int((G["n"] - G["s"]) / G["d"]), G["sub"]
        off = (np.arange(sub) + 0.5) / sub * G["d"]
        glon = (G["w"] + np.arange(nx)[:, None] * G["d"] + off[None, :]).ravel()
        glat = (G["n"] - np.arange(ny)[:, None] * G["d"] - off[None, :]).ravel()
        LO2, LA2 = np.meshgrid(glon, glat)
        def gap(mm, hh_, b_, t_):
            my, mx = to_index(mm, LA2.ravel(), LO2.ravel()); ty, tx = to_index(hh_, LA2.ravel(), LO2.ravel())
            return ((b_[my, mx] == 1) & (t_[ty, tx] < 4000)).reshape(ny, sub, nx, sub).mean(axis=(1, 3))
        blk = gap(m, h, bcm, ht)
        if east:
            try:
                cell_lon = G["w"] + (np.arange(nx) + 0.5) * G["d"]
                blk = np.where(cell_lon[None, :] < SPLIT_LON, blk, gap(*east))
                G["sats"] = f"GOES-18 west of {SPLIT_LON:g}, GOES-19 east"
            except Exception as e:
                soft_fail("goes: GOES-East grid (western cells only)", e)
                keep = int((-100.0 - G["w"]) / G["d"])
                G.update({"s": 30.0, "e": -100.0}); nx, ny = keep, int((50.0 - 30.0) / G["d"]); blk = blk[:ny, :nx]
        digits = "".join(str(min(9, int(v * 9.99))) for v in blk.ravel())
        write_json("goes_grid.json", {"gen": iso(utcnow()), "obs": tstamp, **G, "nx": nx, "ny": ny, "rows": "north to south", "d9": digits,
                                      "note": "tenths of each cell with cloud topping below 4 km (blocks low sun)"})
    except Exception as e:
        log.warning("gap grid: %s", e)
    write_json("goes.json", {"gen": iso(utcnow()), "obs": tstamp, "cols": ["cloud_pct", "lowcloud_pct", "top_m"], "spots": out,
                             "overlay": {"png": "goes_lowcloud.png", "bbox": BBOX}, "products": [km_, kh]})
    keep_history([p["id"] for p in pts], [(tstamp, "".join(hist))])
    return f"scan {tstamp}"


def _set_id(ids):
    """Spot lists change (new researched spots); each scan row names its list by a short hash (data/archive/goes/sets.json)."""
    import hashlib
    from . import archive
    from .common import read_json
    h = hashlib.sha1(",".join(ids).encode()).hexdigest()[:10]
    sp = archive.ROOT / "goes" / "sets.json"; sets = read_json(sp, {}) or {}
    if h not in sets:
        sets[h] = list(ids); sp.parent.mkdir(parents=True, exist_ok=True); sp.write_text(json.dumps(sets, separators=(",", ":")))
    return h


def keep_history(ids, scans):
    """History kept indefinitely: data/archive/goes/<month>.csv.gz, one row per scan (t, spot list, two digits per spot:
    cloud tenth, low-cloud tenth). The old rolling goes_history*.txt files are moved in once, then removed."""
    from . import archive
    rows = [{"t": t, "set": _set_id(ids), "d": d} for t, d in scans]
    for p in sorted(DATA.glob("goes_history*.txt")):
        lines = p.read_text().splitlines()
        if lines and lines[0].startswith("#ids "):
            s = _set_id(lines[0][5:].split(","))
            rows = [{"t": l.split(" ", 1)[0], "set": s, "d": l.split(" ", 1)[1]} for l in lines[1:] if " " in l] + rows
    archive.append("goes", ["t", "set", "d"], rows, lambda r: r["t"], lambda r: (r["t"], r["set"]))
    for p in DATA.glob("goes_history*.txt"): p.unlink()


def history_at(spot_id, t, within=3600):
    """The scan nearest time t (datetime, within `within` s) that covered the spot: (seconds off, cloud %, low cloud %)."""
    from . import archive
    from .common import read_json
    sets = read_json(archive.ROOT / "goes" / "sets.json", {}) or {}
    col = {h: ids.index(spot_id) for h, ids in sets.items() if spot_id in ids}
    if not col: return None
    lo, hi = (t - dt.timedelta(seconds=within)).strftime("%Y-%m-%dT%H:%M"), (t + dt.timedelta(seconds=within)).strftime("%Y-%m-%dT%H:%M:99")
    best = None
    for r in archive.read("goes", lo, "t", hi):
        k = col.get(r["set"])
        if k is None: continue
        try:
            tt = dt.datetime.fromisoformat(r["t"][:19]).replace(tzinfo=dt.timezone.utc)
            dtm = abs((tt - t).total_seconds())
            if dtm <= within and (best is None or dtm < best[0]):
                best = (dtm, int(r["d"][2 * k]) * 11, int(r["d"][2 * k + 1]) * 11)
        except (ValueError, IndexError) as e:
            soft_fail("goes: archived scan unreadable", e)
    return best
