"""GOES-18 right now (MEASURED by satellite, classified by NOAA algorithms).

Uses two NOAA Level-2 CONUS products from the public AWS bucket (no account):
  ABI-L2-ACMC  clear-sky mask (BCM: 0 clear, 1 cloudy)
  ABI-L2-ACHAC cloud-top height (HT, metres)
Low cloud / fog = cloudy with cloud top below 1500 m. Writes per-spot fractions in a 3x3 pixel block
(~6 km), a PNG overlay for the map, and appends a compact history line used by verify.py.
"""
import datetime as dt, io, re, json, math
import numpy as np
from .common import http, spots, write_json, FEED, DATA, CACHE, log, utcnow, iso

BUCKET = "https://noaa-goes18.s3.amazonaws.com"
BBOX = (-124.4, 44.6, -120.0, 46.8)


def latest_key(product):
    now = utcnow()
    for back in range(0, 4):
        t = now - dt.timedelta(hours=back)
        pre = f"{product}/{t:%Y}/{t.timetuple().tm_yday:03d}/{t:%H}/"
        x = http(BUCKET + "/", params={"list-type": 2, "prefix": pre}).text
        keys = re.findall(r"<Key>([^<]+\.nc)</Key>", x)
        if keys:
            return sorted(keys)[-1]
    raise RuntimeError(f"no {product} files in last 4 h")


def open_nc(key):
    import xarray as xr
    b = http(f"{BUCKET}/{key}", timeout=180).content
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
    pts = spots()
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
    write_json("goes.json", {"gen": iso(utcnow()), "obs": tstamp, "cols": ["cloud_pct", "lowcloud_pct", "top_m"], "spots": out,
                             "overlay": {"png": "goes_lowcloud.png", "bbox": BBOX}, "products": [km_, kh]})
    # rolling 120-day history: one line per scan, two digits per spot (cloud tenth, low-cloud tenth)
    hp = DATA / "goes_history.txt"
    lines = hp.read_text().splitlines() if hp.exists() else []
    if not lines or not lines[0].startswith("#"):
        lines = ["#ids " + ",".join(p["id"] for p in pts)] + [l for l in lines if not l.startswith("#")]
    lines.append(f"{tstamp} {''.join(hist)}")
    cut = (utcnow() - dt.timedelta(days=120)).strftime("%Y-%m-%d")
    lines = [lines[0]] + [l for l in lines[1:] if l[:10] >= cut]
    hp.write_text("\n".join(lines) + "\n")
    return f"scan {tstamp}"
