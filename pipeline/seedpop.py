"""How much people actually go to and record each starter spot, from independent references:
  Wikimedia Commons  geotagged photos within 200 m
  Flickr             geotagged photos within 250 m (FLICKR_KEY)
  iNaturalist        nature observations within 300 m (wildlife spots: refuges, hotspots, lakes, beaches, waterfalls)
plus what the seed already knows (Wikipedia/Wikidata links, eBird species, peak prominence) in the seed's own score.
pop = 1.5*log2(1+commons) + 1.2*log2(1+flickr) + 0.8*log2(1+inat)   (about 0-30; 10 = a well-known local spot)

Written to feed/seedpop/<tile>.json ({id: [pop, commons, flickr, inat]}), separate from the seed tiles so it never
clashes with a rebuild. The app merges it when it loads a tile. Incremental: tiles done within 120 days are skipped,
and each tile checks its best 45 spots (most-notable first), so the run can stop any time and continue next time.
"""
import json, math, time
from .common import FEED, http, log, read_json, write_json, secret, utcnow, iso

PER_TILE = 45
WILD = {"refuge", "hotspot", "lake", "beach", "waterfall"}


def _commons(lat, lon):
    j = http("https://commons.wikimedia.org/w/api.php", params={"action": "query", "list": "geosearch", "gscoord": f"{lat}|{lon}", "gsradius": 200,
             "gsnamespace": 6, "gslimit": 100, "format": "json"}, timeout=30, tries=2).json()
    return len(j.get("query", {}).get("geosearch", []))


def _flickr(key, lat, lon):
    j = http("https://api.flickr.com/services/rest/", params={"method": "flickr.photos.search", "api_key": key, "lat": lat, "lon": lon, "radius": 0.25,
             "radius_units": "km", "per_page": 1, "media": "photos", "content_type": 1, "format": "json", "nojsoncallback": 1}, timeout=30, tries=2).json()
    return int(j.get("photos", {}).get("total") or 0)


def _inat(lat, lon):
    j = http("https://api.inaturalist.org/v1/observations", params={"lat": lat, "lng": lon, "radius": 0.3, "per_page": 0, "verifiable": "true"}, timeout=30, tries=2).json()
    return int(j.get("total_results") or 0)


def run(budget_min=300):
    key = secret("FLICKR_KEY")
    sd, od = FEED / "seed", FEED / "seedpop"; od.mkdir(exist_ok=True)
    t0, tiles, n = time.time(), 0, 0
    for f in sorted(sd.glob("*_*.json")):
        if time.time() - t0 > budget_min * 60:
            break
        o = od / f.name; old = read_json(o, {}) or {}
        if old.get("_at", "") >= _days_ago(120):
            continue
        spots = sorted((s for s in json.loads(f.read_text()).get("spots", []) if s.get("kind") != "hotspot"), key=lambda s: -(s.get("score") or 0))[:PER_TILE]
        out = {"_at": iso(utcnow())[:10]}
        for s in spots:
            try:
                c = _commons(s["lat"], s["lon"]); time.sleep(0.2)
                fl = _flickr(key, s["lat"], s["lon"]) if key else 0
                i = _inat(s["lat"], s["lon"]) if s.get("kind") in WILD else 0
                if s.get("kind") in WILD: time.sleep(1.0)   # iNaturalist asks for about 1 request per second
            except Exception as e:
                log.warning("seedpop %s: %s", s["id"], e); continue
            out[s["id"]] = [round(1.5 * math.log2(1 + c) + 1.2 * math.log2(1 + fl) + 0.8 * math.log2(1 + i), 1), c, fl, i]
            n += 1
        write_json(o, out); tiles += 1
    left = sum(1 for f in sd.glob("*_*.json") if (read_json(od / f.name, {}) or {}).get("_at", "") < _days_ago(120))
    return f"{tiles} tiles, {n} spots scored; {left} tiles left"


def _days_ago(d):
    import datetime as dt
    return (utcnow() - dt.timedelta(days=d)).strftime("%Y-%m-%d")
