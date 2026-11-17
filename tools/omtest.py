"""Inspect a previous-runs response the way pipeline/skill.py requests it."""
import requests, os, json, datetime as dt
os.makedirs("ux", exist_ok=True)
d1 = dt.date.today(); d0 = d1 - dt.timedelta(days=1); out = []
for m in (None, "gfs_hrrr"):
    p = {"latitude": 45.6, "longitude": -122.6, "hourly": "cloud_cover_low_previous_day1,cloud_cover_mid_previous_day1", "start_date": d0.isoformat(), "end_date": d1.isoformat(), "timezone": "UTC"}
    if m: p["models"] = m
    r = requests.get("https://previous-runs-api.open-meteo.com/v1/forecast", params=p, timeout=30); j = r.json(); h = j.get("hourly", {})
    out.append(f"{m}: {r.status_code} keys={list(h)} n={len(h.get('time', []))} first={h.get('time', [''])[:2]} nonnull_low={sum(v is not None for v in h.get('cloud_cover_low_previous_day1', []))} sample={h.get('cloud_cover_low_previous_day1', [])[12:20]} err={j.get('reason')}")
open("ux/omtest.txt", "w").write("\n".join(out)); print("\n".join(out))
