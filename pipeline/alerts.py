"""Alerts: scan the next ~3 days for shots worth getting up for, publish feed/alerts.json, and push the new ones.

Rules (each one can be switched off in the app):
  fog_above   valley fog/low cloud at sunrise while a high viewpoint sits above the inversion (HRRR + Salem sounding + 3DEP elevation)
  color       good odds of sunrise/sunset colour (HRRR mid/high cloud canvas with an open low horizon), smoke-aware
  alignment   sun or moon behind a landmark (planner) with decent odds of clear sky (HRRR <48 h, ASOS climatology beyond)
  dark        a clear, moonless stretch of night for the night-sky spots
  smoke       heavy smoke forecast (info: tells you to skip distant-peak shots)

Probabilities are the raw HRRR neighbourhood/time-lagged odds (MODELED), not yet calibrated against your outings.
Push delivery: Web Push (VAPID). Subscriptions are read from the Netlify form "push_sub" on every run and are never
written to the (public) repo; only a hash of dead endpoints is kept.
"""
import datetime as dt, hashlib, json
from zoneinfo import ZoneInfo
from .common import spots, write_json, read_json, FEED, DATA, http, secret, log, utcnow, iso

LA = ZoneInfo("America/Los_Angeles")
ADIR = DATA / "alerts"
DEFAULTS = {"enabled": True, "min_prob": 60, "rules": ["fog_above", "color", "alignment", "dark", "aurora", "smoke"],
            "push_rules": ["fog_above", "color", "alignment", "dark", "aurora", "weekend"], "quiet_start": 22, "quiet_end": 6, "max_per_day": 3, "max_km": 150, "max_km_dark": 300,
            "aurora_kp": 6, "aurora_overrides_quiet": True}
SKY = {"vista", "mountain", "reflection", "coast", "city", "alignment", "geology", "historic"}
FOG_ABOVE = ["cape-horn-lookout", "womens-forum", "vista-house", "jonsrud", "scout-cape-horn-uplands", "angels-rest", "larch-mtn",
             "scout-capehorn-foothill-sunset", "silver-star", "council-crest", "pittock", "scout-angels-hood", "scout-mt-norway-sunset"]
VALLEY = ["steigerwald", "washougal-waterfront"]
HZ = {"days": 3}                                  # how many days ahead the rules look (the weekend plan widens it)
AOD_HAZE, AOD_SMOKY, AOD_HEAVY = 0.15, 0.4, 1.0   # smoke aerosol optical depth: light haze / smoky / heavy
PM_HEAVY = 35.0                                   # near-surface smoke, ug/m3 (EPA "unhealthy for sensitive groups")


def km_home(s):
    return ((s["lat"] - 45.582) ** 2 + ((s["lon"] + 122.353) * 0.7) ** 2) ** 0.5 * 111


# ---------------- inputs ----------------
class Feed:
    def __init__(self):
        self.h = read_json(FEED / "hrrr.json")
        self.L = read_json(FEED / "light.json")
        self.P = (read_json(FEED / "planner.json") or {}).get("events", {})
        self.C = read_json(FEED / "climo.json")
        self.snd = read_json(FEED / "sounding.json")
        self.dk = read_json(FEED / "darksky.json")
        self.cal = read_json(FEED / "calibration.json")

    om = None   # optional Open-Meteo rows {sid: {tmin: row}} beyond the HRRR horizon (weekend plan)

    def hrrr(self, sid, tmin, tol=100):
        h = self.h
        if h and sid in h["spots"]:
            i = min(range(len(h["t"])), key=lambda j: abs(h["t"][j] - tmin))
            if abs(h["t"][i] - tmin) <= tol:
                return dict(zip(h["cols"], h["spots"][sid][i]))
        if self.om and sid in self.om:
            rows = self.om[sid]
            k = min(rows, key=lambda t: abs(t - tmin)) if rows else None
            if k is not None and abs(k - tmin) <= 40:
                return rows[k]
        return None

    def ray(self, sid, tmin, kind):
        """% of the path toward the rising/setting sun (25-300 km) free of a low deck; None if unknown."""
        h = self.h
        if not h or sid not in h.get("rays", {}):
            return None
        i = min(range(len(h["t"])), key=lambda j: abs(h["t"][j] - tmin))
        rr = h["rays"][sid]
        if abs(h["t"][i] - tmin) > 100 or i >= len(rr):
            return None
        return rr[i][0 if kind == "sunrise" else 1]

    def hrrr_span(self, sid, a, b):
        h = self.h
        if not h or sid not in h["spots"]:
            return []
        return [dict(zip(h["cols"], h["spots"][sid][i]), t=t) for i, t in enumerate(h["t"]) if a <= t <= b]

    def day(self, sid, ymd):
        L = self.L
        if not L or sid not in L["spots"] or ymd not in L["days"]:
            return None
        return L["spots"][sid][L["days"].index(ymd)]

    def elev(self, sid):
        return (self.L or {}).get("elev", {}).get(sid)

    def climo_clear(self, s, tmin):
        if not self.C:
            return None
        best, bd = None, 1e9
        for v in self.C["stations"].values():
            d = (v["lat"] - s["lat"]) ** 2 + ((v["lon"] - s["lon"]) * 0.7) ** 2
            if d < bd:
                best, bd = v, d
        if bd > 0.6:  # ~80 km
            return None
        t = dt.datetime.fromtimestamp(tmin * 60, LA)
        return best["clear12k"][t.month - 1][t.hour]

    def inversion_top(self):
        o = (self.snd or {}).get("obs") or []
        o = [x for x in o if x.get("inv_c", 0) >= 2 and x.get("top_m")]
        if not o:
            return None
        age = (utcnow() - dt.datetime.fromisoformat(o[0]["t"].replace("Z", "+00:00"))).total_seconds() / 3600
        return o[0]["top_m"] if age < 30 else None


def fmt(tmin, day=True):
    t = dt.datetime.fromtimestamp(tmin * 60, LA)
    now = dt.datetime.now(LA)
    d = "today" if t.date() == now.date() else "tomorrow" if t.date() == now.date() + dt.timedelta(days=1) else t.strftime("%a %b %-d")
    hm = t.strftime("%-I:%M%p").lower().replace(":00", "")
    return f"{d} {hm}" if day else hm


def ymd(tmin):
    return dt.datetime.fromtimestamp(tmin * 60, LA).strftime("%Y-%m-%d")


def smoke_note(row):
    """(penalty multiplier, text) for a HRRR row."""
    if not row:
        return 1.0, None
    aod, pm = row.get("smoke_aod"), row.get("smoke_ugm3")
    if (aod or 0) >= AOD_HEAVY or (pm or 0) >= PM_HEAVY:
        return 0.3, f"heavy smoke (AOD {aod:.1f}): muted colour, distant peaks hidden"
    if (aod or 0) >= AOD_SMOKY:
        return 0.75, f"smoky (AOD {aod:.2f}): red sun, far peaks faint"
    if (aod or 0) >= AOD_HAZE:
        return 1.1, f"light smoke haze (AOD {aod:.2f}) can deepen reds"
    return 1.0, None


# ---------------- rules ----------------
def rule_fog_above(F, S, now):
    out, top = [], F.inversion_top()
    ref = next((S[v] for v in VALLEY if v in S), None)
    if not ref:
        return out
    for k in range(HZ["days"]):
        dy = (dt.datetime.now(LA) + dt.timedelta(days=k)).strftime("%Y-%m-%d")
        d = F.day(ref["id"], dy)
        if not d or not d.get("or") or d["or"] < now + 30:
            continue
        low = [F.hrrr(v, d["or"]) for v in VALLEY if v in S]
        low = [x for x in low if x]
        if not low:
            continue
        p = max(max(x["p_fog"] or 0, x["p_low"] or 0) for x in low)
        picks = []
        for sid in FOG_ABOVE:
            el = F.elev(sid)
            if sid in S and el is not None and el > (top + 50 if top else 450):
                picks.append((el, sid))
        if not picks:
            continue
        picks.sort(reverse=True)
        names = [S[s]["name"] for _, s in picks[:3]]
        why = [f"{p}% chance of fog or low cloud in the valley at sunrise (HRRR)"]
        why.append(f"inversion top ~{round(top)} m (Salem sounding)" if top else "no fresh sounding: assumes viewpoints above 450 m clear the fog")
        out.append({"rule": "fog_above", "key": f"fog_above:{dy}", "t": d["or"], "p": p, "spots": [s for _, s in picks[:3]],
                    "title": f"Sea of fog {fmt(d['or'])}",
                    "body": f"{p}% chance the valley fills with fog at sunrise. Get above it: {', '.join(names)}.", "why": why})
    return out


def rule_color(F, S, now):
    out = []
    sky = [s for s in S.values() if set(s["cats"]) & SKY and F.h and s["id"] in F.h["spots"]]
    for k in range(HZ["days"]):
        dy = (dt.datetime.now(LA) + dt.timedelta(days=k)).strftime("%Y-%m-%d")
        for kind, fld in (("sunrise", "or"), ("sunset", "os")):
            cands = []
            for s in sky:
                d = F.day(s["id"], dy)
                if not d or not d.get(fld) or d[fld] < now + 30:
                    continue
                row = F.hrrr(s["id"], d[fld])
                if not row or row.get("p_color") is None:
                    continue
                mult, note = smoke_note(row)
                lit = any(a <= d[fld] + 20 and b >= d[fld] - 40 for a, b in d.get("lit", [])) if kind == "sunset" else any(a <= d[fld] + 40 for a, b in d.get("lit", []))
                op = F.ray(s["id"], d[fld], kind)
                rmult = 1.0 if op is None or op >= 70 else 0.75 if op >= 40 else 0.4
                score = row["p_color"] * mult * rmult * (1.0 if lit else 0.85)
                cands.append((score, s, d[fld], row, note, op))
            if not cands:
                continue
            cands.sort(key=lambda x: -x[0])
            best = cands[0]
            p = round(min(100, best[0]))
            top3 = [c[1]["name"] for c in cands[:3]]
            why = [f"{best[3]['p_color']}% chance of a colourful {kind} sky (HRRR: mid/high cloud 20–80%, low cloud under 40%)",
                   "also checks for a low cloud deck between you and the sun"]
            if best[4]:
                why.append(best[4])
            if best[5] is not None:
                why.append(f"path toward the {'rising' if kind == 'sunrise' else 'setting'} sun {best[5]}% open (25–300 km)")
            out.append({"rule": "color", "key": f"color:{dy}:{kind}", "t": best[2], "p": p, "spots": [c[1]["id"] for c in cands[:3]],
                        "title": f"Colourful {kind} likely {fmt(best[2])}",
                        "body": f"{p}% odds of colour. Best bets: {', '.join(top3)}." + (f" Horizon toward the sun is {best[5]}% open." if best[5] is not None else "") + (f" {best[4][0].upper() + best[4][1:]}." if best[4] else ""), "why": why})
    return out


def rule_alignment(F, S, now):
    out, horizon = [], now + HZ["days"] * 1440
    best = {}
    for sid, evs in F.P.items():
        s = S.get(sid)
        if not s:
            continue
        for e in evs:
            if e["obj"] not in ("sun", "moon") or not (now + 60 <= e["t"] <= horizon):
                continue
            row = F.hrrr(sid, e["t"])
            pc = row["p_clear"] if row and row.get("p_clear") is not None else F.climo_clear(s, e["t"])
            src = "HRRR" if row and row.get("p_clear") is not None else "10-year climatology"
            if pc is None:
                continue
            if row:
                mult, _ = smoke_note(row)
                pc = pc * min(1.0, mult)
            k = (e["obj"], e["lm"], ymd(e["t"]))
            if k not in best or pc > best[k][0]:
                best[k] = (pc, s, e, src)
    for (obj, lm, dy), (pc, s, e, src) in best.items():
        p = round(pc)
        what = "Sun" if obj == "sun" else "Moon"
        out.append({"rule": "alignment", "key": f"alignment:{obj}:{lm}:{dy}", "t": e["t"], "p": p, "spots": [s["id"]], "lm": lm,
                    "title": f"{what} behind {lm} {fmt(e['t'])}",
                    "body": f"From {s['name']}: the {what.lower()} lines up with {lm} at {fmt(e['t'], False)} for ~{e['dur']} min. Use ~{e['fl']} mm. {p}% chance of clear sky.",
                    "why": [f"{p}% clear-sky odds ({src})", f"{lm} is {e['dkm']:.0f} km away at azimuth {e['laz']:.0f}°"]})
    return out


def rule_dark(F, S, now):
    out = []
    night = [s for s in S.values() if "night" in s["cats"]]
    if not night or not F.h:
        return out
    ref = night[0]["id"]
    for k in range(HZ["days"] - 1):
        dy = (dt.datetime.now(LA) + dt.timedelta(days=k)).strftime("%Y-%m-%d")
        nxt = (dt.datetime.now(LA) + dt.timedelta(days=k + 1)).strftime("%Y-%m-%d")
        d, d2 = F.day(ref, dy), F.day(ref, nxt)
        if not d or not d2 or not d.get("os") or not d2.get("or"):
            continue
        a, b = d["os"] + 100, d2["or"] - 100            # astronomical darkness (approx. 100 min from sunrise/sunset here)
        # moon up time inside the dark window
        moon_up = []
        for dd in (d, d2):
            if dd.get("mr") and dd.get("ms"):
                moon_up.append((dd["mr"], dd["ms"]) if dd["ms"] > dd["mr"] else (dd["mr"], dd["mr"] + 720))
        bright = (d.get("mi") or 0) >= 30
        best = None
        for s in night:
            rows = F.hrrr_span(s["id"], max(a, now), b)
            good = [r_["t"] for r_ in rows if (r_.get("p_clear") or 0) >= 60 and (r_.get("smoke_aod") or 0) < AOD_SMOKY
                    and not (bright and any(x <= r_["t"] <= y for x, y in moon_up))]
            if len(good) < 3:
                continue
            pc = round(sum(r_["p_clear"] for r_ in rows if r_["t"] in good) / len(good))
            sqm = ((F.dk or {}).get("spots", {}).get(s["id"]) or {}).get("sqm")
            km = km_home(s)
            sc = len(good) * pc + (sqm or 0) * 10 - km * 1.5   # a darker site has to earn the drive
            if not best or sc > best[0]:
                best = (sc, s, good, pc, sqm, km)
        if not best:
            continue
        _, s, good, pc, sqm, km = best
        out.append({"rule": "dark", "key": f"dark:{dy}", "t": good[0], "p": pc, "spots": [s["id"]],
                    "title": f"Clear dark sky {fmt(good[0])}",
                    "body": f"{pc}% clear for about {len(good)} h from {fmt(good[0], False)}" + (" with the moon down" if bright else f", moon {d.get('mi') or 0:.0f}% lit") + f". Try {s['name']}" + (f" (~{round(km / 10) * 10} km away)." if km > 60 else "."),
                    "why": [f"{len(good)} forecast hours with ≥60% clear sky in darkness (HRRR)"] + ([f"sky brightness {sqm} mag/arcsec² (VIIRS)"] if sqm else [])})
    return out


def rule_smoke(F, S, now):
    out = []
    home = next((S[v] for v in VALLEY if v in S), None)
    if not home:
        return out
    rows = F.hrrr_span(home["id"], now, now + 24 * 60)
    bad = [r_ for r_ in rows if (r_.get("smoke_aod") or 0) >= AOD_HEAVY or (r_.get("smoke_ugm3") or 0) >= PM_HEAVY]
    if bad:
        w = max(bad, key=lambda r_: r_.get("smoke_aod") or 0)
        out.append({"rule": "smoke", "key": f"smoke:{ymd(w['t'])}", "t": w["t"], "p": 100, "spots": [],
                    "title": f"Heavy smoke {fmt(w['t'])}", "body": f"Smoke peaks near AOD {w.get('smoke_aod') or 0:.1f} ({w.get('smoke_ugm3') or 0:.0f} µg/m³ at the surface). Skip distant-peak shots; red-sun and close-up work still can be good.",
                    "why": ["HRRR-Smoke forecast"]})
    return out


def _rows(j):
    """SWPC JSON comes either as a header row + lists, or as a list of dicts."""
    if not j:
        return []
    if isinstance(j[0], list):
        hdr = j[0]
        return [dict(zip(hdr, r)) for r in j[1:]]
    return j


def swpc():
    out = {"forecast": [], "now": None}
    try:
        for r in _rows(http("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json", tries=2, timeout=30).json()):
            t = dt.datetime.fromisoformat(str(r["time_tag"]).replace("Z", "").replace(" ", "T")).replace(tzinfo=dt.timezone.utc)
            out["forecast"].append((int(t.timestamp() // 60), float(r["kp"]), str(r.get("observed", ""))))
    except Exception as e:
        log.warning("SWPC Kp forecast failed: %s", e)
    try:
        rows = _rows(http("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json", tries=2, timeout=30).json())
        if rows:
            r = rows[-1]
            out["now"] = float(r.get("estimated_kp") if r.get("estimated_kp") is not None else r.get("kp_index"))
    except Exception as e:
        log.warning("SWPC 1-minute Kp failed: %s", e)
    return out


def north_horizon(sid):
    H = _HZ.get("h")
    if H is None:
        H = _HZ["h"] = read_json(DATA / "horizons.json", {})
    v = H.get(sid)
    if not v:
        return None
    n = len(v["alt"])
    return max(v["alt"][int(round(az / 360 * n)) % n] for az in range(320, 401, 2))


_HZ = {}


def rule_aurora(F, S, now, st=None):
    """Kp >= threshold while it's dark and clear. Kp is a 3-hour planetary index; from ~45.6 N (about 51 N geomagnetic)
    aurora shows on camera on the northern horizon around Kp 5-6 and to the eye around Kp 7+."""
    kp_min = (st or DEFAULTS)["aurora_kp"]
    sw = F.sw = getattr(F, "sw", None) or swpc()
    night = [s for s in S.values() if {"night", "aurora"} & set(s["cats"])]
    if not night:
        return []
    ref = night[0]["id"]
    def dark(t):
        for k in (-1, 0, 1, 2, 3):
            dy = (dt.datetime.now(LA) + dt.timedelta(days=k)).strftime("%Y-%m-%d")
            nx = (dt.datetime.now(LA) + dt.timedelta(days=k + 1)).strftime("%Y-%m-%d")
            d, d2 = F.day(ref, dy), F.day(ref, nx)
            if d and d2 and d.get("os") and d2.get("or") and d["os"] + 90 <= t <= d2["or"] - 90:
                return True
        return False
    def best_spot(t):
        cands = []
        for s in night:
            row = F.hrrr(s["id"], t)
            pc = row["p_clear"] if row and row.get("p_clear") is not None else F.climo_clear(s, t)
            if pc is None:
                continue
            nh = north_horizon(s["id"])
            sqm = ((F.dk or {}).get("spots", {}).get(s["id"]) or {}).get("sqm") or 0
            cands.append((pc - (nh or 5) * 3 + sqm * 2 - km_home(s) * 0.15, pc, s, nh))
        return max(cands, key=lambda c: c[0]) if cands else None
    out = []
    if sw["now"] is not None and sw["now"] >= kp_min and dark(now + 10):
        b = best_spot(now + 30)
        if b and b[1] >= 40:
            out.append({"rule": "aurora", "key": f"aurora:now:{ymd(now)}", "t": now + 5, "p": round(b[1]), "spots": [b[2]["id"]], "urgent": True,
                        "title": f"Aurora possible now (Kp {sw['now']:.0f})",
                        "body": f"Geomagnetic storm in progress and it's dark. Look north from {b[2]['name']}; {round(b[1])}% chance of clear sky. Go wide on a tripod: 10–20 s exposures (phones: Night mode at max).",
                        "why": [f"estimated Kp {sw['now']:.1f} (NOAA SWPC, 1-minute)", f"northern horizon ~{b[3]:.0f}° here" if b[3] is not None else "northern horizon unknown"]})
    blocks = [(t, kp) for t, kp, obs in sw["forecast"] if obs in ("predicted", "estimated") and kp >= kp_min and t + 180 > now and dark(t + 90)]
    seen = set()
    for t, kp in blocks:
        tt = max(t + 90, now + 30)
        dy = ymd(tt - 360)
        if dy in seen:
            continue
        b = best_spot(tt)
        if not b:
            continue
        seen.add(dy)
        p = round(b[1])
        out.append({"rule": "aurora", "key": f"aurora:{dy}", "t": tt, "p": p, "spots": [b[2]["id"]],
                    "title": f"Aurora watch {fmt(tt)} (Kp {kp:.0f} forecast)",
                    "body": f"NOAA forecasts Kp {kp:.0f}, enough for aurora low in the north on camera{' and maybe to the eye' if kp >= 7 else ''}. {p}% chance of clear sky at {b[2]['name']}.",
                    "why": [f"NOAA SWPC 3-day Kp forecast: {kp:.1f} for the 3 hours from {fmt(t)}", "Kp forecasts are uncertain more than a day out"]})
    return out


RULES = {"aurora": rule_aurora, "fog_above": rule_fog_above, "color": rule_color, "alignment": rule_alignment, "dark": rule_dark, "smoke": rule_smoke}


# ---------------- settings + subscriptions (Netlify forms) ----------------
def _submissions(form):
    from .forms import submissions
    return submissions(form)


def settings():
    st = dict(DEFAULTS)
    st.update(read_json(ADIR / "settings.json", {}))
    try:
        subs = _submissions("alert_settings")
    except Exception as e:
        log.warning("alert settings sync failed: %s", e)
        subs = []
    if subs:
        d = subs[-1].get("data", {})
        for k in ("min_prob", "quiet_start", "quiet_end", "max_per_day", "max_km", "max_km_dark", "aurora_kp"):
            try:
                st[k] = int(float(d[k]))
            except Exception:
                pass
        if "enabled" in d:
            st["enabled"] = str(d["enabled"]).lower() in ("1", "true", "on", "yes")
        for k in ("rules", "push_rules"):
            if k in d:
                st[k] = [x for x in str(d[k]).split(",") if x in RULES or x == "weekend"]
        ADIR.mkdir(parents=True, exist_ok=True)
        json.dump(st, open(ADIR / "settings.json", "w"), indent=1)
    return st


def h8(s):
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def subscriptions():
    """Live subscriptions: latest action per endpoint, minus endpoints the push service reported gone."""
    dead = set(read_json(ADIR / "dead.json", []))
    live = {}
    for s in _submissions("push_sub"):
        d = s.get("data", {})
        try:
            sub = json.loads(d.get("sub") or "{}")
        except Exception:
            continue
        ep = sub.get("endpoint")
        if not ep:
            continue
        if d.get("action") == "unsubscribe":
            live.pop(ep, None)
        elif h8(ep) not in dead:
            live[ep] = {"sub": sub, "at": s.get("created_at"), "device": d.get("device") or ""}
    return live


# ---------------- main ----------------
def run():
    now = int(utcnow().timestamp() // 60)
    F = Feed()
    if not F.h:
        return "no HRRR feed yet"
    S = {s["id"]: s for s in spots()}
    st = settings()
    alerts = []
    # drop spots you can't drive to right now (seasonal gates, multi-year closures)
    from .snow import closed_now
    rules = read_json(FEED / "access_rules.json", {}) or read_json(DATA.parent / "config" / "access_rules.json", {})
    fb = read_json(DATA / "research" / "feedback.json", {})
    S = {k: v for k, v in S.items() if not closed_now(rules, k) and (fb.get(k) or {}).get("vote") != "down"}
    near = {k: v for k, v in S.items() if km_home(v) <= st["max_km"]}
    far = {k: v for k, v in S.items() if km_home(v) <= st["max_km_dark"]}
    for name in st["rules"]:
        try:
            if name == "aurora":
                alerts += rule_aurora(F, far, now, st)
            else:
                alerts += RULES[name](F, far if name == "dark" else near, now)
        except Exception as e:
            log.warning("alert rule %s failed: %s", name, e)
    alerts = [a for a in alerts if a["t"] >= now - 30]
    shown = sorted([a for a in alerts if a["p"] >= st["min_prob"] or a["rule"] == "smoke"], key=lambda a: a["t"])
    for a in shown:
        a["at"] = iso(dt.datetime.fromtimestamp(a["t"] * 60, dt.timezone.utc))
    write_json("alerts.json", {"gen": iso(utcnow()), "settings": st, "alerts": shown,
                               "near_misses": sorted([a for a in alerts if a not in shown], key=lambda a: -a["p"])[:5],
                               "note": "Odds are raw HRRR/climatology probabilities (MODELED); log outings to calibrate them."})
    try:
        widget(F, S, shown, now)
    except Exception as e:
        log.warning("widget feed failed: %s", e)
    pushed = push(shown, st, now) if st["enabled"] else "alerts off"
    return f"{len(shown)} alerts ({len(alerts)} candidates); {pushed}"


def widget(F, S, shown, now):
    """feed/widget.json: a ~2 KB summary for the Home Screen widget (Scriptable) - next light at home, top alerts,
    weekend picks, and the HRRR odds at home for the next sunrise and sunset."""
    home = next((v for v in VALLEY if v in S), None)
    light = []
    for k in range(2):
        d = F.day(home, (dt.datetime.now(LA) + dt.timedelta(days=k)).strftime("%Y-%m-%d")) if home else None
        for kind, fld in (("sunrise", "or"), ("sunset", "os")):
            if d and d.get(fld) and d[fld] > now:
                row = F.hrrr(home, d[fld]) or {}
                light.append({"kind": kind, "at": iso(dt.datetime.fromtimestamp(d[fld] * 60, dt.timezone.utc)), "golden_start": iso(dt.datetime.fromtimestamp((d[fld] - (0 if kind == "sunrise" else 50)) * 60, dt.timezone.utc)),
                              "p_color": row.get("p_color"), "p_clear": row.get("p_clear"), "p_fog": row.get("p_fog")})
    wk = read_json(FEED / "weekend.json", {}) or {}
    tidy = lambda a: {"title": a["title"], "body": a["body"][:140], "p": a.get("p"), "rule": a["rule"], "at": a.get("at"), "spot": (a.get("spots") or [None])[0]}
    write_json("widget.json", {"gen": iso(utcnow()), "light": sorted(light, key=lambda x: x["at"])[:2], "alerts": [tidy(a) for a in shown if a["rule"] != "smoke"][:3],
                               "smoke": next((a["title"] for a in shown if a["rule"] == "smoke"), None),
                               "weekend": [tidy(p) for p in (wk.get("picks") or [])][:3] if wk.get("sun", "") >= dt.datetime.now(LA).strftime("%Y-%m-%d") else []})


def push(shown, st, now):
    key = secret("VAPID_PRIVATE_KEY")
    if not key:
        return "no VAPID key; push skipped"
    from . import webpush
    vk = webpush.load_key(key)
    sent = read_json(ADIR / "sent.json", {"keys": {}, "subs": []})
    subs = subscriptions()
    if not subs:
        return "no devices subscribed"
    dead = set(read_json(ADIR / "dead.json", []))
    hour = dt.datetime.now(LA).hour
    qs, qe = st["quiet_start"], st["quiet_end"]
    quiet = False if qs == qe else (hour >= qs or hour < qe) if qs > qe else (qs <= hour < qe)
    today = dt.datetime.now(LA).strftime("%Y-%m-%d")
    n_today = sum(1 for v in sent["keys"].values() if v.startswith(today))
    msgs = []
    # welcome message for new devices (also the end-to-end test)
    for ep, v in subs.items():
        if h8(ep) not in sent["subs"]:
            msgs.append((ep, {"title": "ShotSpots alerts are on", "body": "You'll get a heads-up here when fog, colour, an alignment or a dark sky lines up.", "tag": "welcome", "url": "./#alerts"}))
            sent["subs"].append(h8(ep))
    fresh = [a for a in shown if a["rule"] in st["push_rules"] and a["key"] not in sent["keys"]]
    aur = [a for a in fresh if a["rule"] == "aurora" and (not quiet or st.get("aurora_overrides_quiet", True))][:1]
    todo = aur + ([] if quiet else sorted([a for a in fresh if a["rule"] != "aurora" and a["t"] > now + 45],
                                          key=lambda a: -a["p"])[:max(0, min(2, st["max_per_day"] - n_today))])
    for a in todo:
        for ep in subs:
            msgs.append((ep, {"title": a["title"], "body": a["body"], "tag": a["key"], "url": f"./#alert={a['key']}", "urgent": bool(a.get("urgent"))}))
        sent["keys"][a["key"]] = dt.datetime.now(LA).strftime("%Y-%m-%dT%H:%M")
    ok = fail = 0
    for ep, data in msgs:
        try:
            code = webpush.send(subs[ep]["sub"], data, vk, ttl=1800 if data.get("urgent") else 6 * 3600, urgency="high" if data.get("urgent") else "normal")
        except Exception as e:
            log.warning("push failed: %s", e)
            fail += 1
            continue
        if code in (404, 410):
            dead.add(h8(ep))
        elif code >= 300:
            log.warning("push HTTP %s", code)
            fail += 1
        else:
            ok += 1
    # forget sent keys older than 10 days
    cut = (dt.datetime.now(LA) - dt.timedelta(days=10)).strftime("%Y-%m-%d")
    sent["keys"] = {k: v for k, v in sent["keys"].items() if v >= cut}
    ADIR.mkdir(parents=True, exist_ok=True)
    json.dump(sent, open(ADIR / "sent.json", "w"), indent=1)
    json.dump(sorted(dead), open(ADIR / "dead.json", "w"))
    return f"{len(subs)} devices, {len(todo)} new alerts, {ok} pushes sent, {fail} failed" + (" (quiet hours)" if quiet else "")
