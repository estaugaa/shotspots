"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite."""
import requests, json, datetime as dt
B = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
r = requests.get(f"{B}/stations", params={"stateCds": "OR,WA", "networkCds": "SNTL", "elements": "SNWD", "returnForecastPointMetadata": "false"}, timeout=60)
print("stations", r.status_code, len(r.text)); st = r.json(); print(json.dumps(st[0])[:600]); print(len(st))
trip = [s["stationTriplet"] for s in st if s.get("name", "").lower().startswith(("mt hood", "blazed", "paradise"))][:3]
end = dt.date.today(); beg = end - dt.timedelta(days=3)
r = requests.get(f"{B}/data", params={"stationTriplets": ",".join(trip), "elements": "SNWD,WTEQ", "duration": "DAILY", "beginDate": str(beg), "endDate": str(end)}, timeout=60)
print("data", r.status_code); print(json.dumps(r.json())[:1500])
for u in ["https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json", "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"]:
    r = requests.get(u, timeout=30); print("SWPC", u.split("/")[-1], r.status_code, r.text[:300], "...", r.text[-200:])
