"""Weekend plan: the best 3-5 shots for Saturday and Sunday, built Thursday-Sunday and pushed once on Friday afternoon.

Inputs are the alert rules (fog above, colour, alignments, dark sky, aurora) run without the probability bar, over a
4-day horizon. HRRR covers ~48 h; beyond it the rules fall back to Open-Meteo (single deterministic model, so its
odds are crude and capped at 55%). Plus seasonal wildlife peaks (GBIF/eBird weekly shares) and satellite fall-colour
stage (Sentinel-2).
"""
import datetime as dt, math
from zoneinfo import ZoneInfo
from . import alerts as A
from .common import write_json, read_json, http, log, utcnow, iso, FEED, DATA

LA = ZoneInfo("America/Los_Angeles")
OM_CAP = 55
LENS = {"fog_above": "70-300 to stack the ridges above the fog; 16-50 for the wide view",
        "color": "16-50 wide, foreground first; bracket for the bright horizon",
        "dark": "16-50 at 16 mm f/2.8 (or the 27 at f/2.8), 15–20 s, ISO 3200",
        "aurora": "16-50 at 16 mm f/2.8, 10–20 s, ISO 1600–3200, aim north",
        "wildlife": "70-300 (use the 1.5x crop as reach; keep your distance)",
        "fallcolor": "27 or 16-50; overcast light is your friend for saturated leaves"}


def _md(d):
    import datetime as _dt
    try:
        x = _dt.date.fromisoformat(d[:10]); return x.strftime("%b ") + str(x.day)
    except Exception:
        return d


def weekend_days(today=None):
    t = today or dt.datetime.now(LA).date()
    sat = t + dt.timedelta(days=(5 - t.weekday()) % 7)
    if t.weekday() == 6:      # Sunday: this weekend is today only
        sat = t - dt.timedelta(days=1)
    return sat, sat + dt.timedelta(days=1)


def openmeteo(S, days):
    """Hourly cloud by layer + visibility from Open-Meteo for the given spots; rows shaped like HRRR rows."""
    out, ids = {}, list(S)
    for i in range(0, len(ids), 50):
        chunk = [S[k] for k in ids[i:i + 50]]
        try:
            j = http("https://api.open-meteo.com/v1/forecast", params={
                "latitude": ",".join(f"{s['lat']:.4f}" for s in chunk), "longitude": ",".join(f"{s['lon']:.4f}" for s in chunk),
                "hourly": "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility", "timezone": "UTC",
                "forecast_days": days, "timeformat": "unixtime"}, timeout=60, tries=2).json()
        except Exception as e:
            log.warning("Open-Meteo failed: %s", e)
            continue
        for s, loc in zip(chunk, j if isinstance(j, list) else [j]):
            h = loc.get("hourly", {})
            rows = {}
            for k, t in enumerate(h.get("time", [])):
                tc, lo, mi, hi, vis = (h[x][k] for x in ("cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high", "visibility"))
                if tc is None:
                    continue
                canvas = max(mi or 0, (hi or 0) * 0.9)
                fog = (vis is not None and vis < 1000) or (lo or 0) >= 85
                rows[int(t // 60)] = {"p_fog": 50 if fog else 8, "p_low": 50 if (lo or 0) >= 80 else 10, "p_clear": 50 if tc < 20 else 25 if tc < 45 else 5,
                                      "p_color": OM_CAP if (20 <= canvas <= 80 and (lo or 0) < 40) else 12, "tcc": tc, "lcc": lo, "smoke_aod": None, "smoke_ugm3": None, "om": True}
            out[s["id"]] = rows
    return out


def wildlife_picks(S, sat):
    W = read_json(FEED / "wildlife.json", {}).get("spots", {})
    wk = min(51, (sat - dt.date(sat.year, 1, 1)).days // 7)
    best = []
    for sid, w in W.items():
        if sid not in S:
            continue
        for sp in w.get("species", []):
            rel = sp.get("rel")
            if not rel or sp.get("n", 0) < 40 or len(sp.get("sp", "")) < 6:   # skip short/garbled vernacular names
                continue
            seasonal = rel[wk] - sum(rel) / len(rel)
            if rel[wk] >= 0.75 and seasonal >= 0.3:
                best.append((seasonal * math.log(sp["n"]), sid, sp["sp"], rel[wk]))
    best.sort(reverse=True)
    out, seen = [], set()
    for sc, sid, sp, r in best:
        if sp in seen or sid in {o["spots"][0] for o in out}:
            continue
        seen.add(sp)
        out.append({"rule": "wildlife", "spots": [sid], "p": None, "title": f"{sp} at {S[sid]['name']}",
                    "body": f"{sp} sightings here are near their yearly high this week. Go early: dawn and the two hours after are best.",
                    "why": ["GBIF weekly share of records (presence-only, not encounter odds)"]})
        if len(out) >= 2:
            break
    return out


def colour_picks(S):
    se = read_json(FEED / "sentinel.json", {}).get("spots", {})
    c = [(sid, v) for sid, v in se.items() if v.get("stage") == "near peak" and sid in S and "fallcolor" in S[sid]["cats"]]
    c.sort(key=lambda x: A.km_home(S[x[0]]))
    return [{"rule": "fallcolor", "spots": [sid], "p": None, "title": f"Fall colour near peak at {S[sid]['name']}",
             "body": f"Satellite images show the trees here near peak colour (as of {_md(v['date'])}). Soft overcast or the first sun brings it out best.", "why": ["Sentinel-2 colour index vs. summer baseline"]}
            for sid, v in c[:1]]


def run(push_now=False):
    sat, sun = weekend_days()
    today = dt.datetime.now(LA).date()
    if today.weekday() in (0, 1, 2):        # Mon-Wed: too far out to be useful
        return "not weekend-plan days"
    st = A.settings()
    F = A.Feed()
    S = {s["id"]: s for s in A.spots()}
    from .snow import closed_now
    rules = read_json(FEED / "access_rules.json", {})
    fb = read_json(DATA / "research" / "feedback.json", {})
    S = {k: v for k, v in S.items() if not closed_now(rules, k, sat) and (fb.get(k) or {}).get("vote") != "down"}
    near = {k: v for k, v in S.items() if A.km_home(v) <= st["max_km"]}
    far = {k: v for k, v in S.items() if A.km_home(v) <= st["max_km_dark"]}
    days = (sun - today).days + 1
    A.HZ["days"] = max(3, days + 1)
    om_spots = {k: v for k, v in near.items() if set(v["cats"]) & A.SKY} | {k: v for k, v in far.items() if {"night", "aurora"} & set(v["cats"])} | {k: S[k] for k in A.VALLEY if k in S}
    F.om = openmeteo(om_spots, min(16, days + 1))
    now = int(utcnow().timestamp() // 60)
    cands = []
    for name, fn in A.RULES.items():
        if name == "smoke":
            continue
        try:
            cands += fn(F, far if name in ("dark", "aurora") else near, now, st) if name == "aurora" else fn(F, far if name == "dark" else near, now)
        except Exception as e:
            log.warning("weekend rule %s: %s", name, e)
    lo = int(dt.datetime.combine(sat, dt.time(0), LA).timestamp() // 60)
    hi = int(dt.datetime.combine(sun, dt.time(23, 59), LA).timestamp() // 60)
    cands = [c for c in cands if lo <= c["t"] <= hi]
    for c in cands:   # was this candidate built on Open-Meteo instead of HRRR?
        row = F.hrrr(c["spots"][0], c["t"]) if c.get("spots") else None
        if row and row.get("om"):
            c["p"] = min(c["p"], OM_CAP)
            c["why"] = c.get("why", []) + ["beyond the 48-hour HRRR range: Open-Meteo single-model forecast, rough odds"]
    cands.sort(key=lambda c: -c["p"])
    picks, used = [], set()
    for c in cands:
        dayk = (c["t"] - lo) // 1440
        key = (c["rule"], dayk)
        lm = c.get("lm")
        if key in used or c["p"] < 30 or (lm and ("lm", lm) in used):
            continue
        used.add(key)
        if lm:
            used.add(("lm", lm))
        picks.append(c)
        if len(picks) >= 4:
            break
    extras = wildlife_picks(near, sat) + colour_picks(near)
    picks = sorted(picks, key=lambda c: c["t"]) + extras[: max(1, 5 - len(picks))]
    for p in picks:
        p["lens"] = LENS.get(p["rule"]) or (f"~{p['body'].split('Use ~')[1].split(' mm')[0]} mm: the 70-300" if "Use ~" in p["body"] else "")
        if p.get("t"):
            p["at"] = iso(dt.datetime.fromtimestamp(p["t"] * 60, dt.timezone.utc))
            p["day"] = dt.datetime.fromtimestamp(p["t"] * 60, LA).strftime("%a")
    out = {"gen": iso(utcnow()), "sat": str(sat), "sun": str(sun), "picks": picks,
           "note": "Odds within 48 h are HRRR; beyond that Open-Meteo, capped at 55% because a single model can't give real odds."}
    write_json("weekend.json", out)
    pushed = ""
    if (today.weekday() == 4 and dt.datetime.now(LA).hour >= 12) or push_now:
        pushed = push(out, st)
    return f"{len(picks)} weekend picks for {sat:%b %d}-{sun:%d}; {pushed}"


def push(plan, st):
    if "weekend" not in st.get("push_rules", []) or not plan["picks"]:
        return "push off or nothing to send"
    sent = read_json(A.ADIR / "sent.json", {"keys": {}, "subs": []})
    key = f"weekend:{plan['sat']}"
    if key in sent["keys"]:
        return "already sent"
    top = [p for p in plan["picks"] if p.get("p")][:3] or plan["picks"][:3]
    body = "; ".join(f"{p['title'].split(' (')[0]}" + (f" ({p['p']}%)" if p.get("p") else "") for p in top)
    fake = [{"rule": "weekend", "key": key, "t": int(utcnow().timestamp() // 60) + 600, "p": 100,
             "title": "Your weekend plan", "body": body[:230], "spots": []}]
    st2 = dict(st, push_rules=["weekend"], quiet_start=0, quiet_end=0)
    return A.push(fake, st2, int(utcnow().timestamp() // 60))
