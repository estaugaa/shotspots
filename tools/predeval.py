"""Did the app's rankings match what happened? Joins the prediction log (data/archive/predictions, written nightly by
`tools/scoretest.py --live`) with ground truth archived for the same windows:

  webcam   data/archive/camtruth  sky_warm (share of the sky in warm colour) from road cameras within 30 km, same
           sunrise/sunset (OR, CA). MEASURED.
  airport  data/archive/skill     observed low cloud (< 6,500 ft) at airports within 40 km, same date and sunrise/sunset
           (nationwide). MEASURED.
  airport  data/archive/obs       ceiling and fog within 40 km, within an hour of the peak (WA, OR). MEASURED.

Reports Spearman rank correlation between the predicted score (and the first layer, light and weather alone) and each
truth, pooled over every spot with truth nearby, plus "night level": does a case's best score track how good that
window turned out (mean truth over the case)? Expected signs: webcam colour +, low cloud -, fog -.
Webcam points (data/archive/predcams): the app's sky colour score at each camera vs that camera's colour, overall, per
camera relative to its own median, by sunrise/sunset and by lead time.
One prediction per window (the last made before it started: the nightly check can run more than once a day); webcam
frames with the current colour measure only (camtruth column mv).
Small samples are reported as such: n < 30 means no conclusion. Output: stdout and ux/predeval.txt (diag.yml).

    python tools/predeval.py [days]     (default: all logged predictions)
"""
import datetime as dt, math, pathlib, statistics, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import archive   # noqa: E402

R_CAM, R_AIR = 30, 40


def km(a, b, c, d):
    x = math.radians(d - b) * math.cos(math.radians((a + c) / 2)); y = math.radians(c - a)
    return 6371 * math.hypot(x, y)


def spearman(a, b):
    if len(a) < 3: return None
    def rk(x):
        o = sorted(range(len(x)), key=lambda i: x[i]); r = [0.0] * len(x); i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and x[o[j + 1]] == x[o[i]]: j += 1
            for k in range(i, j + 1): r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = rk(a), rk(b); ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)); va = sum((x - ma) ** 2 for x in ra); vb = sum((y - mb) ** 2 for y in rb)
    return round(cov / math.sqrt(va * vb), 3) if va and vb else None


def ts(s):
    return dt.datetime.fromisoformat(s[:19]).replace(tzinfo=dt.timezone.utc)   # every logged time is UTC


def latest(preds, key, start):
    """One prediction per window: the last one made before the window started (the nightly check can run more than once a
    day). Each keeps its lead time in hours (lead_h)."""
    best = {}
    for p in preds:
        s = start(p)
        if not s or p["at"] >= s: continue
        k = key(p)
        if k not in best or p["at"] > best[k]["at"]: best[k] = p
    for p in best.values(): p["lead_h"] = round((ts(start(p)) - ts(p["at"])).total_seconds() / 3600, 1)
    return list(best.values())


def cam_frames(since):
    """Webcam frames that show sky, current colour measure only (camtruth marks it in column mv; older measures counted
    LED signs and tail lights)."""
    num = archive.num
    rows = [r for r in archive.read("camtruth", since[:10], "date") if (num(r.get("sky_blue")) or 0) + (num(r.get("sky_grey")) or 0) >= 25]
    mv = max((r.get("mv") or "" for r in rows), default="")
    return [r for r in rows if (r.get("mv") or "") == mv]


def truth_sources(since):
    cam = cam_frames(since)
    sk = archive.read("skill", since[:10], "date")
    ob = archive.read("obs", since[:13], "t")
    return cam, sk, ob


def truth_for(spot, rec, src):
    """Mean of each truth measure near the spot for this window, or None when nothing is near."""
    cam, sk, ob = src; num = archive.num
    peak = ts(rec["window"]["peak"]); day, kind = str(peak.date()), rec["kind"]
    out = {}
    v = [num(r["sky_warm"]) for r in cam if r["event"] == kind and km(spot["lat"], spot["lon"], num(r["lat"]), num(r["lon"])) <= R_CAM
         and (abs((ts(r["t"]) - peak).total_seconds()) <= 5400 if r.get("t") else r["date"] == day)]
    v = [x for x in v if x is not None]
    if v: out["webcam colour"] = statistics.fmean(v)
    v = [num(r["o_low"]) for r in sk if r["date"] == day and r["kind"] == kind and r["model"] == "best_match"
         and km(spot["lat"], spot["lon"], num(r["lat"]), num(r["lon"])) <= R_AIR]
    v = [x for x in v if x is not None]
    if v: out["airport low cloud"] = statistics.fmean(v)
    lo, hi = (peak - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:00"), (peak + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:00")
    v = [r for r in ob if lo <= r["t"] <= hi and km(spot["lat"], spot["lon"], num(r["lat"]), num(r["lon"])) <= R_AIR]
    if v: out["airport fog"] = statistics.fmean(1.0 if archive.flag(r["fog"]) else 0.0 for r in v)
    return out


def main(days=None):
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat() if days else ""
    raw = [p for p in archive.read_jsonl("predictions", since) if not p.get("err") and p.get("top") and p.get("at", "") >= since]
    preds = latest(raw, lambda p: (p["case"], p["kind"], p["window"]["peak"][:13]), lambda p: p["window"]["start"])
    leads = sorted(p["lead_h"] for p in preds)
    lines = [f"Prediction log: {len(preds)} windows ranked ({len(raw)} logged; the last one before each window is used), "
             f"{len({p['at'][:10] for p in preds})} nights, {len({p['case'] for p in preds})} places (since {since[:10] or 'the start'})."
             + (f" Lead time {leads[0]}-{leads[-1]} h, median {statistics.median(leads)} h." if leads else "")]
    now = dt.datetime.now(dt.timezone.utc)
    cams_eval(lines, since, now)
    done = [p for p in preds if ts(p["window"]["end"]) < now - dt.timedelta(hours=2)]
    lines.append(f"{len(done)} windows are over (truth can exist); {len(preds) - len(done)} still ahead.")
    if not done:
        out = "\n".join(lines); print(out); _save(out); return 0
    src = truth_sources(min(p["window"]["start"] for p in done))
    pairs, nights = {}, {}
    for p in done:
        per = {}
        for s in p["top"]:
            for k, v in truth_for(s, p, src).items():
                pairs.setdefault(k, []).append((s["score"], (s.get("layers") or [None])[0], v)); per.setdefault(k, []).append(v)
        for k, vs in per.items():
            nights.setdefault(k, []).append((p["top"][0]["score"], statistics.fmean(vs), f"{p['case']} {p['kind']} {p['window']['peak'][:10]}"))
    sign = {"webcam colour": "+", "airport low cloud": "-", "airport fog": "-"}
    lines.append("")
    lines.append("Spot level (every ranked spot with truth nearby): Spearman of predicted score / light-and-weather layer vs truth")
    for k in sign:
        ps = pairs.get(k, [])
        if not ps: lines.append(f"  {k:18s} no matches yet"); continue
        l1 = [(a, t) for _, a, t in ps if a is not None]
        lines.append(f"  {k:18s} n={len(ps):4d}  score rho={spearman([a for a, _, _ in ps], [t for _, _, t in ps])}"
                     f"  layer1 rho={spearman([a for a, _ in l1], [t for _, t in l1])}  (good if {sign[k]}){'  n<30: no conclusion' if len(ps) < 30 else ''}")
    lines.append("")
    lines.append("Night level (each window: best score vs mean truth over its spots): does the app know a good night from a bad one?")
    for k in sign:
        ns = nights.get(k, [])
        if not ns: lines.append(f"  {k:18s} no matches yet"); continue
        lines.append(f"  {k:18s} n={len(ns):4d}  rho={spearman([a for a, _, _ in ns], [b for _, b, _ in ns])}  (good if {sign[k]})"
                     f"{'  n<30: no conclusion' if len(ns) < 30 else ''}")
        for a, b, w in sorted(ns, key=lambda x: x[2])[-8:]:
            lines.append(f"      {w:40s} best score {a:5.1f}  {k} {b:.2f}")
    out = "\n".join(lines); print(out); _save(out)
    return 0


def cams_eval(lines, since, now):
    """The app's sky model at each webcam (data/archive/predcams, forecast at the camera) vs that camera's measured colour
    at the same sunrise/sunset. Also relative to each camera's own median (tinted lenses, cameras that never see the
    horizon cancel out), as camtruth.fit does."""
    num = archive.num
    flat = [{**r, "at": rec["at"]} for rec in archive.read_jsonl("predcams", since) for r in rec.get("rows") or []]
    preds = latest(flat, lambda r: (r["cam"], r["kind"], r["peak"][:13]), lambda r: r["start"])
    preds = [r for r in preds if ts(r["peak"]) < now - dt.timedelta(hours=2)]
    lines.append("")
    lines.append(f"Webcam points: {len(preds)} camera windows predicted and over (sky model, forecast at the camera).")
    if not preds: return
    frames = {}
    for r in cam_frames(min(r["start"] for r in preds)):
        if r.get("t"): frames.setdefault((r["cam"], r["event"]), []).append((ts(r["t"]), num(r["sky_warm"])))
    pairs = []
    for p in preds:
        pk = ts(p["peak"])
        got = [v for t, v in frames.get((p["cam"], p["kind"]), []) if abs((t - pk).total_seconds()) <= 5400 and v is not None]
        if got and p["sk"].get("q") is not None: pairs.append((p["cam"], p["kind"], p["sk"]["q"], statistics.fmean(got), p["lead_h"]))
    med = {}
    for c, _, _, v, _ in pairs: med.setdefault(c, []).append(v)
    rel = [(q, v - statistics.median(med[c])) for c, _, q, v, _ in pairs if len(med[c]) >= 3]
    tag = lambda n: "  n<30: no conclusion" if n < 30 else ""
    lines.append(f"  sky colour score vs measured colour  n={len(pairs):4d}  rho={spearman([x[2] for x in pairs], [x[3] for x in pairs])}  (good if +){tag(len(pairs))}")
    lines.append(f"  same, each camera vs its own median  n={len(rel):4d}  rho={spearman([a for a, _ in rel], [b for _, b in rel])}{tag(len(rel))}")
    for kind in ("sunrise", "sunset"):
        ps = [x for x in pairs if x[1] == kind]
        lines.append(f"  {kind:8s}                             n={len(ps):4d}  rho={spearman([x[2] for x in ps], [x[3] for x in ps])}{tag(len(ps))}")
    for lo, hi in ((0, 12), (12, 48)):
        ps = [x for x in pairs if lo <= x[4] < hi]
        lines.append(f"  made {lo:2d}-{hi:2d} h ahead                   n={len(ps):4d}  rho={spearman([x[2] for x in ps], [x[3] for x in ps])}{tag(len(ps))}")


def _save(text):
    d = ROOT / "ux"; d.mkdir(exist_ok=True); (d / "predeval.txt").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else None))
