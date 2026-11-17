"""Forecast vs reality, every day, nationwide: did the sky at sunrise and sunset look like the forecast said?

For every US airport (ASOS, Iowa Environmental Mesonet archive) and each sunrise/sunset in the last day:
  observed  = low cloud (< 6,500 ft) and mid cloud (6,500-12,000 ft) from the report nearest the event (within 30 min)
  forecast  = the same hour's cloud cover as forecast the DAY BEFORE (Open-Meteo previous-runs, best_match and HRRR)
Pairs are kept for 60 days (data/skill/<date>.csv). From them:
  * skill: mean absolute error and bias of low cloud, raw vs calibrated (calibration fitted on even days, scored on odd)
  * calibration: forecast low cloud in 10%-bins -> what was actually observed on average, by region (west/east of -100)
    and model -> feed/calib.json, which the app applies to forecast low cloud (app/nowcast.js).
Automated stations see only up to 12,000 ft, so only LOW cloud is calibrated; mid is reported for information.
MEASURED (observations) against MODELED (forecasts).
"""
import csv, io, math, time, datetime as dt, glob, os
import requests
from .common import DATA, log, write_json, iso, utcnow
from .sunlite import sun_times

STATES = ("AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
COVER = {"FEW": 19, "SCT": 44, "BKN": 75, "OVC": 100, "VV": 100, "CLR": 0, "SKC": 0, "NSC": 0}
SKD = DATA / "skill"
MODELS = ("best_match", "gfs_hrrr")


def _obs(sts, ets):
    rows = []
    for st in STATES:
        url = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
        p = {"network": f"{st}_ASOS", "data": "skyc1,skyc2,skyc3,skyc4,skyl1,skyl2,skyl3,skyl4", "tz": "Etc/UTC", "format": "onlycomma",
             "latlon": "yes", "missing": "M", "trace": "T", "report_type": "3", "sts": sts.strftime("%Y-%m-%dT%H:%MZ"), "ets": ets.strftime("%Y-%m-%dT%H:%MZ")}
        for i in range(3):
            try:
                r = requests.get(url, params=p, timeout=120, headers={"User-Agent": "ShotSpots/1.0 (github.com/estaugaa/shotspots)"})
                if r.ok: rows += list(csv.DictReader(io.StringIO(r.text))); break
            except Exception as e:
                log.warning("skill obs %s: %s", st, e)
            time.sleep(5 * (i + 1))
        time.sleep(1)
    return rows


def _layers(r):
    low = mid = None; any_ = False
    for k in "1234":
        c, h = r.get("skyc" + k, "M"), r.get("skyl" + k, "M")
        if c in ("M", "", None): continue
        cov = COVER.get(c.strip())
        if cov is None: continue
        any_ = True
        if cov == 0: low = low or 0; mid = mid or 0; continue
        try: base = float(h)
        except Exception: continue
        if base < 6500: low = max(low or 0, cov)
        elif base < 12000: mid = max(mid or 0, cov)
    if not any_: return None
    return (low or 0, mid or 0)


def _forecast(pts, day0, day1):
    """{(sid, hour_iso): {model: (low, mid)}} day-ahead forecasts for the stations."""
    out = {}
    ids = list(pts)
    for i in range(0, len(ids), 80):
        chunk = ids[i:i + 80]
        p = {"latitude": ",".join(str(pts[s][0]) for s in chunk), "longitude": ",".join(str(pts[s][1]) for s in chunk),
             "hourly": "cloud_cover_low_previous_day1,cloud_cover_mid_previous_day1", "models": ",".join(MODELS),
             "start_date": day0.isoformat(), "end_date": day1.isoformat(), "timezone": "UTC"}
        j = None
        for k in range(3):
            try:
                r = requests.get("https://previous-runs-api.open-meteo.com/v1/forecast", params=p, timeout=120)
                if r.ok: j = r.json(); break
                log.warning("skill forecast %s: %s", r.status_code, r.text[:200])
                if r.status_code == 400 and "," in p["models"]: p["models"] = "best_match"   # HRRR may be unavailable here
            except Exception as e:
                log.warning("skill forecast: %s", e)
            time.sleep(10 * (k + 1))
        if not j: continue
        if isinstance(j, dict): j = [j]
        for sid, loc in zip(chunk, j):
            h = loc.get("hourly") or {}
            for m in MODELS:
                suf = "" if len(p["models"].split(",")) == 1 else f"_{m}"
                lo, mi = h.get(f"cloud_cover_low_previous_day1{suf}"), h.get(f"cloud_cover_mid_previous_day1{suf}")
                if not lo: continue
                for t, a, b in zip(h.get("time", []), lo, mi or [None] * len(lo)):
                    if a is not None: out.setdefault((sid, t[:13]), {})[m] = (a, b)
        time.sleep(1.5)
    return out


def collect():
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    sts, ets = now - dt.timedelta(hours=27), now - dt.timedelta(hours=1)
    raw = _obs(sts, ets)
    by = {}
    for r in raw:
        try:
            t = dt.datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
            lat, lon = float(r["lat"]), float(r["lon"])
        except Exception:
            continue
        lay = _layers(r)
        if lay is None: continue
        by.setdefault(r["station"], {"pos": (round(lat, 3), round(lon, 3)), "obs": []})["obs"].append((t, lay))
    events = []   # (sid, kind, event time, observed)
    for sid, d in by.items():
        lat, lon = d["pos"]
        for day in {sts.date(), ets.date()}:
            st = sun_times(lat, lon, day)
            if not st: continue
            for kind, ev in zip(("sunrise", "sunset"), st):
                if not ev or not (sts <= ev <= ets): continue
                best = min(d["obs"], key=lambda o: abs((o[0] - ev).total_seconds()))
                if abs((best[0] - ev).total_seconds()) <= 1800: events.append((sid, kind, ev, best[1]))
    pts = {sid: by[sid]["pos"] for sid, _, _, _ in events}
    fc = _forecast(pts, sts.date(), ets.date())
    SKD.mkdir(parents=True, exist_ok=True)
    rows = []
    for sid, kind, ev, (ol, om) in events:
        hr = ev.replace(minute=0) + (dt.timedelta(hours=1) if ev.minute >= 30 else dt.timedelta(0))
        f = fc.get((sid, hr.strftime("%Y-%m-%dT%H")))
        if not f: continue
        lat, lon = pts[sid]
        for m, (fl, fm) in f.items():
            rows.append([ev.date().isoformat(), sid, lat, lon, kind, m, fl, fm if fm is not None else "", ol, om])
    path = SKD / f"{now.date().isoformat()}.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["date", "sid", "lat", "lon", "kind", "model", "f_low", "f_mid", "o_low", "o_mid"]); w.writerows(rows)
    for p in sorted(SKD.glob("*.csv"))[:-60]: p.unlink()
    return len(by), len(events), len(rows)


def _bins(pairs):
    b = [[0, 0] for _ in range(11)]
    for f, o in pairs:
        k = min(10, int(f // 10)); b[k][0] += o; b[k][1] += 1
    return [[k * 10 + (5 if k < 10 else 0), round(s / n, 1) if n else None, n] for k, (s, n) in enumerate(b)]


def _apply(bins, f):
    pts = [(c, v) for c, v, n in bins if v is not None and n >= 30]
    if len(pts) < 3: return f
    if f <= pts[0][0]: return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if f <= x1: return y0 + (y1 - y0) * (f - x0) / (x1 - x0)
    return pts[-1][1]


def fit():
    rows = []
    for p in sorted(SKD.glob("*.csv")):
        with open(p) as fh: rows += list(csv.DictReader(fh))
    out = {"gen": iso(utcnow()), "days": len(list(SKD.glob("*.csv"))), "note": "forecast low cloud (day ahead) -> observed at airports at sunrise/sunset", "cal": {}, "skill": {}}
    for m in MODELS:
        for reg in ("west", "east"):
            rs = [r for r in rows if r["model"] == m and ((float(r["lon"]) < -100) == (reg == "west"))]
            if len(rs) < 200: continue
            pairs = [(float(r["f_low"]), float(r["o_low"])) for r in rs]
            even = [(f, o) for (f, o), r in zip(pairs, rs) if int(r["date"][-2:]) % 2 == 0]
            odd = [(f, o) for (f, o), r in zip(pairs, rs) if int(r["date"][-2:]) % 2 == 1]
            tr, te = (even, odd) if len(even) >= len(odd) else (odd, even)
            cal = _bins(tr)
            mae = lambda ps, g: round(sum(abs(g(f) - o) for f, o in ps) / max(1, len(ps)), 1)
            out["skill"][f"{m}/{reg}"] = {"n": len(pairs), "bias": round(sum(f - o for f, o in pairs) / len(pairs), 1),
                                         "mae_raw": mae(te, lambda f: f), "mae_cal": mae(te, lambda f: _apply(cal, f)), "n_test": len(te)}
            out["cal"][f"{m}/{reg}"] = _bins(pairs)
    write_json("calib.json", out)
    return out


def run():
    n_st, n_ev, n_rows = collect()
    out = fit()
    s = "; ".join(f"{k}: n={v['n']} bias {v['bias']:+} MAE {v['mae_raw']} -> {v['mae_cal']} calibrated" for k, v in out["skill"].items())
    return f"{n_st} stations, {n_ev} sunrise/sunset reports, {n_rows} forecast pairs today; {out['days']} days kept. {s or 'not enough data yet'}"
