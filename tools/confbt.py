"""Forecast-confidence backtest (Pacific Northwest stations, 2024 onward).

Forecasts : day-ahead cloud cover at sunrise and sunset hours from four models (Open-Meteo previous-runs archive:
            *_previous_day1 = the run issued ~24 h earlier): GFS, ECMWF IFS, ICON, GEM.
Truth     : ERA5 total cloud cover at the same hour (Open-Meteo archive).
Questions : 1) spread-skill: does model disagreement predict error?  2) does per-station/season bias correction cut
            error?  3) are probabilities for "clear (<30%)" and "overcast (>85%)" from the four-model blend + spread
            better calibrated than one model alone?  Train before 2025-11-01, test after.
Output    : ux/confbt.txt"""
import datetime as dt, json, os, subprocess, sys, time
sys.path.insert(0, ".")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "scikit-learn", "pandas", "scipy"], check=False)
import numpy as np, pandas as pd, requests
from pipeline.sunlite import sun_times
os.makedirs("ux", exist_ok=True); OUT = []
def log(*a): OUT.append(" ".join(str(x) for x in a)); print(*a, flush=True)
S = requests.Session(); S.headers["User-Agent"] = "ShotSpots research"
START, END = dt.date(2024, 2, 1), dt.date.today() - dt.timedelta(days=8)   # ERA5 lags ~5 days
ST = {"PDX": (45.5958, -122.6092), "TTD": (45.5512, -122.4092), "HIO": (45.5404, -122.9498), "KLS": (46.1180, -122.8986), "SLE": (44.9095, -123.0026),
      "EUG": (44.1246, -123.2119), "DLS": (45.6187, -121.1673), "OLM": (46.9725, -122.9025), "AST": (46.1580, -123.8787), "ONP": (44.5804, -124.0579),
      "RDM": (44.2541, -121.1500), "YKM": (46.5682, -120.5440), "BLI": (48.7928, -122.5375), "HQM": (46.9712, -123.9365), "MWH": (47.2077, -119.3202)}
MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_seamless"]


def get(url, params):
    for i in range(4):
        try:
            r = S.get(url, params=params, timeout=240)
            if r.status_code == 200: return r.json()
            log(f"  http {r.status_code}: {r.text[:160]}"); time.sleep(15 * (i + 1))
        except Exception as e:
            log(f"  err {str(e)[:120]}"); time.sleep(15 * (i + 1))
    return {}


rows = []
for st, (la, lo) in ST.items():
    j = get("https://previous-runs-api.open-meteo.com/v1/forecast", {"latitude": la, "longitude": lo, "start_date": START.isoformat(), "end_date": END.isoformat(),
            "hourly": "cloud_cover_previous_day1", "models": ",".join(MODELS), "timezone": "UTC"})
    e = get("https://archive-api.open-meteo.com/v1/archive", {"latitude": la, "longitude": lo, "start_date": START.isoformat(), "end_date": END.isoformat(), "hourly": "cloud_cover", "timezone": "UTC"})
    h = j.get("hourly") or {}; eh = e.get("hourly") or {}
    if not h or not eh: log(f"{st}: missing data ({list(h)[:4]} / {list(eh)[:2]})"); continue
    F = pd.DataFrame(h); F["t"] = pd.to_datetime(F.time, utc=True); F = F.set_index("t")
    E = pd.DataFrame(eh); E["t"] = pd.to_datetime(E.time, utc=True); E = E.set_index("t")["cloud_cover"]
    cols = {m: next((c for c in F.columns if c.startswith("cloud_cover_previous_day1") and m in c), None) for m in MODELS}
    if st == "PDX": log(f"columns: {list(F.columns)[:8]} -> {cols}")
    d = START; n = 0
    while d <= END:
        sr, ss = sun_times(la, lo, d)
        for kind, t in (("sunrise", sr), ("sunset", ss)):
            if not t: continue
            t = pd.Timestamp(t); t = t.tz_localize("UTC") if t.tzinfo is None else t; t = t.round("h")
            if t not in F.index or t not in E.index: continue
            v = {m: F.at[t, c] if c else np.nan for m, c in cols.items()}
            if sum(pd.notna(x) for x in v.values()) < 3 or pd.isna(E.at[t]): continue
            rows.append({"st": st, "date": d, "kind": kind, "month": d.month, "truth": E.at[t], **{"m_" + m.split("_")[0]: v[m] for m in MODELS}}); n += 1
        d += dt.timedelta(days=1)
    log(f"{st}: {n} windows"); time.sleep(1)

D = pd.DataFrame(rows); MC = [c for c in D.columns if c.startswith("m_")]
D["mean"] = D[MC].mean(axis=1); D["spread"] = D[MC].std(axis=1); D["err"] = (D["mean"] - D.truth).abs()
D["date"] = pd.to_datetime(D.date); tr, te = D[D.date < "2025-11-01"].copy(), D[D.date >= "2025-11-01"].copy()
log(f"\nrows {len(D)} | train {len(tr)} | test {len(te)} ({te.date.min().date()}..{te.date.max().date()})")
log("\n1) SPREAD vs ERROR (all data): model disagreement bins -> mean absolute error of the 4-model mean")
D["sbin"] = pd.cut(D.spread, [0, 5, 10, 20, 30, 100], include_lowest=True)
for b, g in D.groupby("sbin", observed=True): log(f"  spread {str(b):<14} n={len(g):5d}  MAE {g.err.mean():5.1f}  share>30pts {(g.err > 30).mean():.2f}")
from scipy.stats import spearmanr
log(f"  Spearman(spread, error) = {spearmanr(D.spread, D.err).correlation:.3f}")
log("\n2) BIAS CORRECTION (test MAE, cloud % points)")
for m in MC + ["mean"]: log(f"  raw {m:<14} {(te[m] - te.truth).abs().mean():5.1f}")
bias = (tr["mean"] - tr.truth).groupby([tr.st, tr.kind, tr.month]).mean().rename("bias")
te = te.join(bias, on=["st", "kind", "month"]); te["bias"] = te["bias"].fillna(0)
log(f"  4-model mean, bias-corrected by station x sunrise/sunset x month: {(te['mean'] - te.bias - te.truth).abs().mean():5.1f}")
log("\n3) PROBABILITIES (test): Brier score, lower is better")
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
for name, ev in (("clear (<30%)", lambda x: x < 30), ("overcast (>85%)", lambda x: x > 85), ("partly (30-75%, best color odds)", lambda x: (x >= 30) & (x <= 75))):
    ytr, yte = ev(tr.truth).astype(int), ev(te.truth).astype(int)
    single = ev(te["m_gfs"]).astype(float) * 0.8 + 0.1
    vote = sum(ev(te[m]).astype(float) for m in MC) / len(MC) * 0.9 + 0.05
    X = lambda d: np.column_stack([d["mean"], d.spread, *(ev(d[m]).astype(float) for m in MC), np.sin(2 * np.pi * d.month / 12), np.cos(2 * np.pi * d.month / 12), (d.kind == "sunset").astype(int)])
    lr = LogisticRegression(max_iter=2000).fit(X(tr), ytr); p = lr.predict_proba(X(te))[:, 1]
    log(f"  {name:<34} base rate {yte.mean():.2f} | GFS alone {brier_score_loss(yte, single):.4f} | 4-model vote {brier_score_loss(yte, vote):.4f} | blend+spread (fitted) {brier_score_loss(yte, p):.4f} | climatology {brier_score_loss(yte, np.full(len(yte), ytr.mean())):.4f}")
    if name.startswith("partly"):
        log("    reliability (fitted): predicted -> observed (n)")
        for a, b in zip([0, .2, .4, .6, .8], [.2, .4, .6, .8, 1.01]):
            mk = (p >= a) & (p < b)
            if mk.sum() > 20: log(f"      {a:.1f}-{b:.1f}: {yte[mk].mean():.2f} (n={mk.sum()})")
open("ux/confbt.txt", "w").write("\n".join(OUT))
