"""Fog model backtest (Pacific Northwest stations, 2022 onward).

Label   : fog at dawn at an airport weather station (IEM ASOS archive): visibility <= 1 mile, or a FG present-weather
          report, in any routine report from 1 h before to 2 h after sunrise.
Features: only what is known the evening before (02 UTC, ~6 PM Pacific):
          - the forecast for dawn from the historical forecast archive (Open-Meteo, best-match model): 2 m temperature,
            dewpoint, wind, low cloud, visibility, 925/850 hPa temperatures (inversion), rain in the prior 24 h
          - the evening's observed temperature-dewpoint spread, wind and sky at the station
          - fog persistence (fog observed that morning) and the station's month fog rate from training years
Baseline: what the raw forecast says (dawn visibility < 1 km or low cloud >= 90% with spread <= 1 C), i.e. today's
          rule-based approach. Split: train on dawns before 2025-07-01, test on everything after (two fog seasons).
Output  : ux/fogbt.txt (+ ux/fogbt_data.csv.gz for reuse)."""
import datetime as dt, io, json, math, os, subprocess, sys, time
sys.path.insert(0, ".")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "scikit-learn", "pandas"], check=False)
import numpy as np, pandas as pd, requests
from pipeline.sunlite import sun_times

os.makedirs("ux", exist_ok=True); OUT = []
def log(*a): OUT.append(" ".join(str(x) for x in a)); print(*a, flush=True)
S = requests.Session(); S.headers["User-Agent"] = "ShotSpots research (github.com/estaugaa/shotspots)"
START, END = dt.date(2024, 2, 1), dt.date.today() - dt.timedelta(days=2)
# airport stations: valley floor, Gorge, coast, east side
ST = {"PDX": (45.5958, -122.6092), "TTD": (45.5512, -122.4092), "VUO": (45.6205, -122.6565), "HIO": (45.5404, -122.9498), "SPB": (45.7728, -122.8622),
      "KLS": (46.1180, -122.8986), "UAO": (45.2471, -122.7700), "MMV": (45.1944, -123.1361), "SLE": (44.9095, -123.0026), "EUG": (44.1246, -123.2119),
      "CVO": (44.4972, -123.2894), "DLS": (45.6187, -121.1673), "OLM": (46.9725, -122.9025), "TIW": (47.2679, -122.5781), "PWT": (47.4902, -122.7648),
      "AST": (46.1580, -123.8787), "ONP": (44.5804, -124.0579), "RDM": (44.2541, -121.1500), "YKM": (46.5682, -120.5440), "BLI": (48.7928, -122.5375)}


def get(url, params, tries=4):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=180)
            if r.status_code == 200: return r
            time.sleep(10 * (i + 1))
        except Exception:
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"failed {url}")


def asos(st):
    r = get("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py", {"station": st, "data": ["tmpf", "dwpf", "sknt", "vsby", "wxcodes", "skyc1", "skyl1"],
            "year1": START.year, "month1": START.month, "day1": START.day, "year2": END.year, "month2": END.month, "day2": END.day,
            "tz": "Etc/UTC", "format": "onlycomma", "latlon": "no", "missing": "empty", "trace": "empty", "direct": "no", "report_type": [3, 4]})
    d = pd.read_csv(io.StringIO(r.text), na_values=["", "M"])
    d["t"] = pd.to_datetime(d["valid"], utc=True)
    return d


HV = ["temperature_2m", "dew_point_2m", "wind_speed_10m", "cloud_cover_low", "visibility", "precipitation", "temperature_925hPa", "temperature_850hPa"]
def fcst(lat, lon):
    """Day-ahead forecasts only (issued ~24 h before the valid time): the previous-runs archive. The stitched
    historical-forecast archive leaks (its dawn values come from runs started around dawn)."""
    parts = []
    y0 = START
    while y0 < END:
        y1 = min(END, dt.date(y0.year, 12, 31))
        r = get("https://previous-runs-api.open-meteo.com/v1/forecast", {"latitude": lat, "longitude": lon, "start_date": y0.isoformat(), "end_date": y1.isoformat(),
                "hourly": ",".join(v + "_previous_day1" for v in HV), "models": "gfs_seamless", "timezone": "UTC", "wind_speed_unit": "kmh"})
        h = r.json().get("hourly") or {}
        if h: parts.append(pd.DataFrame(h))
        y0 = y1 + dt.timedelta(days=1); time.sleep(1)
    f = pd.concat(parts); f["t"] = pd.to_datetime(f["time"], utc=True); f = f.set_index("t").drop(columns=["time"])
    f.columns = [c.replace("_previous_day1", "").replace("_gfs_seamless", "") for c in f.columns]
    for v in HV:
        if v not in f.columns: f[v] = np.nan
    return f


def rows_for(st, lat, lon):
    a = asos(st); f = fcst(lat, lon)
    a["fogobs"] = (a["vsby"] <= 1.0) | a["wxcodes"].fillna("").str.contains(r"\bFG\b|FZFG")
    out = []
    d = START + dt.timedelta(days=1)
    while d <= END:
        sr, _ = sun_times(lat, lon, d)
        if sr:
            sr = pd.Timestamp(sr).tz_localize("UTC") if pd.Timestamp(sr).tzinfo is None else pd.Timestamp(sr)
            w = a[(a.t >= sr - pd.Timedelta(hours=1)) & (a.t <= sr + pd.Timedelta(hours=2))]
            if len(w) >= 2:
                eve = pd.Timestamp(dt.datetime.combine(d, dt.time(2, 0)), tz="UTC")   # 02 UTC of the dawn date = previous evening Pacific
                ev = a[(a.t >= eve - pd.Timedelta(hours=1.5)) & (a.t <= eve)]
                prev_sr, _ = sun_times(lat, lon, d - dt.timedelta(days=1))
                prev_sr = pd.Timestamp(prev_sr).tz_localize("UTC") if pd.Timestamp(prev_sr).tzinfo is None else pd.Timestamp(prev_sr)
                pw = a[(a.t >= prev_sr - pd.Timedelta(hours=1)) & (a.t <= prev_sr + pd.Timedelta(hours=2))]
                fh = f.loc[(f.index >= sr.floor("h") - pd.Timedelta(hours=1)) & (f.index <= sr.ceil("h"))]
                f24 = f.loc[(f.index > eve - pd.Timedelta(hours=24)) & (f.index <= eve)]
                fn = f.loc[(f.index > eve) & (f.index <= sr)]
                if len(fh) and len(ev):
                    m = fh.mean(numeric_only=True)
                    out.append({"st": st, "date": d.isoformat(), "month": d.month, "y": int(w.fogobs.any()),
                        "f_t": m.temperature_2m, "f_td": m.dew_point_2m, "f_spread": m.temperature_2m - m.dew_point_2m, "f_wind": m.wind_speed_10m,
                        "f_low": m.cloud_cover_low, "f_vis": m.visibility, "f_inv925": m.temperature_925hPa - m.temperature_2m, "f_inv850": m.temperature_850hPa - m.temperature_2m,
                        "f_rain24": f24.precipitation.sum(), "f_night_low": fn.cloud_cover_low.mean(), "f_night_wind": fn.wind_speed_10m.mean(),
                        "o_spread": ((ev.tmpf - ev.dwpf) * 5 / 9).mean(), "o_wind": ev.sknt.mean(), "o_clear": float((ev.skyc1.fillna("").isin(["CLR", "SKC", "FEW"])).mean()),
                        "o_fog_today": int(pw.fogobs.any()) if len(pw) else np.nan})
        d += dt.timedelta(days=1)
    return out


rows = []
for st, (la, lo) in ST.items():
    try:
        r = rows_for(st, la, lo); rows += r; log(f"{st}: {len(r)} dawns, fog rate {np.mean([x['y'] for x in r]):.3f}")
    except Exception as e:
        log(f"{st}: FAILED {str(e)[:150]}")
D = pd.DataFrame(rows); D.to_csv("ux/fogbt2_data.csv.gz", index=False)
log(f"forecast columns present: {[c for c in HV]}"); log(f"\nrows {len(D)}, stations {D.st.nunique()}, fog dawns {int(D.y.sum())} ({D.y.mean():.3f})")

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, average_precision_score, precision_recall_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

D["date"] = pd.to_datetime(D["date"]); tr = D[D.date < "2025-07-01"].copy(); te = D[D.date >= "2025-07-01"].copy()
clim = tr.groupby(["st", "month"]).y.mean().rename("clim"); D = D.join(clim, on=["st", "month"]); tr = D[D.date < "2025-07-01"].copy(); te = D[D.date >= "2025-07-01"].copy()
for X in (tr, te): X["clim"] = X["clim"].fillna(tr.y.mean())
FEAT = ["f_t", "f_td", "f_spread", "f_wind", "f_low", "f_vis", "f_inv925", "f_inv850", "f_rain24", "f_night_low", "f_night_wind", "o_spread", "o_wind", "o_clear", "o_fog_today", "clim", "month_sin", "month_cos"]
for X in (tr, te): X["month_sin"] = np.sin(2 * np.pi * X.month / 12); X["month_cos"] = np.cos(2 * np.pi * X.month / 12)
log(f"train {len(tr)} ({tr.date.min().date()}..{tr.date.max().date()}, fog {tr.y.mean():.3f}) | test {len(te)} ({te.date.min().date()}..{te.date.max().date()}, fog {te.y.mean():.3f})")

def report(name, p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4); pr, rc, th = precision_recall_curve(y, p)
    r50 = max([r for pp, r in zip(pr, rc) if pp >= 0.5] or [0]); r70 = max([r for pp, r in zip(pr, rc) if pp >= 0.7] or [0])
    log(f"{name:<28} Brier {brier_score_loss(y, p):.4f}  logloss {log_loss(y, p):.4f}  AUC {roc_auc_score(y, p):.3f}  PR-AUC {average_precision_score(y, p):.3f}  recall@precision50 {r50:.2f}  recall@precision70 {r70:.2f}")
    return p

y = te.y.values
log("\nTEST (unseen period)")
report("climatology (station x month)", te.clim.values, y)
base = (((te.f_vis < 1000) | ((te.f_low >= 90) & (te.f_spread <= 1.0))).astype(float) * 0.8 + 0.02).values
report("raw forecast rule (baseline)", base, y)
lr = make_pipeline(SimpleImputer(), StandardScaler(), LogisticRegression(max_iter=2000, C=0.5)).fit(tr[FEAT], tr.y)
p_lr = report("logistic regression", lr.predict_proba(te[FEAT])[:, 1], y)
gb = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0).fit(tr[FEAT], tr.y)
p_gb = report("gradient boosting", gb.predict_proba(te[FEAT])[:, 1], y)

log("\nRELIABILITY (gradient boosting, test): predicted bin -> observed fog rate (n)")
bins = np.array([0, .05, .1, .2, .3, .5, .7, 1.0001])
for a, b in zip(bins[:-1], bins[1:]):
    m = (p_gb >= a) & (p_gb < b)
    if m.sum(): log(f"  {a:.2f}-{b:.2f}: {y[m].mean():.3f} (n={m.sum()})")
log("\nBY STATION (test): station fog-rate, AUC gb vs baseline")
for st, g in te.assign(p=p_gb, b=base).groupby("st"):
    if g.y.nunique() > 1: log(f"  {st}: rate {g.y.mean():.3f}  AUC gb {roc_auc_score(g.y, g.p):.3f}  base {roc_auc_score(g.y, g.b):.3f}")
log("\nLOGISTIC COEFFICIENTS (standardized)")
co = lr[-1].coef_[0]
for f, c in sorted(zip(FEAT, co), key=lambda x: -abs(x[1])): log(f"  {f:<14} {c:+.3f}")
# leave-stations-out check: train on 15 stations, test on the other 5 (same test period)
rng = np.random.default_rng(1); sts = sorted(D.st.unique()); hold = list(rng.choice(sts, 5, replace=False))
gb2 = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0).fit(tr[~tr.st.isin(hold)][FEAT].drop(columns=["clim"]), tr[~tr.st.isin(hold)].y)
th = te[te.st.isin(hold)]
log(f"\nUNSEEN STATIONS {hold} (no station climatology): AUC {roc_auc_score(th.y, gb2.predict_proba(th[FEAT].drop(columns=['clim']))[:, 1]):.3f}, baseline {roc_auc_score(th.y, base[te.st.isin(hold).values]):.3f}")
open("ux/fogbt2.txt", "w").write("\n".join(OUT))
