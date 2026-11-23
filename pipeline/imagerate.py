"""Automatic image rating for the validation set (MODELED): which truth measure matches how a photo looks?

A free image model stands in for hand ratings: CLIP ViT-B/32 (OpenAI weights via open_clip, MIT) gives
  vivid   probability the image is "a vivid, colourful sunrise or sunset sky" rather than the other prompts below
  aes     LAION aesthetic predictor v1 (linear head on the CLIP embedding, MIT; trained on people's 1-10 ratings)
Rated:
  Commons golden-hour photos (commonsphotos.py v3 + photoweather.py windows) in cells that have ERA5 weather, a few
  thousand a run, never twice (data/imagerate/rated.csv.gz: pid, cell, date, event, vivid, aes, dull, fog, night)
  webcam thumbnails (data/camtruth/thumbs/<date>/<cam>_<event>_<min>_sw<sky_warm>.jpg) against their warm-pixel share
Analysis -> feed/imagerate.json: vivid and aes by cloud level and rain at that hour; Spearman of the sky formula
(camtruth.sky_q) against vivid; for webcams, Spearman of sky_warm against vivid (is the warm-pixel measure any good?).
Images: Wikimedia Commons thumbnails (330 px, a standard size), fetched gently with the project's User-Agent; only
scores are kept. Needs torch + open_clip (installed only for this job, requirements-ml.txt).

    python -m pipeline imagerate
"""
import csv, gzip, io, json, random, re, time
from collections import defaultdict
from .common import http, soft_fail, log, utcnow, iso, DATA, FEED
from . import commonsphotos, photoweather
from .camtruth import sky_q, _spearman
_rs = lambda a, b: (lambda x: round(x, 3) if x is not None else None)(_spearman(a, b))   # None when one side doesn't vary

DIR = DATA / "imagerate"
RATED = DIR / "rated.csv.gz"
OUT = FEED / "imagerate.json"
API = "https://commons.wikimedia.org/w/api.php"
H = {"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots; image rating for photo-timing statistics)"}
HEAD = "https://github.com/LAION-AI/aesthetic-predictor/raw/main/sa_0_4_vit_b_32_linear.pth"
PROMPTS = {"vivid": ["a photo of a vivid colourful sunset sky", "a photo of a sunrise with glowing pink and orange clouds"],
           "plain": ["a photo of a clear sky at dusk with no clouds"],
           "dull": ["a photo under a dull grey overcast sky"],
           "fog": ["a photo of a landscape in fog"],
           "night": ["a photo taken at night"],
           "other": ["a photo of a building", "a photo of people", "an indoor photo"]}
PER_RUN = 3000
BUDGET_MIN = 150
COLS = ["pid", "cell", "date", "event", "vivid", "aes", "dull", "fog", "night", "plain", "other", "words"]
SKY_MIN = 0.5   # a sky photo: at least half the model's answer is a sky/weather prompt (vivid, plain, dull, fog)


class Rater:
    def __init__(self):
        import torch, open_clip
        self.torch = torch
        self.model, _, self.prep = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        self.model.eval(); tok = open_clip.get_tokenizer("ViT-B-32")
        self.keys = [k for k, v in PROMPTS.items() for _ in v]
        with torch.no_grad():
            t = self.model.encode_text(tok([p for v in PROMPTS.values() for p in v])); self.text = t / t.norm(dim=-1, keepdim=True)
        w = torch.load(io.BytesIO(http(HEAD, timeout=60).content), map_location="cpu")
        self.head = torch.nn.Linear(512, 1); self.head.load_state_dict(w); self.head.eval()

    def rate(self, img_bytes):
        from PIL import Image
        torch = self.torch
        im = self.prep(Image.open(io.BytesIO(img_bytes)).convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            e = self.model.encode_image(im); e = e / e.norm(dim=-1, keepdim=True)
            p = (100 * e @ self.text.T).softmax(dim=-1)[0].tolist(); aes = float(self.head(e.float())[0][0])
        by = defaultdict(float)
        for k, x in zip(self.keys, p):
            by[k] += x
        return {k: round(by[k], 3) for k in ("vivid", "dull", "fog", "night", "plain", "other")} | {"aes": round(aes, 2)}


def _rated():
    try:
        return {r["pid"]: r for r in csv.DictReader(gzip.open(RATED, "rt"))}
    except Exception:
        return {}


def _thumbs(pids):
    """page id -> 330 px thumbnail URL, 50 per API call, gently."""
    out = {}
    for i in range(0, len(pids), 50):
        try:
            j = http(API, params={"action": "query", "format": "json", "pageids": "|".join(pids[i:i + 50]), "prop": "imageinfo",
                                  "iiprop": "url", "iiurlwidth": 330}, headers=H, timeout=60).json()
            for pg in (j.get("query") or {}).get("pages", {}).values():
                ii = (pg.get("imageinfo") or [{}])[0]
                if ii.get("thumburl"):
                    out[str(pg["pageid"])] = ii["thumburl"]
        except Exception as e:
            soft_fail("imagerate: thumbnail urls", e)
            if "429" in str(e):
                break
        time.sleep(3)
    return out


WEB = DIR / "webcams.csv.gz"
WCOLS = ["file", "date", "cam", "event", "min", "sky_warm", "vivid", "aes", "dull", "fog", "night", "plain", "other"]


def webcams(rater, limit=2000):
    """Rate each saved road-camera thumbnail once (file names carry the warm-pixel share, sw<value>), then compare with
    the webcam archive's forecast for the same frame: the sky formula (with its horizon-gap term) against vivid."""
    import re as _re
    try:
        done = {r["file"]: r for r in csv.DictReader(gzip.open(WEB, "rt"))}
    except Exception:
        done = {}
    new = 0
    for f in sorted((DATA / "camtruth" / "thumbs").glob("*/*.jpg")):
        k = f"{f.parent.name}/{f.name}"
        if k in done or new >= limit:
            continue
        m = _re.match(r"(.+)_(sunrise|sunset)_([-+]?\d+)_sw(\d+)\.jpg$", f.name)
        if not m:
            continue
        try:
            done[k] = {"file": k, "date": f.parent.name, "cam": m.group(1), "event": m.group(2), "min": m.group(3), "sky_warm": m.group(4), **rater.rate(f.read_bytes())}; new += 1
        except Exception as e:
            soft_fail("imagerate: webcam thumbnail", e)
    DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(WEB, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=WCOLS, extrasaction="ignore"); w.writeheader(); w.writerows(done.values())
    rows = [r for r in done.values() if r.get("plain") not in (None, "")]
    out = {"n": len(rows), "rated_now": new}
    if len(rows) < 20:
        return out
    f = lambda r, k: float(r[k])
    out["spearman_skywarm_vivid"] = _rs([f(r, "sky_warm") for r in rows], [f(r, "vivid") for r in rows])
    out["spearman_skywarm_aes"] = _rs([f(r, "sky_warm") for r in rows], [f(r, "aes") for r in rows])
    # the same frames in the webcam archive (forecast at capture time, probe point toward the sun)
    from . import archive
    from .camtruth import MV
    since = min(r["date"] for r in rows)
    arc = {}
    for a in archive.read("camtruth", since, "date"):
        if a.get("mv") == str(MV):
            arc[(a["date"], _re.sub(r"[^A-Za-z0-9]", "", a["cam"]), a["event"])] = a
    DEF = {"canvasFloor": 0.32, "lowBroken": 0.85, "lowDeck": 0.4}
    q, v = [], []
    for r in rows:
        a = arc.get((r["date"], r["cam"], r["event"]))
        skyp = sum(f(r, k) for k in ("vivid", "plain", "dull", "fog"))
        if not a or skyp < SKY_MIN:
            continue
        n = {k: archive.num(a.get(k)) for k in ("low", "mid", "high", "pop", "p_low", "p_mid")}
        if None in (n["low"], n["mid"], n["high"]):
            continue
        q.append(sky_q(n["low"], n["mid"], n["high"], n["pop"], n["p_low"], n["p_mid"], DEF)); v.append(f(r, "vivid") / skyp)
    out["sky_frames_with_forecast"] = len(q)
    out["spearman_formula_vivid"] = _rs(q, v) if len(q) >= 30 else None
    return out


def analyse(rated):
    wx = {}
    rows = []
    for r in rated.values():
        if r["cell"] not in wx:
            wx[r["cell"]] = photoweather._read(photoweather.WX / f"{r['cell']}.json.gz", {})
        w = (wx[r["cell"]].get(r["date"]) or {}).get(r["event"])
        if not w or any(x is None for x in w[:4]):
            continue
        low, mid, high, prc, snow, code, prev = w
        skyp = sum(float(r[k]) for k in ("vivid", "plain", "dull", "fog")) if r.get("plain") not in (None, "") else None
        if skyp is None or (skyp < SKY_MIN and "s" not in (r.get("words") or "")):
            continue   # sky photos only (older ratings lack the sky scores: re-rated over time)
        rows.append({"vivid": float(r["vivid"]) / max(skyp, 1e-6), "aes": float(r["aes"]), "low": low, "mid": mid, "high": high,
                     "rain": prc >= 0.2 or code in (61, 63, 65, 80, 81, 82, 95), "ev": r["event"]})
    if len(rows) < 100:
        return {"n": len(rows), "note": "too few rated sky photos with weather yet"}
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    B = [(0, 10), (10, 30), (30, 50), (50, 70), (70, 90), (90, 101)]
    def table(key):
        o = {}
        for a, b in B:
            g = [r for r in rows if a <= r[key] < b]
            if len(g) >= 20:
                o[f"{a}-{min(b, 100)}"] = {"n": len(g), "vivid": mean([r["vivid"] for r in g]), "aes": mean([r["aes"] for r in g])}
        return o
    DEF = {"canvasFloor": 0.32, "lowBroken": 0.85, "lowDeck": 0.4}
    q = [sky_q(r["low"], r["mid"], r["high"], 100 if r["rain"] else 0, None, None, DEF) for r in rows]
    return {"n": len(rows), "measure": "sky photos only; vivid = share of the sky answers that are 'vivid colourful sky'", "by": {k: table(k) for k in ("low", "mid", "high")},
            "rain": {str(v): {"n": len(g), "vivid": mean([r["vivid"] for r in g])} for v in (True, False) for g in [[r for r in rows if r["rain"] == v]]},
            "spearman_formula_vivid": _rs(q, [r["vivid"] for r in rows]),
            "spearman_formula_aes": _rs(q, [r["aes"] for r in rows])}


def run():
    t0 = time.time(); left = lambda: BUDGET_MIN - (time.time() - t0) / 60
    idx = photoweather._read(commonsphotos.OUT / "index.json", {})
    pf = commonsphotos.OUT / idx.get("file", "")
    if idx.get("version", 0) < 3 or not pf.is_file():
        return "photo file with page ids (v3) not ready yet"
    cells = {f.name[:-8] for f in photoweather.WX.glob("*.json.gz")}
    rated = _rated(); random.seed(len(rated))
    cand = [(f"{ck[0]:g}_{ck[1]:g}", d, ev, r["pid"], r["words"]) for ck, d, ev, r in photoweather.photo_events(pf)
            if ev and r.get("pid") and f"{ck[0]:g}_{ck[1]:g}" in cells and (r["pid"] not in rated or not rated[r["pid"]].get("plain"))]
    random.shuffle(cand); cand.sort(key=lambda c: "s" not in c[4])   # files named sunset/sunrise/afterglow first (stable: shuffled within)
    cand = cand[:PER_RUN]
    rater = Rater()
    urls = _thumbs([c[3] for c in cand])
    new = 0
    for cell, d, ev, pid, words in cand:
        if left() < 15:
            break
        u = urls.get(pid)
        if not u:
            continue
        try:
            img = http(u, headers=H, timeout=30).content
            rated[pid] = {"pid": pid, "cell": cell, "date": d, "event": ev, "words": words, **rater.rate(img)}; new += 1
        except Exception as e:
            soft_fail("imagerate: photo", e)
        time.sleep(0.5)
    DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(RATED, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore"); w.writeheader(); w.writerows(rated.values())
    res = {"gen": iso(utcnow()), "kind": "MODELED (CLIP ViT-B/32 + LAION aesthetic v1) on MEASURED photos", "photos": analyse(rated), "webcams": webcams(rater)}
    FEED.mkdir(parents=True, exist_ok=True); json.dump(res, open(OUT, "w"), separators=(",", ":"))
    p = res["photos"]
    return (f"{new} photos rated this run ({len(rated)} in all, {p.get('n', 0)} sky photos with weather); formula vs vivid {p.get('spearman_formula_vivid')}; "
            f"webcam warm-pixel share vs vivid {res['webcams'].get('spearman_skywarm_vivid')}")
