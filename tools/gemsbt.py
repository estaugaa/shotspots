"""Hidden gems prototype (Pacific Northwest).

1. Terrain features per starter spot from AWS terrain tiles (terrarium PNG, zoom 11, ~55 m): view openness by direction,
   share of directions with a long open view, local relief, prominence, big terrain within 20 km, nearby water spots.
2. Scenic-potential model: predict photo popularity (log Commons photo count + photographers at the stand) from terrain
   + kind. Validated with spatial cross-validation (whole 1-degree tiles held out): Spearman rank correlation.
3. Gems: spots whose predicted popularity far exceeds the actual (out-of-fold residual), shown near Washougal.
Output: ux/gems.txt, ux/gems.json"""
import io, json, math, os, subprocess, sys, time, glob
sys.path.insert(0, ".")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "scikit-learn", "pandas", "pillow", "scipy"], check=False)
import numpy as np, pandas as pd, requests
from PIL import Image
os.makedirs("ux", exist_ok=True); OUT = []
def log(*a): OUT.append(" ".join(str(x) for x in a)); print(*a, flush=True)
S = requests.Session(); S.headers["User-Agent"] = "ShotSpots research"
Z = 10; TILE = {}
LAT0, LAT1, LON0, LON1 = 36.0, 49.0, -124.8, -110.0
KINDS = ["viewpoint", "lookout", "peak", "waterfall", "lake", "beach", "arch", "lighthouse", "bridge", "landmark", "cave", "hotspring", "refuge", "hotspot", "park", "garden", "tower"]


def tile(x, y):
    k = (x, y)
    if k not in TILE:
        for i in range(3):
            try:
                r = S.get(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png", timeout=60)
                a = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB")).astype(np.float32)
                TILE[k] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768; break
            except Exception:
                time.sleep(3); TILE[k] = None
    return TILE[k]


def elev(lat, lon):
    n = 2 ** Z; xf = (lon + 180) / 360 * n; yf = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    t = tile(int(xf), int(yf))
    if t is None: return np.nan
    return float(t[min(255, int((yf % 1) * 256)), min(255, int((xf % 1) * 256))])


def feats(s):
    la, lo = s["lat"], s["lon"]; z0 = elev(la, lo) + 2
    dlat = lambda m: m / 111320; dlon = lambda m: m / (111320 * math.cos(math.radians(la)))
    hz, far, rise = [], [], []
    for az in range(0, 360, 22):
        a = math.radians(az); best = -90; bigrise = -9999
        for d in list(range(150, 3000, 150)) + list(range(3000, 20001, 600)):
            z = elev(la + dlat(d * math.cos(a)), lo + dlon(d * math.sin(a)))
            if np.isnan(z): continue
            ang = math.degrees(math.atan2(z - z0, d)); best = max(best, ang)
            if d >= 3000: bigrise = max(bigrise, z - z0)
        hz.append(best); rise.append(bigrise)
    ring = [elev(la + dlat(r * math.cos(math.radians(b))), lo + dlon(r * math.sin(math.radians(b)))) for r in (500, 1000, 2000) for b in range(0, 360, 45)]
    ring5 = [elev(la + dlat(r * math.cos(math.radians(b))), lo + dlon(r * math.sin(math.radians(b)))) for r in (2500, 5000) for b in range(0, 360, 30)] + ring
    hz = np.array(hz)
    return {"z": z0, "openness": float(np.mean(90 - hz)), "open_dirs": float(np.mean(hz < 1.0)), "open_dirs3": float(np.mean(hz < 3.0)),
            "max_hz": float(hz.max()), "prominence": z0 - float(np.nanmean(ring)), "relief5": float(np.nanmax(ring5) - np.nanmin(ring5 + [z0])),
            "big_rise20": float(max(rise)), "steep": float(np.nanstd(ring))}


# spots in the region, with popularity
rows = []
for f in glob.glob("feed/seed/*_*.json"):
    la, lo = map(int, os.path.basename(f)[:-5].split("_"))
    if not (LAT0 - 1 <= la <= LAT1 and LON0 - 1 <= lo <= LON1): continue
    pp = json.load(open(f"feed/seedpop/{os.path.basename(f)}")) if os.path.exists(f"feed/seedpop/{os.path.basename(f)}") else {}
    sd = json.load(open(f"feed/stands/{os.path.basename(f)}")) if os.path.exists(f"feed/stands/{os.path.basename(f)}") else {}
    for s in json.load(open(f))["spots"]:
        if not (LAT0 <= s["lat"] <= LAT1 and LON0 <= s["lon"] <= LON1) or s.get("kind") in ("hotspot", "refuge", "park", "garden"): continue
        p = pp.get(s["id"]); st = sd.get(s["id"]) or {}
        rows.append({"id": s["id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"], "kind": s.get("kind") or "other", "tile": os.path.basename(f)[:-5],
                     "commons": (p[1] if isinstance(p, list) and len(p) > 1 else np.nan), "inat": (p[3] if isinstance(p, list) and len(p) > 3 else np.nan),
                     "stand_u": st.get("u", 0)})
D = pd.DataFrame(rows)
A = D[["lat", "lon"]].values
def dens(r, km):
    d = np.hypot((A[:, 0] - r.lat) * 111, (A[:, 1] - r.lon) * 78); return int((d < km).sum())
D["dens5"] = D.apply(lambda r: dens(r, 5), axis=1); D["dens20"] = D.apply(lambda r: dens(r, 20), axis=1)
D = D[D.commons.notna()].reset_index(drop=True)
log(f"spots with popularity data: {len(D)} in {D.tile.nunique()} tiles; kinds: {D.kind.value_counts().head(10).to_dict()}")
# water features nearby (other starter spots of water kinds within 2 km)
W = D[D.kind.isin(["lake", "waterfall", "beach"])][["lat", "lon"]].values
def near_water(r):
    if not len(W): return 0
    d = np.hypot((W[:, 0] - r.lat) * 111, (W[:, 1] - r.lon) * 78); return int(((d < 2.0) & (d > 0.05)).sum())
D["water2"] = D.apply(near_water, axis=1)
t0 = time.time(); F = []
for i, r in D.iterrows():
    F.append(feats(r));
    if i % 500 == 0: log(f"  terrain {i}/{len(D)} ({len(TILE)} tiles, {round(time.time()-t0)} s)")
D = pd.concat([D, pd.DataFrame(F)], axis=1)
D["target"] = np.log1p(D.commons) + 0.5 * np.log1p(D.stand_u)
for k in KINDS: D["k_" + k] = (D.kind == k).astype(int)
FEAT = ["dens5", "dens20", "z", "openness", "open_dirs", "open_dirs3", "max_hz", "prominence", "relief5", "big_rise20", "steep", "water2"] + ["k_" + k for k in KINDS]

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from scipy.stats import spearmanr
oof = np.zeros(len(D)); kind_only = np.zeros(len(D)); base2 = np.zeros(len(D))
BF = ["dens5", "dens20"] + ["k_" + k for k in KINDS]
for trn, tst in GroupKFold(n_splits=5).split(D, groups=D.tile):
    m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0).fit(D.iloc[trn][FEAT], D.iloc[trn].target)
    oof[tst] = m.predict(D.iloc[tst][FEAT])
    base2[tst] = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0).fit(D.iloc[trn][BF], D.iloc[trn].target).predict(D.iloc[tst][BF])
    kind_only[tst] = D.iloc[tst].kind.map(D.iloc[trn].groupby("kind").target.mean()).fillna(D.iloc[trn].target.mean()).values
D["pred"] = oof
log("\nVALIDATION (spatial CV, whole 1-degree tiles held out)")
log(f"  Spearman terrain+kind model: {spearmanr(oof, D.target).correlation:.3f}")
log(f"  Spearman kind-only baseline: {spearmanr(kind_only, D.target).correlation:.3f}")
log(f"  Spearman kind + accessibility (no terrain): {spearmanr(base2, D.target).correlation:.3f}   <- terrain must beat this to mean anything")
D["resid_access"] = D.target - base2   # popularity not explained by type + accessibility
log(f"  terrain-only signal: Spearman(terrain-model gain, access-residual) = {spearmanr(oof - base2, D.resid_access).correlation:.3f}")
for k in ["viewpoint", "peak", "waterfall", "lake"]:
    g = D[D.kind == k]
    if len(g) > 30: log(f"  within {k:<10} (n={len(g)}): Spearman {spearmanr(g.pred, g.target).correlation:.3f}  (terrain only matters here)")
m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0).fit(D[FEAT], D.target)
from sklearn.inspection import permutation_importance
pi = permutation_importance(m, D[FEAT], D.target, n_repeats=3, random_state=0)
log("\nFEATURE IMPORTANCE (permutation)"); [log(f"  {f:<12} {v:.3f}") for f, v in sorted(zip(FEAT, pi.importances_mean), key=lambda x: -x[1])[:12]]
# gems: high predicted scenic popularity, low actual
CF = D[FEAT].copy(); CF["dens5"] = D.dens5.median(); CF["dens20"] = D.dens20.median()
D["pred_cf"] = m.predict(CF); D["potential_pct"] = D.pred_cf.rank(pct=True); D["resid"] = D.pred_cf - D.target
gems = D[(D.potential_pct >= 0.8) & (D.commons <= 3) & (D.stand_u == 0)].sort_values("resid", ascending=False)
H = (45.582, -122.353); D["km_home"] = np.hypot((D.lat - H[0]) * 111, (D.lon - H[1]) * 78); gems = gems.join(D.km_home)
log(f"\nGEMS: {len(gems)} of {len(D)} spots (top-20% potential, <=3 Commons photos, no photographer cluster)")
log("Nearest 25 to Washougal:")
for _, r in gems.sort_values("km_home").head(25).iterrows():
    log(f"  {r['name'][:38]:<38} {r.kind:<10} {r.km_home:5.0f} km  potential pct {r.potential_pct:.2f}  commons {int(r.commons)}  open {r.open_dirs:.2f} relief {r.relief5:.0f} m  rise20 {r.big_rise20:.0f} m  https://www.google.com/maps/@{r.lat},{r.lon},15z")
log("\nFor contrast, most famous (highest actual) near Washougal:")
for _, r in D[D.km_home < 80].sort_values("target", ascending=False).head(8).iterrows(): log(f"  {r['name'][:38]:<38} {r.kind:<10} commons {int(r.commons)}  potential pct {r.potential_pct:.2f}")
json.dump(gems.head(300)[["id", "name", "lat", "lon", "kind", "potential_pct", "commons", "km_home"]].to_dict("records"), open("ux/gems.json", "w"))
open("ux/gems.txt", "w").write("\n".join(OUT))
