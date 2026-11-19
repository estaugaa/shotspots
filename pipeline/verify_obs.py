"""Free forecast scoring from airport reports. Every GOES run, metar.py keeps the METARs taken near sunrise and
sunset (data/archive/obs/, kept indefinitely; the last 60 days are used here). Daily, this matches each one to what the forecast said a day earlier at
that airport (Open-Meteo previous-runs API, HRRR in the US; keyless) and scores three events:

  fog        reported visibility ≤ 1 mi or FG           vs  forecast visibility ≤ 1,600 m (the model's own visibility only)
  low cloud  BKN/OVC at or below 6,500 ft (any layer)   vs  forecast low cloud ≥ 70 %
  overcast   BKN/OVC below 12,000 ft                    vs  forecast total cloud ≥ 70 %

Like with like (method 2, Nov 18): Open-Meteo's "low cloud" is cover up to ~2 km (6,500 ft). Method 1 compared it with a
ceiling ≤ 1,500 ft and scored few/scattered and 1,500-6,500 ft decks as clear, which inflated false alarms and the bias;
it also counted "low cloud ≥ 95 %" as a fog forecast where the archive had no visibility. Observed low cover now comes
from every reported layer (IEM ASOS archive, free): the largest of FEW 19 / SCT 44 / BKN 75 / OVC 100 % at or below
6,500 ft. Bias = forecast low cloud minus that. For each event: hits, misses, false alarms, correct negatives, hit rate,
false-alarm ratio, accuracy vs always guessing the usual answer. Writes feed/verify_obs.json."""
import datetime as dt
from collections import defaultdict
from .common import http, read_json, write_json, utcnow, iso, log, DATA, soft_fail

LOW_TOP_FT = 6500                                     # Open-Meteo cloud_cover_low: up to ~2 km
COVER = {"FEW": 19, "SCT": 44, "BKN": 75, "OVC": 100, "VV": 100, "CLR": 0, "SKC": 0, "NSC": 0, "NCD": 0}
CLEAR = ("CLR", "SKC", "NSC", "NCD")


def low_cover(row):
    """Observed low-cloud cover (%) from an IEM ASOS row: the largest layer cover at or below 6,500 ft; 0 when clear
    or all layers are higher; None when the sky wasn't reported."""
    layers = []
    for i in (1, 2, 3):
        c = (row.get(f"skyc{i}") or "").strip()
        if c in ("", "M"):
            continue
        try:
            base = float(row.get(f"skyl{i}"))
        except (TypeError, ValueError):
            base = None
        layers.append((c, base))
    if not layers:
        return None
    if all(c in CLEAR for c, _ in layers):
        return 0
    return max([COVER.get(c, 0) for c, b in layers if b is not None and b <= LOW_TOP_FT] or [0])


def _iem_id(sid):
    return sid[1:] if len(sid) == 4 and sid.startswith("K") else sid   # IEM uses FAA ids for US stations (KPDX -> PDX)


def _iem_low(stations, start, end):
    """{station: {"YYYY-MM-DDTHH:00": low cover %}}: the routine METAR nearest each hour, within 30 min."""
    from .obs import asos_rows
    import time
    out = {}
    for s in stations:
        rows = None
        for attempt in range(3):   # IEM answers "Too many requests" as a page with no rows: pause and retry
            time.sleep(1 + 20 * attempt)
            try:
                rows = asos_rows(_iem_id(s["id"]), start, end)
            except Exception as e:
                soft_fail("verify_obs: IEM station fetch failed", e); rows = None; continue
            if rows and "valid" in rows[0]:
                break
            rows = None
        if not rows:
            soft_fail("verify_obs: IEM gave no rows (rate limit or no data)")
            continue
        best = {}
        for r in rows:
            lc = low_cover(r)
            if lc is None:
                continue
            try:
                t = dt.datetime.strptime(r["valid"], "%Y-%m-%d %H:%M")
            except Exception as e:
                soft_fail("verify_obs: IEM row with bad time", e)
                continue
            h = (t + dt.timedelta(minutes=30)).replace(minute=0)
            d = abs((t - h).total_seconds())
            if d <= 1800 and (h not in best or d < best[h][0]):
                best[h] = (d, lc)
        out[s["id"]] = {h.strftime("%Y-%m-%dT%H:00"): lc for h, (_, lc) in best.items()}
    return out



VARS = ("visibility_previous_day1", "cloud_cover_low_previous_day1", "cloud_cover_previous_day1")


def _prev(stations):
    """Hourly forecasts made 1 day before, for many points in one call (Open-Meteo accepts comma lists). The default
    (HRRR-first) archive keeps total cloud but not low cloud or visibility, so missing fields are filled from GFS."""
    out = {}
    for i in range(0, len(stations), 40):
        ch = stations[i:i + 40]
        base = {"latitude": ",".join(str(s["lat"]) for s in ch), "longitude": ",".join(str(s["lon"]) for s in ch), "past_days": 30, "forecast_days": 1, "timezone": "GMT", "hourly": ",".join(VARS)}
        got = {}
        for model in (None, "gfs_seamless", "ecmwf_ifs025"):
            missing = [v for v in VARS if not any(any(x is not None for x in got.get(s["id"], {}).get(v, [])) for s in ch)]
            if not missing:
                break
            try:
                j = http("https://previous-runs-api.open-meteo.com/v1/forecast", params={**base, **({"models": model} if model else {})}, timeout=120).json()
            except Exception as e:
                log.warning("previous-runs %s: %s", model, e); continue
            if isinstance(j, dict) and j.get("error"):
                log.warning("previous-runs refused %s: %s", model, j.get("reason")); continue
            rows = j if isinstance(j, list) else [j]
            if i == 0 and rows:
                h0 = rows[0].get("hourly") or {}
                log.info("previous-runs %s non-null %s", model or "default", {k: sum(v is not None for v in vv) for k, vv in h0.items() if k != "time"})
            for s, r in zip(ch, rows):
                h = r.get("hourly") or {}
                g = got.setdefault(s["id"], {"time": h.get("time", [])})
                for v in missing:
                    if any(x is not None for x in h.get(v) or []):
                        g[v] = h[v]
        for s in ch:
            g = got.get(s["id"]) or {}
            tt = g.get("time", [])
            col = lambda v: g.get(v) or [None] * len(tt)
            out[s["id"]] = {t: (a, b, c) for t, a, b, c in zip(tt, col(VARS[0]), col(VARS[1]), col(VARS[2]))}
    return out


ARCH = DATA / "fc_archive.json"


def _snapshot(stations):
    """The archive API keeps only total cloud, so save tomorrow's low cloud and visibility forecast ourselves each day.
    After a few days these let the fog and low-cloud scores fill in."""
    arch = read_json(ARCH, {}) or {}
    tomorrow = (utcnow() + dt.timedelta(days=1)).strftime("%Y-%m-%d")
    for i in range(0, len(stations), 40):
        ch = stations[i:i + 40]
        try:
            j = http("https://api.open-meteo.com/v1/forecast", params={"latitude": ",".join(str(s["lat"]) for s in ch), "longitude": ",".join(str(s["lon"]) for s in ch),
                     "hourly": "visibility,cloud_cover_low", "forecast_days": 3, "timezone": "GMT"}, timeout=120).json()
        except Exception as e:
            log.warning("snapshot: %s", e); continue
        for s, r in zip(ch, j if isinstance(j, list) else [j]):
            h = r.get("hourly") or {}
            a = arch.setdefault(s["id"], {})
            for t, v, l in zip(h.get("time", []), h.get("visibility", []), h.get("cloud_cover_low", [])):
                if t.startswith(tomorrow) and t not in a:
                    a[t] = [v, l]
    cut = (utcnow() - dt.timedelta(days=60)).strftime("%Y-%m-%dT%H:%M")
    arch = {k: {t: x for t, x in v.items() if t >= cut} for k, v in arch.items()}
    write_json(ARCH, arch)
    return arch


EVE = DATA / "fc_archive_eve.json"


def snapshot_evening():
    """Save the evening forecast (visibility, low cloud, humidity, wind) for the next 24 hours at every verified airport,
    so fog can be scored at the lead people plan with (the evening before, ~12 h; tools/fogrule.py). Runs after the
    fog-chance job (~03 UTC). The archive API keeps none of these at that lead."""
    from .metar import history
    st = {}
    for o in history(60):
        st.setdefault(o["id"], {"id": o["id"], "lat": o["lat"], "lon": o["lon"]})
    arch = read_json(EVE, {}) or {}; now = utcnow(); end = (now + dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:00"); n = 0
    stations = list(st.values())
    for i in range(0, len(stations), 40):
        ch = stations[i:i + 40]
        try:
            j = http("https://api.open-meteo.com/v1/forecast", params={"latitude": ",".join(str(s["lat"]) for s in ch), "longitude": ",".join(str(s["lon"]) for s in ch),
                     "hourly": "visibility,cloud_cover_low,relative_humidity_2m,wind_speed_10m", "wind_speed_unit": "mph", "forecast_days": 2, "timezone": "GMT"}, timeout=120).json()
        except Exception as e:
            soft_fail("fcsnap_eve", e); continue
        for s, r in zip(ch, j if isinstance(j, list) else [j]):
            h = r.get("hourly") or {}; a = arch.setdefault(s["id"], {})
            for t, v, l, rh, w in zip(h.get("time", []), h.get("visibility", []), h.get("cloud_cover_low", []), h.get("relative_humidity_2m", []), h.get("wind_speed_10m", [])):
                if now.strftime("%Y-%m-%dT%H:00") < t <= end and t not in a:
                    a[t] = [v, l, rh, w]; n += 1
    cut = (now - dt.timedelta(days=60)).strftime("%Y-%m-%dT%H:%M")
    write_json(EVE, {k: {t: x for t, x in v.items() if t >= cut} for k, v in arch.items()})
    return f"{n} hours saved for {len(st)} airports"


def run():
    from .metar import history
    hist = history(60)
    if not hist:
        return "no airport history yet"
    st = {}
    for o in hist:
        st.setdefault(o["id"], {"id": o["id"], "lat": o["lat"], "lon": o["lon"], "name": o.get("name", o["id"])})
    fc = _prev(list(st.values()))
    try:
        arch = _snapshot(list(st.values()))
    except Exception as e:
        log.warning("snapshot failed: %s", e); arch = {}
    for sid, rows in fc.items():
        for t, (v, l, c) in list(rows.items()):
            sv = (arch.get(sid) or {}).get(t)
            if sv and (v is None or l is None):
                rows[t] = (v if v is not None else sv[0], l if l is not None else sv[1], c)
    log.info("%d reports from %d stations; forecasts for %d; sample report time %s, sample forecast times %s", len(hist), len(st), len(fc), hist[0]["t"], list(next(iter(fc.values()), {}))[:2])
    t0 = dt.date.fromisoformat(min(o["t"] for o in hist)[:10]); t1 = utcnow().date() + dt.timedelta(days=1)
    lowobs = _iem_low(list(st.values()), t0, t1)
    T = {k: defaultdict(int) for k in ("fog", "low", "ovc")}
    per = defaultdict(lambda: {k: defaultdict(int) for k in ("fog", "low", "ovc")})
    bias = []; no_vis = 0; no_layers = 0
    for o in hist:
        hr = o["t"]
        f = (fc.get(o["id"]) or {}).get(hr)
        if not f or f[2] is None:
            continue
        vis_f, low_f, cc_f = f
        events = {"ovc": (o["base_ft"] is not None and o["base_ft"] <= 12000, cc_f >= 70)}
        if vis_f is not None:
            events["fog"] = (o["fog"], vis_f <= 1600)
        else:
            no_vis += 1                            # no model visibility: not scored (method 1 used a low-cloud stand-in)
        lc = (lowobs.get(o["id"]) or {}).get(hr[:13] + ":00")
        if low_f is not None and lc is not None:
            events["low"] = (lc >= 70, low_f >= 70)
            bias.append(low_f - lc)
        elif low_f is not None:
            no_layers += 1
        for k, (obs, fct) in events.items():
            key = "hit" if obs and fct else "miss" if obs else "fa" if fct else "cn"
            T[k][key] += 1
            per[o["id"]][k][key] += 1

    def score(c):
        n = sum(c.values())
        if not n:
            return None
        h, m, fa, cn = c["hit"], c["miss"], c["fa"], c["cn"]
        base = (h + m) / n
        return {"n": n, "hit": h, "miss": m, "false_alarm": fa, "correct_no": cn, "base_rate": round(base, 3),
                "hit_rate": round(h / (h + m), 2) if h + m else None, "false_alarm_ratio": round(fa / (h + fa), 2) if h + fa else None,
                "accuracy": round((h + cn) / n, 3), "accuracy_if_always_usual": round(max(base, 1 - base), 3)}

    out = {"gen": iso(utcnow()), "method": 2, "lead": "forecast made 1 day ahead", "window": "airport reports within 45 min of sunrise or sunset, last 30 days",
           "defs": {"fog": "visibility <= 1 mi or FG vs forecast visibility <= 1,600 m (model visibility only)",
                    "low": "BKN/OVC at or below 6,500 ft vs forecast low cloud >= 70%",
                    "ovc": "BKN/OVC below 12,000 ft vs forecast total cloud >= 70%",
                    "bias": "forecast low cloud minus observed cover of layers at or below 6,500 ft"},
           "unscored": {"fog_no_model_visibility": no_vis, "low_no_reported_layers": no_layers},
           "events": {k: score(v) for k, v in T.items()}, "low_cloud_bias_pct": round(sum(bias) / len(bias), 1) if bias else None, "n_bias": len(bias),
           "stations": {sid: {"name": st[sid]["name"], **{k: score(v) for k, v in ev.items()}} for sid, ev in per.items()}}
    write_json("verify_obs.json", out)
    f = out["events"]["fog"] or {}
    return f"{sum(T['ovc'].values())} matched reports; fog hit rate {f.get('hit_rate')}, false alarms {f.get('false_alarm_ratio')}"
