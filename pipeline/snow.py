"""Snow and road access (MEASURED + researched rules).

* SNOTEL snow depth: for every spot above 450 m, the nearest NRCS SNOTEL stations within 45 km whose elevation is
  within 350 m of the spot. Depth is reported from the station closest in elevation (inches, last 3 days).
* Seasonal access rules: config/access_rules.json (gates, permits, one-off closures), researched from agency pages.
Writes feed/snow.json and feed/access_rules.json.
"""
import datetime as dt, json, math
from .common import spots, write_json, http, log, utcnow, iso, ROOT, FEED

B = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"


def _km(a, b):
    return math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(math.radians(a[0]))) * 111.0


def run():
    rules = json.load(open(ROOT / "config" / "access_rules.json"))
    write_json("access_rules.json", rules)
    L = json.load(open(FEED / "light.json")) if (FEED / "light.json").exists() else {}
    H = json.load(open(ROOT / "data" / "horizons.json")) if (ROOT / "data" / "horizons.json").exists() else {}
    elev = lambda sid: (L.get("elev") or {}).get(sid) or (H.get(sid) or {}).get("elev")
    hi = [(s, elev(s["id"])) for s in spots()]
    hi = [(s, e) for s, e in hi if e and e > 450]
    st = http(f"{B}/stations", params={"stateCds": "OR,WA,ID", "networkCds": "SNTL", "elements": "SNWD"}, timeout=120).json()
    st = [x for x in st if x.get("networkCode") == "SNTL" and x.get("endDate", "2100") > "2026" and x.get("latitude")]
    pick, need = {}, set()
    for s, e in hi:
        c = []
        for x in st:
            d = _km((s["lat"], s["lon"]), (x["latitude"], x["longitude"]))
            de = x["elevation"] * 0.3048 - e
            if d <= 45 and abs(de) <= 350:
                c.append((abs(de) + d * 8, x, d, de))
        if c:
            c.sort(key=lambda z: z[0])
            pick[s["id"]] = c[0]
            need.add(c[0][1]["stationTriplet"])
    vals = {}
    end = dt.date.today()
    trips = sorted(need)
    for i in range(0, len(trips), 25):
        j = http(f"{B}/data", params={"stationTriplets": ",".join(trips[i:i + 25]), "elements": "SNWD", "duration": "DAILY",
                                      "beginDate": str(end - dt.timedelta(days=4)), "endDate": str(end)}, timeout=120).json()
        for row in j:
            for el in row.get("data", []):
                v = [x for x in el.get("values", []) if x.get("value") is not None]
                if v:
                    vals[row["stationTriplet"]] = (v[-1]["value"], v[-1]["date"])
    out = {}
    for sid, (_, x, d, de) in pick.items():
        if x["stationTriplet"] in vals:
            depth, date = vals[x["stationTriplet"]]
            out[sid] = {"in": depth, "date": date, "station": x["name"], "st_elev_m": round(x["elevation"] * 0.3048), "km": round(d), "delev_m": round(de)}
    write_json("snow.json", {"gen": iso(utcnow()), "spots": out, "note": "SNOTEL snow depth (inches) at the nearest station of similar elevation (within 45 km, ±350 m)."})
    return f"{len(out)} high spots with SNOTEL depth from {len(vals)} stations; {len(rules['rules'])} access rules"


def closed_now(rules, sid, day=None):
    """The rule closing car access to this spot on this date, or None."""
    day = day or dt.date.today()
    md = day.strftime("%m-%d")
    for r in rules.get("rules", []):
        if sid not in r["spots"]:
            continue
        if r.get("until") and str(day) >= r["until"]:
            continue
        a, b = r.get("from"), r.get("to")
        if not a:
            continue
        inside = (a <= md <= b) if a <= b else (md >= a or md <= b)
        if r["type"] == "closed" and inside:
            return r
        if r["type"] == "open_only" and not inside:
            return r
    return None
