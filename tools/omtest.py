"""Which previous-runs requests work, and how fast (for pipeline/skill.py)."""
import requests, time, os
os.makedirs("ux", exist_ok=True)
B = "https://previous-runs-api.open-meteo.com/v1/forecast"
lat = ",".join(["45.6", "40.0", "35.0", "33.4", "39.7"]); lon = ",".join(["-122.6", "-105.0", "-90.0", "-112.0", "-75.2"])
V = "cloud_cover_low_previous_day1,cloud_cover_mid_previous_day1"
cases = [("best_match 1pt", {"latitude": "45.6", "longitude": "-122.6", "hourly": V, "past_days": 1, "forecast_days": 1}),
         ("gfs_seamless 1pt", {"latitude": "45.6", "longitude": "-122.6", "hourly": V, "models": "gfs_seamless", "past_days": 1, "forecast_days": 1}),
         ("gfs_hrrr 1pt", {"latitude": "45.6", "longitude": "-122.6", "hourly": V, "models": "gfs_hrrr", "past_days": 1, "forecast_days": 1}),
         ("gfs_seamless 5pt", {"latitude": lat, "longitude": lon, "hourly": V, "models": "gfs_seamless", "past_days": 1, "forecast_days": 1}),
         ("gfs_seamless,gfs_hrrr 5pt", {"latitude": lat, "longitude": lon, "hourly": V, "models": "gfs_seamless,gfs_hrrr", "past_days": 1, "forecast_days": 1}),
         ("best_match start/end 5pt", {"latitude": lat, "longitude": lon, "hourly": V, "start_date": "2026-11-16", "end_date": "2026-11-17"}),
         ("gfs_seamless start/end 5pt", {"latitude": lat, "longitude": lon, "hourly": V, "models": "gfs_seamless", "start_date": "2026-11-16", "end_date": "2026-11-17"})]
out = []
for name, p in cases:
    t = time.time()
    try:
        r = requests.get(B, params=p, timeout=90); out.append(f"{name}: {r.status_code} {time.time() - t:.1f}s {r.text[:160]}")
    except Exception as e:
        out.append(f"{name}: ERR {time.time() - t:.1f}s {e}")
    time.sleep(3)
open("ux/omtest.txt", "w").write("\n".join(out)); print("\n".join(out))
