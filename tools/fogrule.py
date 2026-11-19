"""Which fog rule does the app's scoring deserve? Scores candidate fog rules against what airports reported.

verify_obs (method 2) tests the model's visibility alone. The app's rule (app/app.js skyAt) is different: fog in a
morning window when low cloud >= 80 % with visibility under 3 km, OR humidity >= 96 % with wind <= 3 mph. This replays
that rule and variants on the latest forecast before each report and the one made a day ahead, for every archived sunrise
report (data/archive/obs, airport reports within 45 min of sunrise; observed fog = visibility <= 1 mi or FG).
Free data: Open-Meteo previous-runs API (humidity, wind; same-day visibility and low cloud) and verify_obs's daily
snapshot data/fc_archive.json (day-ahead visibility and low cloud, which the archive API doesn't keep). Output: ux/fogrule.txt

    python tools/fogrule.py
"""
import datetime as dt, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline.common import http, read_json, DATA
from pipeline.metar import history

V = ("visibility", "cloud_cover_low", "relative_humidity_2m", "wind_speed_10m")
# rule name -> f(vis m, low %, rh %, wind mph): True = fog forecast
RULES = {
    "app now: (low>=80 & vis<3km) or (rh>=96 & wind<=3)": lambda v, l, r, w: (l >= 80 and v < 3000) or (r >= 96 and w <= 3),
    "  part 1 only: low>=80 & vis<3km": lambda v, l, r, w: l >= 80 and v < 3000,
    "  part 2 only: rh>=96 & wind<=3": lambda v, l, r, w: r >= 96 and w <= 3,
    "vis<=1600 (verify_obs)": lambda v, l, r, w: v <= 1600,
    "vis<1000": lambda v, l, r, w: v < 1000,
    "vis<3km": lambda v, l, r, w: v < 3000,
    "rh>=98 & wind<=3": lambda v, l, r, w: r >= 98 and w <= 3,
    "rh>=96 & wind<=3 & vis<5km": lambda v, l, r, w: r >= 96 and w <= 3 and v < 5000,
    "(low>=80 & vis<3km) or (rh>=98 & wind<=3 & vis<5km)": lambda v, l, r, w: (l >= 80 and v < 3000) or (r >= 98 and w <= 3 and v < 5000),
}


def prev(stations, day):
    """Hourly forecasts made `day` days before (0 = the same day's runs), filling missing fields from GFS then ECMWF."""
    names = [f"{x}_previous_day{day}" if day else x for x in V]; out = {}
    for i in range(0, len(stations), 40):
        ch = stations[i:i + 40]
        base = {"latitude": ",".join(str(s["lat"]) for s in ch), "longitude": ",".join(str(s["lon"]) for s in ch), "past_days": 31,
                "forecast_days": 1, "timezone": "GMT", "wind_speed_unit": "mph", "hourly": ",".join(names)}
        got = {}
        for model in (None, "gfs_seamless", "ecmwf_ifs025"):
            try:
                j = http("https://previous-runs-api.open-meteo.com/v1/forecast", params={**base, **({"models": model} if model else {})}, timeout=120).json()
            except Exception as e:
                print("previous-runs", model, e); continue
            if isinstance(j, dict) and j.get("error"):
                print("refused", model, j.get("reason")); continue
            for s, r in zip(ch, j if isinstance(j, list) else [j]):
                h = r.get("hourly") or {}; g = got.setdefault(s["id"], {})
                for k, t in enumerate(h.get("time", [])):
                    row = g.setdefault(t, [None] * 4)
                    for n, nm in enumerate(names):
                        x = (h.get(nm) or [None] * (k + 1))[k]
                        if row[n] is None and x is not None:
                            row[n] = x
        out.update(got)
    return out


def table(pairs):
    lines = []
    for name, f in RULES.items():
        c = defaultdict(int)
        for obs, x in pairs:
            fc = f(*x); c["hit" if obs and fc else "miss" if obs else "fa" if fc else "cn"] += 1
        h, m, fa, cn = c["hit"], c["miss"], c["fa"], c["cn"]; n = h + m + fa + cn
        hr = h / (h + m) if h + m else 0; far = fa / (h + fa) if h + fa else 0
        # Peirce skill (hit rate minus false-alarm rate) and accuracy vs always saying "no fog"
        pofd = fa / (fa + cn) if fa + cn else 0
        lines.append(f"  {name:<56} forecast {h + fa:>4}  hit {h:>3}  miss {m:>3}  false {fa:>4} | caught {hr:4.0%}  came true {1 - far if h + fa else 0:4.0%}  skill {hr - pofd:+.2f}  acc {(h + cn) / n:.3f}")
    return lines


def main():
    obs = history(60)
    st = {}
    for o in obs:
        st.setdefault(o["id"], {"id": o["id"], "lat": o["lat"], "lon": o["lon"]})
    # sunrise reports only (the rule is applied to morning windows): local solar hour before noon
    am = [o for o in obs if (int(o["t"][11:13]) + o["lon"] / 15) % 24 < 12]
    out = [f"Fog rules vs airport reports at sunrise: {len(am)} reports from {len(st)} stations, {min(o['t'] for o in am)[:10]} to {max(o['t'] for o in am)[:10]}, "
           f"observed fog {sum(o['fog'] for o in am)} ({sum(o['fog'] for o in am) / len(am):.0%})",
           "caught = share of fog mornings forecast; came true = share of fog forecasts that verified; skill = caught minus false-alarm rate (0 = no skill)"]
    snap = read_json(DATA / "fc_archive.json", {}) or {}
    for day, label in ((0, "same-day forecast (latest run before the hour)"), (1, "day-ahead forecast (made ~11 UTC the day before)")):
        fc = prev(list(st.values()), day); pairs = []; skipped = 0
        if day:   # the archive API keeps no day-ahead visibility or low cloud: verify_obs saves its own snapshot of them
            for sid, rows in fc.items():
                for t, row in rows.items():
                    sv = (snap.get(sid) or {}).get(t); row[0], row[1] = (sv[0], sv[1]) if sv else (None, None)
        for o in am:
            x = (fc.get(o["id"]) or {}).get(o["t"])
            if not x or any(v is None for v in x):
                skipped += 1; continue
            pairs.append((o["fog"], tuple(x)))
        out += ["", f"== {label}: {len(pairs)} scored, {skipped} without all four forecast fields, fog {sum(p[0] for p in pairs)}"] + table(pairs)
    txt = "\n".join(out); print(txt)
    os.makedirs("ux", exist_ok=True); open("ux/fogrule.txt", "w", encoding="utf-8").write(txt + "\n")


if __name__ == "__main__":
    main()
