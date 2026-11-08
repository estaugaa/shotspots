"""Birding report, free on GitHub Actions: recent bird sightings near home from iNaturalist (keyless API), flagged
as notable when they're rare here (few records in the past year), a first-of-season arrival, or on your target list
(config/bird_targets.json). Writes feed/birds.json; alerts.py pushes new rare/target birds nearby.

Not covered (needs a person or a key): Tweeters mailing-list posts, eBird rare-bird alerts (needs an eBird API key:
set EBIRD_KEY and they're added automatically), BirdCast migration counts."""
import datetime as dt
from .common import http, write_json, read_json, utcnow, iso, log, secret, DATA

LAT, LON, R_KM = 45.60, -122.30, 90
INAT = "https://api.inaturalist.org/v1"
H = {"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots)"}


def _counts(d1, d2):
    out, page = {}, 1
    while page <= 3:
        j = http(f"{INAT}/observations/species_counts", params={"iconic_taxa": "Aves", "lat": LAT, "lng": LON, "radius": R_KM, "d1": d1, "d2": d2,
                 "per_page": 500, "page": page, "verifiable": "true"}, headers=H, timeout=60).json()
        for r in j.get("results", []):
            out[r["taxon"]["id"]] = r["count"]
        if len(j.get("results", [])) < 500:
            break
        page += 1
    return out


def _ebird(key, targets):
    """eBird notable (rare) sightings within 50 km, if an eBird key is set."""
    j = http("https://api.ebird.org/v2/data/obs/geo/recent/notable", params={"lat": LAT, "lng": LON, "dist": 50, "back": 4, "detail": "simple"},
             headers={**H, "X-eBirdApiToken": key}, timeout=40).json()
    return [{"species": o.get("comName"), "sci": o.get("sciName"), "date": (o.get("obsDt") or "")[:10], "place": o.get("locName"), "lat": o.get("lat"), "lon": o.get("lng"),
             "count": o.get("howMany"), "url": f"https://ebird.org/checklist/{o['subId']}" if o.get("subId") else "", "why": "flagged as rare here by eBird", "src": "eBird",
             "target": (o.get("comName") or "").lower() in targets} for o in j]


def run():
    now = utcnow().date()
    targets = {t.lower() for t in (read_json(DATA.parent / "config" / "bird_targets.json", {"targets": []}).get("targets") or [])}
    recent = http(f"{INAT}/observations", params={"iconic_taxa": "Aves", "lat": LAT, "lng": LON, "radius": R_KM, "d1": str(now - dt.timedelta(days=4)),
                  "per_page": 200, "order_by": "observed_on", "verifiable": "true", "photos": "true"}, headers=H, timeout=60).json().get("results", [])
    year = _counts(str(now - dt.timedelta(days=365)), str(now - dt.timedelta(days=5)))
    season = _counts(str(now - dt.timedelta(days=60)), str(now - dt.timedelta(days=5)))
    notables, seen = [], set()
    for o in recent:
        t = o.get("taxon") or {}
        tid, name = t.get("id"), (t.get("preferred_common_name") or t.get("name") or "").strip()
        if not tid or t.get("rank") not in ("species", "subspecies") or (tid, o.get("observed_on")) in seen:
            continue
        seen.add((tid, o.get("observed_on")))
        ny, ns = year.get(tid, 0), season.get(tid, 0)
        why = "on your target list" if name.lower() in targets else "rare here: %s record%s in the past year" % (ny, "" if ny == 1 else "s") if ny <= 3 \
            else "first of the season: none reported in the last two months" if ns == 0 and ny >= 6 else None
        if not why:
            continue
        loc = (o.get("location") or ",").split(",")
        ph = (o.get("photos") or [{}])[0].get("url", "")
        notables.append({"species": name[:1].upper() + name[1:], "sci": t.get("name"), "date": o.get("observed_on"), "place": (o.get("place_guess") or "")[:80],
                         "lat": round(float(loc[0]), 3) if loc[0] else None, "lon": round(float(loc[1]), 3) if loc[1] else None, "url": o.get("uri"),
                         "photo": ph.replace("square", "small"), "why": why, "src": "iNaturalist", "target": why.startswith("on your"), "geoprivacy": o.get("geoprivacy")})
    key = secret("EBIRD_KEY")
    if key:
        try:
            notables += _ebird(key, targets)
        except Exception as e:
            log.warning("eBird notable: %s", e)
    seen2, uniq = set(), []
    for n in notables:   # one line per species and place (eBird repeats a bird for every checklist)
        k = (n["species"], (n["place"] or "").split(",")[0].strip().lower())
        if k not in seen2:
            seen2.add(k); uniq.append(n)
    notables = uniq
    notables = sorted(notables, key=lambda n: (0 if n["target"] else 1, -(int((n["date"] or "0000-00-00").replace("-", "")))))[:25]
    write_json("birds.json", {"gen": iso(utcnow()), "radius_km": R_KM, "notables": notables, "sources": ["iNaturalist"] + (["eBird"] if key else []),
                              "note": "Notable = rare here (≤3 iNaturalist records within 90 km in the past year), first of season, or on your target list."})
    return f"{len(recent)} recent bird observations, {len(notables)} notable"
