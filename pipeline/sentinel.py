"""Fall colour, green-up and snow cover from Sentinel-2 L2A (MEASURED reflectance, ESTIMATED interpretation).

Uses the free Element84 Earth Search STAC catalogue of Sentinel-2 on AWS (no account; replaces Google Earth Engine).
For each foliage spot, reads a 300 m window from the newest scene with enough clear pixels (scene classification
4 = vegetation) and compares it with that spot's own July–August baseline:
  gcc   = green / (red+green+blue)      (falls as leaves turn)
  red   = (red-green)/(red+green)       (rises with red/orange/yellow colour)
  ndvi  drop vs summer                  (leaves falling)
Snow fraction (mountain spots): SCL class 11 or NDSI > 0.4.
"""
import datetime as dt, json, math
import numpy as np
from .common import http, spots, write_json, read_json, CACHE, log, utcnow, iso, r

STAC = "https://earth-search.aws.element84.com/v1/search"
HALF = 150  # metres


def search(lat, lon, start, end, limit=6, maxcc=70):
    body = {"collections": ["sentinel-2-l2a"], "intersects": {"type": "Point", "coordinates": [lon, lat]},
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": limit,
            "query": {"eo:cloud_cover": {"lt": maxcc}}, "sortby": [{"field": "properties.datetime", "direction": "desc"}]}
    return http(STAC, method="POST", data=json.dumps(body), headers={"Content-Type": "application/json"}).json().get("features", [])


def window(item, lat, lon, bands=("red", "green", "blue", "nir", "swir16", "scl")):
    import rasterio
    from rasterio.warp import transform
    from rasterio.windows import from_bounds
    out = {}
    for b in bands:
        href = item["assets"][b]["href"]
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
            with rasterio.open(href) as ds:
                xs, ys = transform("EPSG:4326", ds.crs, [lon], [lat])
                w = from_bounds(xs[0] - HALF, ys[0] - HALF, xs[0] + HALF, ys[0] + HALF, ds.transform)
                a = ds.read(1, window=w, boundless=True, fill_value=0).astype(np.float32)
        out[b] = a
    # resample 20 m bands (swir16, scl) to the 10 m grid by nearest repetition
    shp = out["red"].shape
    for b in ("swir16", "scl"):
        a = out[b]
        if a.shape != shp:
            ry, rx = shp[0] / a.shape[0], shp[1] / a.shape[1]
            out[b] = np.kron(a, np.ones((int(round(ry)), int(round(rx)))))[: shp[0], : shp[1]]
    return out


def metrics(w):
    scl = w["scl"]
    veg = scl == 4
    snow = scl == 11
    clear = np.isin(scl, [4, 5, 6, 7, 11])
    R, G, B, N, S = (w[k] / 10000.0 for k in ("red", "green", "blue", "nir", "swir16"))
    with np.errstate(invalid="ignore", divide="ignore"):
        gcc = G / (R + G + B)
        red = (R - G) / (R + G)
        ndvi = (N - R) / (N + R)
        ndsi = (G - S) / (G + S)
    m = lambda a, mask: float(np.nanmedian(a[mask])) if mask.sum() >= 20 else None
    return {"clear": float(clear.mean()), "veg": float(veg.mean()), "gcc": m(gcc, veg), "red": m(red, veg), "ndvi": m(ndvi, veg),
            "snow": float(((snow | ((ndsi > 0.4) & (N > 0.11))) & clear).sum() / max(1, clear.sum()))}


def best_scene(lat, lon, start, end):
    for it in search(lat, lon, start, end):
        try:
            mt = metrics(window(it, lat, lon))
        except Exception as e:
            log.warning("s2 read failed: %s", e)
            continue
        if mt["clear"] >= 0.6:
            mt["date"] = it["properties"]["datetime"][:10]
            mt["scene"] = it["id"]
            return mt
    return None


def run():
    today = utcnow().date()
    base_cache = CACHE / "s2_baseline.json"
    base = read_json(base_cache, {})
    yr = today.year if today.month >= 9 else today.year - 1
    out = {}
    for s in spots():
        cats = set(s["cats"])
        foliage = bool(cats & {"fallcolor", "wildflowers", "garden"})
        snowy = bool(cats & {"mountain"}) and s.get("effort") in ("road", "short")
        if not (foliage or snowy):
            continue
        key = f'{s["id"]}:{yr}'
        if foliage and key not in base:
            b = best_scene(s["lat"], s["lon"], f"{yr}-07-01", f"{yr}-08-31")
            base[key] = b
        cur = best_scene(s["lat"], s["lon"], (today - dt.timedelta(days=25)).isoformat(), today.isoformat())
        if not cur:
            continue
        rec = {"date": cur["date"], "snow": r(cur["snow"] * 100, 0)}
        b = base.get(key) if foliage else None
        if foliage and b and cur.get("gcc") is not None and b.get("gcc") is not None:
            dg = b["gcc"] - cur["gcc"]
            dr = (cur["red"] or 0) - (b["red"] or 0)
            dn = (b["ndvi"] or 0) - (cur["ndvi"] or 0)
            stage = "green" if dg < 0.01 and dr < 0.03 else "past (leaves dropping)" if dn > 0.25 else "near peak" if dg > 0.035 or dr > 0.08 else "turning"
            rec.update({"gcc_drop": r(dg, 3), "red_rise": r(dr, 3), "ndvi_drop": r(dn, 3), "stage": stage, "veg": r(cur["veg"] * 100, 0)})
        out[s["id"]] = rec
    json.dump(base, open(base_cache, "w"))
    write_json("sentinel.json", {"gen": iso(utcnow()), "spots": out,
                                 "note": "Sentinel-2 10 m, 300 m window, vegetation pixels only; colour stage is an estimate from change vs this spot's July–August baseline."})
    return f"{len(out)} spots"
