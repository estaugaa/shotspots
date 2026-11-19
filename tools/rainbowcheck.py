"""Replay the app's two rainbow rules for a place and day, against the model data and airport observations.
python tools/rainbowcheck.py lat lon YYYY-MM-DD -> ux/rainbow.txt"""
import requests, math, sys, os, datetime as dt, csv, io
os.makedirs("ux", exist_ok=True)
lat, lon, day = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
def sunpos(t, lat, lon):
    d = (t - dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc)).total_seconds() / 86400
    g = math.radians((357.529 + 0.98560028 * d) % 360); q = (280.459 + 0.98564736 * d) % 360
    L = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360); e = math.radians(23.439 - 0.00000036 * d)
    ra = math.atan2(math.cos(e) * math.sin(L), math.cos(L)); dec = math.asin(math.sin(e) * math.sin(L))
    gmst = (18.697374558 + 24.06570982441908 * d) % 24; ha = math.radians((gmst * 15 + lon) % 360) - ra
    la = math.radians(lat); alt = math.asin(math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(ha))
    az = math.atan2(-math.sin(ha), math.tan(dec) * math.cos(la) - math.sin(la) * math.cos(ha))
    return math.degrees(alt), (math.degrees(az) + 360) % 360
def dest(lat, lon, az, km):
    d = km / 6371; a = math.radians(az); la1, lo1 = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(a))
    lo2 = lo1 + math.atan2(math.sin(a) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2)); return math.degrees(la2), math.degrees(lo2)
DIRS, KMS = [0, 45, 90, 135, 180, 225, 270, 315], [16, 32]
pts = [(lat, lon)] + [dest(lat, lon, az, k) for az in DIRS for k in KMS]
out = []
r = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": ",".join(f"{a:.3f}" for a, _ in pts), "longitude": ",".join(f"{b:.3f}" for _, b in pts),
    "minutely_15": "precipitation,direct_normal_irradiance", "hourly": "precipitation_probability,precipitation,cloud_cover,weather_code,sunshine_duration",
    "start_date": day, "end_date": day, "timezone": "GMT"}, timeout=60)
J = r.json(); J = J if isinstance(J, list) else [J]
m = J[0]["minutely_15"]; h = J[0]["hourly"]
out.append("15-min replay of the 'near you' rule (sun 3-40 deg, direct sun >=120 W/m2 at you, >=0.15 mm/15min shower 16 or 32 km opposite the sun, no shower 16 km toward the sun):")
for i, ts in enumerate(m["time"]):
    t = dt.datetime.fromisoformat(ts).replace(tzinfo=dt.timezone.utc); alt, az = sunpos(t, lat, lon)
    if alt < 0: continue
    anti = (az + 180) % 360; oi = min(range(8), key=lambda k: abs(((DIRS[k] - anti + 540) % 360) - 180)); ti = (oi + 4) % 8
    near_o, far_o = J[1 + oi * 2]["minutely_15"]["precipitation"][i] or 0, J[2 + oi * 2]["minutely_15"]["precipitation"][i] or 0
    near_t = J[1 + ti * 2]["minutely_15"]["precipitation"][i] or 0; dni = m["direct_normal_irradiance"][i] or 0
    ring_max = max((J[1 + k]["minutely_15"]["precipitation"][i] or 0) for k in range(16))
    ok = 3 <= alt <= 40 and dni >= 120 and max(near_o, far_o) >= 0.15 and near_t < 0.15
    span = [k for k in range(i - 2, i + 3) if 0 <= k < len(m["time"])]
    side = (oi + 1) % 8
    sun_k = lambda k: (m["direct_normal_irradiance"][k] or 0) >= 120
    rain_k = lambda k: max(J[1 + oi * 2]["minutely_15"]["precipitation"][k] or 0, J[2 + oi * 2]["minutely_15"]["precipitation"][k] or 0, J[1 + side * 2]["minutely_15"]["precipitation"][k] or 0) >= 0.15
    new = 3 <= alt <= 42 and any(sun_k(k) for k in span) and any(rain_k(k) for k in span) and not (near_t >= 0.15 and not sun_k(i))
    lt = (t - dt.timedelta(hours=8)).strftime("%H:%M")
    out.append(f"{lt} PT sun {alt:4.1f}deg dni {dni:5.0f} here_rain {m['precipitation'][i] or 0:.2f} opp({DIRS[oi]}) {near_o:.2f}/{far_o:.2f} toward {near_t:.2f} ringmax {ring_max:.2f} -> old {'RAINBOW' if ok else '-'} | new {'RAINBOW' if new else '-'}")
out.append("\nhourly rule (main score): showers = rain chance 30-59%, or clearing after rain; sun under 40 deg; cloud < 90%:")
for i, ts in enumerate(h["time"]):
    t = dt.datetime.fromisoformat(ts).replace(tzinfo=dt.timezone.utc); alt, _ = sunpos(t, lat, lon)
    if alt < -1: continue
    pop, cc = h["precipitation_probability"][i], h["cloud_cover"][i]; prev = h["precipitation_probability"][i - 1] if i else 0; prevr = h["precipitation"][i - 1] if i else 0
    mode = "rain" if (pop or 0) >= 60 else "clearing" if ((prev or 0) >= 60 or (prevr or 0) >= 1) and (pop or 0) < 40 and cc < 90 else "showers" if (pop or 0) >= 30 else "-"
    rb = mode in ("showers", "clearing") and alt < 40 and cc < 90
    sun = h["sunshine_duration"][i]; code = h["weather_code"][i]
    showery = mode in ("showers", "clearing") or code in (80, 81, 82, 95) or ((pop or 0) >= 25 and (h["precipitation"][i] or 0) > 0)
    rb2 = showery and -1 < alt < 42 and ((sun or 0) >= 600 if sun is not None else cc < 90)
    out.append(f"{(t - dt.timedelta(hours=8)).strftime('%H:%M')} PT pop {pop} precip {h['precipitation'][i]} cloud {cc} code {h['weather_code'][i]} sun {round((sun or 0) / 60)} min mode {mode} -> old {'RAINBOW' if rb else '-'} | new {'RAINBOW' if rb2 else '-'}")
out.append("\nairport reports (present weather, sky):")
for st in ("TTD", "PDX", "VUO"):
    try:
        t = requests.get("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py", params=[("station", st), ("data", "wxcodes"), ("data", "skyc1"), ("data", "skyl1"), ("data", "skyc2"), ("data", "skyl2"), ("data", "p01i"),
            ("tz", "America/Los_Angeles"), ("format", "onlycomma"), ("sts", day + "T15:00Z"), ("ets", (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat() + "T01:30Z"), ("report_type", "3"), ("report_type", "4")], timeout=60).text
        for row in csv.DictReader(io.StringIO(t)): out.append(f"{st} {row['valid'][11:16]} wx={row['wxcodes']} sky={row['skyc1']}{row['skyl1']} {row['skyc2']}{row['skyl2']} precip={row['p01i']}")
    except Exception as e: out.append(f"{st}: {e}")
open("ux/rainbow.txt", "w").write("\n".join(out)); print("\n".join(out[:5]))
