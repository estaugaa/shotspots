"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite."""
import datetime as dt
from herbie import Herbie
t = dt.datetime.utcnow().replace(minute=0, second=0, microsecond=0) - dt.timedelta(hours=2)
H = Herbie(t, model="hrrr", product="sfc", fxx=1, save_dir="/tmp/h", verbose=False)
print(H.inventory(":MASSDEN:|:COLMD:|:AOTK:")[["search_this"]].to_string())
ds = H.xarray(":MASSDEN:8 m above|:COLMD:entire|:AOTK:", remove_grib=True)
for d in (ds if isinstance(ds, list) else [ds]):
    for v in d.data_vars:
        a = d[v]
        print("VAR", v, a.attrs.get("GRIB_shortName"), a.attrs.get("GRIB_typeOfLevel"), a.attrs.get("GRIB_units"), float(a.max()), a.dims)
