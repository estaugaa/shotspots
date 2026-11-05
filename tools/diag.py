"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite."""
import datetime as dt, numpy as np
from herbie import Herbie
t = dt.datetime.utcnow().replace(minute=0, second=0, microsecond=0) - dt.timedelta(hours=2)
for pat in (":AOTK:", ":COLMD:", ":MASSDEN:8 m above"):
    H = Herbie(t, model="hrrr", product="sfc", fxx=1, save_dir="/tmp/h", verbose=False)
    d = H.xarray(pat, remove_grib=True)
    d = d[0] if isinstance(d, list) else d
    v = list(d.data_vars)[0]; a = d[v].values; lat = d.latitude.values; lon = d.longitude.values - 360
    m = (lat > 44.5) & (lat < 47) & (lon > -124) & (lon < -120)
    print("VAR", pat, d[v].attrs.get("GRIB_typeOfLevel"), "PNW pctl 50/90/99/max", np.percentile(a[m], [50, 90, 99]).round(8), a[m].max(), "CONUS max", a.max())
