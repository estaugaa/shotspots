import math, sys, types
import numpy as np
sys.path.insert(0, ".")
from pipeline import terrain, goes, verify


def test_horizon_cone():
    # flat plain with a 1000 m cone 10 km due east of the observer
    lat0, lon0 = 45.5, -122.0
    n = 2000
    bbox = (lon0 - 0.3, lat0 - 0.2, lon0 + 0.3, lat0 + 0.2)
    lons = np.linspace(bbox[0], bbox[2], n); lats = np.linspace(bbox[3], bbox[1], n)
    LO, LA = np.meshgrid(lons, lats)
    clat, clon = lat0, lon0 + 10 / (111.2 * math.cos(math.radians(lat0)))
    d = np.hypot((LA - clat) * 111.2, (LO - clon) * 111.2 * math.cos(math.radians(lat0)))
    z = np.clip(1000 - d * 500, 0, None).astype(np.float32)
    g = terrain.Grid(z, bbox)
    alt, bd, h0 = terrain.horizon(lat0, lon0, [g])
    east = alt[int(90 / 0.5)]
    expect = math.degrees(math.atan2(1000 - 1.7, 10000)) - 10000 * (1 - 0.13) / (2 * 6371000) * 180 / math.pi
    assert abs(east - expect) < 0.35, (east, expect)
    assert alt[int(270 / 0.5)] < 0.05
    assert abs(bd[int(90 / 0.5)] - 10000) < 400


def test_goes_projection():
    # GOES-R PUG worked example (GOES-East, lon0 = -75)
    attrs = {"semi_major_axis": 6378137.0, "semi_minor_axis": 6356752.31414, "perspective_point_height": 35786023.0, "longitude_of_projection_origin": -75.0}
    ds = {"goes_imager_projection": types.SimpleNamespace(attrs=attrs)}
    x, y = goes.scan_angles(ds, np.array([33.846162]), np.array([-84.690932]))
    assert abs(x[0] - (-0.024052)) < 2e-6 and abs(y[0] - 0.095340) < 2e-6, (x, y)


def test_brier_and_platt():
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 400)
    o = (rng.uniform(0, 1, 400) < p).astype(int)
    b = verify.brier(list(zip(p, o)))
    assert 0.12 < b["brier"] < 0.22 and b["skill_vs_climatology"] > 0.2
    s = rng.uniform(0, 100, 500); y = (rng.uniform(0, 1, 500) < 1 / (1 + np.exp(-(6 * s / 100 - 3)))).astype(int)
    a, c = verify.platt(s, y)
    assert abs(a - 6) < 1.5 and abs(c + 3) < 0.8, (a, c)


def test_sep():
    assert abs(verify.sep(0, 0, 1, 0) - 60) < 1e-6
