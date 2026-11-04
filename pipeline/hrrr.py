"""HRRR conditions as probabilities (MODELED).

Method: neighbourhood + time-lagged ensemble. For every forecast hour we take the 7x7 block of 3 km
HRRR cells around each spot (~21 km) from the newest run, and the same block from the previous run's
saved output. The probability of an event is the fraction of those cells/runs where it happens. This is
the standard way to turn a single deterministic convection-allowing model into calibrated-ish odds;
verify.py then measures how calibrated they really are.

Events: fog (vis < 1 km or cloud base < 150 m AGL with low cloud > 80%), low stratus (low cloud > 80%),
clear (total cloud < 20%), colour sky (mid/high 20-80% with low < 40%).
Also: near-surface and column smoke, snow level (0 C isotherm - 300 m), inversion strength (T925 - T2m), wind.
"""
import datetime as dt, json
import numpy as np
from .common import spots, write_json, read_json, FEED, CACHE, log, utcnow, iso, r

SEARCH = (":(TCDC|LCDC|MCDC|HCDC):|:VIS:surface|:TMP:2 m above|:RH:2 m above|:(UGRD|VGRD):10 m above|"
          ":HGT:cloud base|:HGT:surface|:HGT:0C isotherm|:MASSDEN:8 m above|:COLMD:entire|:TMP:925 mb")
NB = 3  # half-width of neighbourhood (7x7)


def latest_run(synoptic=False):
    from herbie import Herbie
    now = utcnow().replace(minute=0, second=0, microsecond=0, tzinfo=None)
    for back in range(1, 12):
        t = now - dt.timedelta(hours=back)
        if synoptic and t.hour % 6:
            continue
        H = Herbie(t, model="hrrr", product="sfc", fxx=18 if not synoptic else 48, save_dir=str(CACHE / "herbie"), verbose=False)
        if H.grib:
            return t
    raise RuntimeError("no HRRR run found")


def _flatten(ds):
    """Herbie may return one Dataset or a list (one per level type). Map 'shortName:typeOfLevel' -> 2D array."""
    out, lat, lon = {}, None, None
    for d in (ds if isinstance(ds, list) else [ds]):
        if lat is None:
            lat, lon = d.latitude.values, d.longitude.values
        for v in d.data_vars:
            a = d[v]
            key = f"{a.attrs.get('GRIB_shortName', v)}:{a.attrs.get('GRIB_typeOfLevel', '')}"
            vals = a.values
            if vals.ndim == 3:  # stacked levels
                levs = d[a.dims[0]].values
                for j, lv in enumerate(levs):
                    out[f"{key}:{int(lv)}"] = vals[j]
            else:
                out[key] = vals
    return out, lat, lon


def _pick(fields, *names):
    for n in names:
        for k, v in fields.items():
            if k.lower().startswith(n.lower()):
                return v
    return None


def grid_index(lat, lon, pts):
    from scipy.spatial import cKDTree
    lon = np.where(lon > 180, lon - 360, lon)
    c = np.cos(np.radians(45.6))
    tree = cKDTree(np.c_[lat.ravel(), lon.ravel() * c])
    _, i = tree.query(np.c_[[p["lat"] for p in pts], [p["lon"] * c for p in pts]])
    return np.unravel_index(i, lat.shape)


def one_hour(run, fxx, pts, idx_cache):
    from herbie import Herbie
    H = Herbie(run, model="hrrr", product="sfc", fxx=fxx, save_dir=str(CACHE / "herbie"), verbose=False)
    ds = H.xarray(SEARCH, remove_grib=True)
    f, lat, lon = _flatten(ds)
    if "idx" not in idx_cache:
        idx_cache["idx"] = grid_index(lat, lon, pts)
        idx_cache["shape"] = lat.shape
    iy, ix = idx_cache["idx"]
    ny, nx = idx_cache["shape"]
    tcc = _pick(f, "tcc:atmosphere", "tcc")
    lcc, mcc, hcc = _pick(f, "lcc"), _pick(f, "mcc"), _pick(f, "hcc")
    vis = _pick(f, "vis")
    t2 = _pick(f, "2t", "t2m")
    rh = _pick(f, "2r", "r2")
    u10, v10 = _pick(f, "10u", "u10"), _pick(f, "10v", "v10")
    cb = _pick(f, "gh:cloudBase")
    zs = _pick(f, "orog", "gh:surface", "hgt:surface")
    z0 = _pick(f, "gh:isothermZero")
    smk = _pick(f, "mdens", "massden")
    col = _pick(f, "colmd", "unknown:atmosphere")
    t925 = _pick(f, "t:isobaricInhPa:925", "t:isobaricInhPa")
    rows = []
    for k in range(len(pts)):
        y0, y1 = max(0, iy[k] - NB), min(ny, iy[k] + NB + 1)
        x0, x1 = max(0, ix[k] - NB), min(nx, ix[k] + NB + 1)
        blk = lambda a: None if a is None else a[y0:y1, x0:x1]
        L, T, M, Hh, V = blk(lcc), blk(tcc), blk(mcc), blk(hcc), blk(vis)
        CB = blk(cb) - blk(zs) if cb is not None and zs is not None else None
        fog = (V < 1000) if V is not None else np.zeros_like(L, bool)
        if CB is not None:
            fog = fog | ((CB < 150) & (L > 80))
        canvas = np.maximum(M, Hh * 0.9) if M is not None and Hh is not None else None
        color = ((canvas >= 20) & (canvas <= 80) & (L < 40)) if canvas is not None else None
        c = (iy[k], ix[k])
        rows.append({
            "fog": fog, "low": L > 80, "clear": T < 20, "color": color,
            "tcc": float(tcc[c]), "lcc": float(lcc[c]),
            "smoke": None if smk is None else float(smk[c]) * 1e9,
            "smoke_col": None if col is None else float(col[c]) * 1e6,
            "snow": None if z0 is None else float(z0[c]) - 300,
            "inv": None if (t925 is None or t2 is None) else float(t925[c] - t2[c]),
            "wind": None if u10 is None else float(np.hypot(u10[c], v10[c])) * 2.237,
            "rh": None if rh is None else float(rh[c]),
            "t": None if t2 is None else (float(t2[c]) - 273.15) * 9 / 5 + 32,
        })
    return rows


def run():
    pts = spots()
    grid = json.load(open(FEED.parent / "config" / "grid.json")) if (FEED.parent / "config" / "grid.json").exists() else []
    pts = pts + grid
    run_h = latest_run()
    run_s = latest_run(synoptic=True)
    plan = [(run_h, f) for f in range(0, 19)] + [(run_s, f) for f in range(21, 49, 3) if run_s + dt.timedelta(hours=f) > run_h + dt.timedelta(hours=18)]
    prev = read_json(CACHE / "hrrr_members.json", {})  # previous run's per-spot event fractions keyed by valid time
    idx_cache, valid, per = {}, [], {p["id"]: [] for p in pts}
    members_now = {}
    for rn, f in plan:
        vt = rn + dt.timedelta(hours=f)
        try:
            rows = one_hour(rn, f, pts, idx_cache)
        except Exception as e:
            log.warning("HRRR %s f%02d failed: %s", rn, f, e)
            continue
        key = str(int(vt.replace(tzinfo=dt.timezone.utc).timestamp() // 60))
        valid.append(int(key))
        members_now[key] = {}
        for p, row in zip(pts, rows):
            frac = {e: (None if row[e] is None else float(np.mean(row[e]))) for e in ("fog", "low", "clear", "color")}
            members_now[key][p["id"]] = frac
            old = prev.get(key, {}).get(p["id"])
            prob = {}
            for e, v in frac.items():
                vals = [x for x in (v, None if not old else old.get(e)) if x is not None]
                prob[e] = None if not vals else round(100 * sum(vals) / len(vals))
            per[p["id"]].append([prob["fog"], prob["low"], prob["clear"], prob["color"], r(row["tcc"], 0), r(row["lcc"], 0),
                                  r(row["smoke"], 1), r(row["smoke_col"], 1), r(row["snow"], -1), r(row["inv"], 1), r(row["wind"], 0), r(row["rh"], 0), r(row["t"], 0)])
    json.dump(members_now, open(CACHE / "hrrr_members.json", "w"))
    write_json("hrrr.json", {"gen": iso(utcnow()), "run": iso(run_h.replace(tzinfo=dt.timezone.utc)), "cols": ["p_fog", "p_low", "p_clear", "p_color", "tcc", "lcc", "smoke_ugm3", "smoke_col_mgm2", "snow_m", "inv_c", "wind_mph", "rh", "t_f"],
                             "t": valid, "spots": per, "method": "7x7 neighbourhood (21 km) + previous-run time-lagged member"})
    return f"run {run_h:%m-%d %HZ}, {len(valid)} valid hours, {len(pts)} points"
