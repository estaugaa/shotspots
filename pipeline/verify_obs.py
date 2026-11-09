"""Free forecast scoring from airport reports. Every GOES run, metar.py keeps the METARs taken near sunrise and
sunset (data/obs_history.json, 60 days). Daily, this matches each one to what the forecast said a day earlier at
that airport (Open-Meteo previous-runs API, HRRR in the US; keyless) and scores three events:

  fog        reported visibility ≤ 1 mi or FG   vs  forecast visibility ≤ 1,600 m
  low cloud  ceiling ≤ 1,500 ft                 vs  forecast low cloud ≥ 70 %
  overcast   BKN/OVC below 12,000 ft            vs  forecast total cloud ≥ 70 %

For each: hits, misses, false alarms, correct negatives, hit rate, false-alarm rate, accuracy vs always guessing
the usual answer, and the forecast's low-cloud bias. Writes feed/verify_obs.json."""
import datetime as dt
from collections import defaultdict
from .common import http, read_json, write_json, utcnow, iso, log, DATA

HIST = DATA / "obs_history.json"


def _prev(stations):
    """Hourly forecasts made 1 day before, for many points in one call (Open-Meteo accepts comma lists)."""
    out = {}
    for i in range(0, len(stations), 40):
        ch = stations[i:i + 40]
        base = {"latitude": ",".join(str(s["lat"]) for s in ch), "longitude": ",".join(str(s["lon"]) for s in ch), "past_days": 30, "forecast_days": 1, "timezone": "GMT"}
        j = None
        for hv in ("visibility_previous_day1,cloud_cover_low_previous_day1,cloud_cover_previous_day1", "cloud_cover_low_previous_day1,cloud_cover_previous_day1"):
            try:
                j = http("https://previous-runs-api.open-meteo.com/v1/forecast", params={**base, "hourly": hv}, timeout=120).json()
            except Exception as e:
                log.warning("previous-runs %s: %s", hv.split(",")[0], e); j = None; continue
            if isinstance(j, dict) and j.get("error"):
                log.warning("previous-runs refused %s: %s", hv.split(",")[0], j.get("reason")); j = None; continue
            break
        if j is None:
            continue
        rows = j if isinstance(j, list) else [j]
        if i == 0 and rows:
            h0 = rows[0].get("hourly") or {}
            log.info("previous-runs keys %s; non-null %s; first t %s", list(h0), {k: sum(v is not None for v in vv) for k, vv in h0.items() if k != "time"}, (h0.get("time") or [None])[:2])
        for s, r in zip(ch, rows):
            h = r.get("hourly") or {}
            tt = h.get("time", [])
            vis = h.get("visibility_previous_day1") or [None] * len(tt)
            out[s["id"]] = {t: (v, l, c) for t, v, l, c in zip(tt, vis, h.get("cloud_cover_low_previous_day1", []), h.get("cloud_cover_previous_day1", []))}
    return out


def run():
    hist = read_json(HIST, {"obs": []})["obs"]
    if not hist:
        return "no airport history yet"
    st = {}
    for o in hist:
        st.setdefault(o["id"], {"id": o["id"], "lat": o["lat"], "lon": o["lon"], "name": o.get("name", o["id"])})
    fc = _prev(list(st.values()))
    log.info("%d reports from %d stations; forecasts for %d; sample report time %s, sample forecast times %s", len(hist), len(st), len(fc), hist[0]["t"], list(next(iter(fc.values()), {}))[:2])
    T = {k: defaultdict(int) for k in ("fog", "low", "ovc")}
    per = defaultdict(lambda: {k: defaultdict(int) for k in ("fog", "low", "ovc")})
    bias = []
    for o in hist:
        hr = o["t"]
        f = (fc.get(o["id"]) or {}).get(hr)
        if not f or f[1] is None or f[2] is None:
            continue
        vis_f, low_f, cc_f = f
        if vis_f is None:   # no visibility in the forecast archive: treat a full low-cloud deck as forecast fog
            vis_f = 1000 if low_f >= 95 else 20000
        events = {"fog": (o["fog"], vis_f <= 1600), "low": (o["base_ft"] is not None and o["base_ft"] <= 1500, low_f >= 70),
                  "ovc": (o["base_ft"] is not None and o["base_ft"] <= 12000, cc_f >= 70)}
        for k, (obs, fct) in events.items():
            key = "hit" if obs and fct else "miss" if obs else "fa" if fct else "cn"
            T[k][key] += 1
            per[o["id"]][k][key] += 1
        bias.append(low_f - (90 if o["base_ft"] is not None and o["base_ft"] <= 3000 else 5))

    def score(c):
        n = sum(c.values())
        if not n:
            return None
        h, m, fa, cn = c["hit"], c["miss"], c["fa"], c["cn"]
        base = (h + m) / n
        return {"n": n, "hit": h, "miss": m, "false_alarm": fa, "correct_no": cn, "base_rate": round(base, 3),
                "hit_rate": round(h / (h + m), 2) if h + m else None, "false_alarm_ratio": round(fa / (h + fa), 2) if h + fa else None,
                "accuracy": round((h + cn) / n, 3), "accuracy_if_always_usual": round(max(base, 1 - base), 3)}

    out = {"gen": iso(utcnow()), "lead": "forecast made 1 day ahead", "window": "airport reports within 45 min of sunrise or sunset, last 30 days",
           "events": {k: score(v) for k, v in T.items()}, "low_cloud_bias_pct": round(sum(bias) / len(bias), 1) if bias else None,
           "stations": {sid: {"name": st[sid]["name"], **{k: score(v) for k, v in ev.items()}} for sid, ev in per.items()}}
    write_json("verify_obs.json", out)
    f = out["events"]["fog"] or {}
    return f"{sum(T['ovc'].values())} matched reports; fog hit rate {f.get('hit_rate')}, false alarms {f.get('false_alarm_ratio')}"
