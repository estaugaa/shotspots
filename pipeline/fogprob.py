"""Valley-fog chance at dawn (shadow mode): a gradient-boosted model, backtested in tools/fogbt.py (Nov 2026: AUC 0.83 vs
0.58 for the forecast fog rule and 0.75 for station climatology, on day-ahead forecasts, unseen 2025-26 seasons).

Nightly (evening Pacific): for each airport station, predict the chance of fog (visibility <= 1 mile or FG) from 1 h
before to 2 h after tomorrow's sunrise. Features: forecast 2 m temperature, dewpoint, wind and rain (GFS via
Open-Meteo), the evening's observed temperature-dewpoint spread, wind and sky (IEM ASOS), fog that morning, and the
station's month fog rate. The model is (re)trained weekly from ~2 years of history and cached in data/.

Shadow mode: predictions go to feed/fogprob.json and are logged to data/fogprob_log.csv; each run scores the
previous dawns against what the station reported, so the app only uses this once it holds up live."""
import datetime as dt, io, json, math, pickle, time
import numpy as np
from .common import http, write_json, read_json, DATA, log, utcnow, iso
from .sunlite import sun_times

ST = {"PDX": (45.5958, -122.6092), "TTD": (45.5512, -122.4092), "VUO": (45.6205, -122.6565), "HIO": (45.5404, -122.9498), "SPB": (45.7728, -122.8622),
      "KLS": (46.1180, -122.8986), "UAO": (45.2471, -122.7700), "MMV": (45.1944, -123.1361), "SLE": (44.9095, -123.0026), "EUG": (44.1246, -123.2119),
      "CVO": (44.4972, -123.2894), "DLS": (45.6187, -121.1673), "OLM": (46.9725, -122.9025), "TIW": (47.2679, -122.5781), "PWT": (47.4902, -122.7648),
      "AST": (46.1580, -123.8787), "ONP": (44.5804, -124.0579), "RDM": (44.2541, -121.1500), "YKM": (46.5682, -120.5440), "BLI": (48.7928, -122.5375)}
FEAT = ["f_t", "f_td", "f_spread", "f_wind", "f_rain24", "f_night_wind", "o_spread", "o_wind", "o_clear", "o_fog_today", "clim", "month_sin", "month_cos"]
MODEL = DATA / "fogprob_model.pkl"
LOGF = DATA / "fogprob_log.csv"


def _asos(st, d0, d1):
    import pandas as pd
    r = http("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py", params={"station": st, "data": ["tmpf", "dwpf", "sknt", "vsby", "wxcodes", "skyc1"],
             "year1": d0.year, "month1": d0.month, "day1": d0.day, "year2": d1.year, "month2": d1.month, "day2": d1.day, "tz": "Etc/UTC", "format": "onlycomma",
             "latlon": "no", "missing": "empty", "trace": "empty", "direct": "no", "report_type": [3, 4]}, timeout=180)
    a = pd.read_csv(io.StringIO(r.text), na_values=["", "M"]); a["t"] = pd.to_datetime(a["valid"], utc=True)
    a["fogobs"] = (a["vsby"] <= 1.0) | a["wxcodes"].fillna("").str.contains(r"\bFG\b|FZFG"); return a


def _sr(lat, lon, d):
    import pandas as pd
    s, _ = sun_times(lat, lon, d); t = pd.Timestamp(s); return t.tz_localize("UTC") if t.tzinfo is None else t


def _obs_feats(a, lat, lon, d):
    """Evening (02 UTC of dawn date d) observations + fog the morning before."""
    import pandas as pd
    eve = pd.Timestamp(dt.datetime.combine(d, dt.time(2, 0)), tz="UTC")
    ev = a[(a.t >= eve - pd.Timedelta(hours=1.5)) & (a.t <= eve)]
    ps = _sr(lat, lon, d - dt.timedelta(days=1)); pw = a[(a.t >= ps - pd.Timedelta(hours=1)) & (a.t <= ps + pd.Timedelta(hours=2))]
    if not len(ev): return None
    return {"o_spread": float(((ev.tmpf - ev.dwpf) * 5 / 9).mean()), "o_wind": float(ev.sknt.mean()), "o_clear": float(ev.skyc1.fillna("").isin(["CLR", "SKC", "FEW"]).mean()),
            "o_fog_today": float(pw.fogobs.any()) if len(pw) else np.nan}


def _label(a, lat, lon, d):
    import pandas as pd
    s = _sr(lat, lon, d); w = a[(a.t >= s - pd.Timedelta(hours=1)) & (a.t <= s + pd.Timedelta(hours=2))]
    return int(w.fogobs.any()) if len(w) >= 2 else None


def _fc_feats(f, sr, eve):
    m = f[(f.index >= sr.floor("h") - np.timedelta64(1, "h")) & (f.index <= sr.ceil("h"))].mean(numeric_only=True)
    f24 = f[(f.index > eve - np.timedelta64(24, "h")) & (f.index <= eve)]; fn = f[(f.index > eve) & (f.index <= sr)]
    return {"f_t": m.temperature_2m, "f_td": m.dew_point_2m, "f_spread": m.temperature_2m - m.dew_point_2m, "f_wind": m.wind_speed_10m,
            "f_rain24": f24.precipitation.sum(), "f_night_wind": fn.wind_speed_10m.mean()}


def _train():
    """~2 years of day-ahead forecasts (previous-runs archive) + ASOS labels -> gradient-boosted classifier."""
    import pandas as pd
    from sklearn.ensemble import HistGradientBoostingClassifier
    d0, d1 = dt.date(2024, 2, 1), dt.date.today() - dt.timedelta(days=2); rows = []
    for st, (la, lo) in ST.items():
        try:
            a = _asos(st, d0, d1); parts = []; y0 = d0
            while y0 < d1:
                y1 = min(d1, dt.date(y0.year, 12, 31))
                h = http("https://previous-runs-api.open-meteo.com/v1/forecast", params={"latitude": la, "longitude": lo, "start_date": y0.isoformat(), "end_date": y1.isoformat(),
                         "hourly": "temperature_2m_previous_day1,dew_point_2m_previous_day1,wind_speed_10m_previous_day1,precipitation_previous_day1",
                         "models": "gfs_seamless", "timezone": "UTC", "wind_speed_unit": "kmh"}, timeout=240).json().get("hourly") or {}
                if h: parts.append(pd.DataFrame(h))
                y0 = y1 + dt.timedelta(days=1); time.sleep(1)
            f = pd.concat(parts); f["t"] = pd.to_datetime(f.time, utc=True); f = f.set_index("t").drop(columns=["time"])
            f.columns = [c.replace("_previous_day1", "").replace("_gfs_seamless", "") for c in f.columns]
            d = d0 + dt.timedelta(days=1)
            while d <= d1:
                y = _label(a, la, lo, d); o = _obs_feats(a, la, lo, d)
                if y is not None and o:
                    sr = _sr(la, lo, d); eve = pd.Timestamp(dt.datetime.combine(d, dt.time(2, 0)), tz="UTC")
                    rows.append({"st": st, "month": d.month, "y": y, **o, **_fc_feats(f, sr, eve)})
                d += dt.timedelta(days=1)
        except Exception as e:
            log.info(f"fogprob train {st}: {e}")
    D = pd.DataFrame(rows)
    clim = D.groupby(["st", "month"]).y.mean().to_dict()
    D["clim"] = [clim[(s, m)] for s, m in zip(D.st, D.month)]
    D["month_sin"] = np.sin(2 * np.pi * D.month / 12); D["month_cos"] = np.cos(2 * np.pi * D.month / 12)
    gb = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0).fit(D[FEAT], D.y)
    MODEL.write_bytes(pickle.dumps({"model": gb, "clim": {f"{s}|{m}": v for (s, m), v in clim.items()}, "rate": float(D.y.mean()), "n": len(D), "at": iso(utcnow())}))
    return len(D)


def run():
    import pandas as pd
    trained = ""
    old = pickle.loads(MODEL.read_bytes()) if MODEL.exists() else None
    if not old or (utcnow() - dt.datetime.fromisoformat(old["at"].replace("Z", "+00:00"))).days >= 7:
        trained = f"retrained on {_train()} dawns; "; old = pickle.loads(MODEL.read_bytes())
    gb, clim = old["model"], old["clim"]
    today = dt.datetime.now(dt.timezone.utc).date()
    dawn = today + dt.timedelta(days=1) if dt.datetime.now(dt.timezone.utc).hour >= 2 else today   # tomorrow's dawn (Pacific evening run)
    out, logrows, scored = {}, [], []
    for st, (la, lo) in ST.items():
        try:
            a = _asos(st, today - dt.timedelta(days=3), today + dt.timedelta(days=1))
            # score past predictions for this station
            if LOGF.exists():
                L = pd.read_csv(LOGF)
                for _, r in L[(L.st == st) & L.y.isna()].iterrows():
                    dd = dt.date.fromisoformat(r.dawn)
                    if dd < today: y = _label(a, la, lo, dd); scored.append((st, r.dawn, r.p, y))
            o = _obs_feats(a, la, lo, dawn)
            h = http("https://api.open-meteo.com/v1/forecast", params={"latitude": la, "longitude": lo, "hourly": "temperature_2m,dew_point_2m,wind_speed_10m,precipitation",
                     "models": "gfs_seamless", "past_days": 1, "forecast_days": 3, "timezone": "UTC", "wind_speed_unit": "kmh"}, timeout=60).json()["hourly"]
            f = pd.DataFrame(h); f["t"] = pd.to_datetime(f.time, utc=True); f = f.set_index("t").drop(columns=["time"])
            if not o: continue
            sr = _sr(la, lo, dawn); eve = pd.Timestamp(dt.datetime.combine(dawn, dt.time(2, 0)), tz="UTC")
            x = {**o, **_fc_feats(f, sr, eve), "clim": clim.get(f"{st}|{dawn.month}", old["rate"]), "month_sin": math.sin(2 * math.pi * dawn.month / 12), "month_cos": math.cos(2 * math.pi * dawn.month / 12)}
            p = float(gb.predict_proba(pd.DataFrame([x])[FEAT])[0, 1])
            out[st] = {"lat": la, "lon": lo, "p": round(p, 3), "clim": round(x["clim"], 3), "dawn": dawn.isoformat()}
            logrows.append({"st": st, "dawn": dawn.isoformat(), "p": round(p, 4), "clim": round(x["clim"], 4), "y": None})
        except Exception as e:
            log.info(f"fogprob {st}: {e}")
    # update the log: fill labels, append new predictions (one per station+dawn)
    L = pd.read_csv(LOGF) if LOGF.exists() else pd.DataFrame(columns=["st", "dawn", "p", "clim", "y"])
    for st, dawn_s, p, y in scored:
        if y is not None: L.loc[(L.st == st) & (L.dawn == dawn_s), "y"] = y
    new = pd.DataFrame(logrows)
    if len(new): L = pd.concat([L[~(L.st + L.dawn).isin(new.st + new.dawn)], new], ignore_index=True)
    L.to_csv(LOGF, index=False)
    done = L[L.y.notna()]
    shadow = ""
    if len(done) >= 20:
        y = done.y.astype(float); bp = ((done.p - y) ** 2).mean(); bc = ((done.clim - y) ** 2).mean()
        shadow = f"shadow so far: {len(done)} dawns, fog {y.mean():.2f}, Brier model {bp:.3f} vs climatology {bc:.3f}"
    write_json("fogprob.json", {"gen": iso(utcnow()), "mode": "shadow", "dawn": dawn.isoformat(), "stations": out, "shadow": shadow})
    return f"{trained}{len(out)} stations for {dawn}; {shadow or 'shadow log building'}"
