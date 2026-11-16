"""How famous is a place: English Wikipedia page views (people, not bots) over the last 12 months, for every starter
spot that carries a Wikidata id (~37k of 75k). A clean fame signal that needs no keys (Flickr counts are unavailable).

feed/seedviews/<tile>.json  {_at, <spot id>: views_12m}   + index.json
The app adds a fame lift from views (seedFame in app.js): ~2k/yr adds nothing, ~20k +2, ~200k +4, ~2M +6.
Refreshed every 180 days; long first run queues its own next run (.more) until all tiles are done."""
import json, time, datetime as dt, urllib.parse
import requests
from .common import FEED, log, utcnow, iso, read_json

S = requests.Session(); S.headers["User-Agent"] = "ShotSpots/1.0 (https://estaugaa.github.io/shotspots/; photo-planning app) python-requests"


def _get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=60)
            if r.status_code == 200: return r.json()
            if r.status_code == 404: return None
            time.sleep(3 * (i + 1))
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def _titles(qids):
    out = {}
    for i in range(0, len(qids), 50):
        j = _get("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]), "props": "sitelinks", "sitefilter": "enwiki", "format": "json"}) or {}
        for q, e in (j.get("entities") or {}).items():
            t = ((e.get("sitelinks") or {}).get("enwiki") or {}).get("title")
            if t: out[q] = t
        time.sleep(0.2)
    return out


def _views(title, start, end):
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    j = _get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/{t}/monthly/{start}/{end}")
    return sum(x.get("views", 0) for x in (j or {}).get("items", [])) if j else 0


def run(budget_min=300):
    sd, od = FEED / "seed", FEED / "seedviews"; od.mkdir(exist_ok=True)
    today = dt.date.today().replace(day=1); end = today - dt.timedelta(days=1); start = end.replace(day=1) - dt.timedelta(days=330)
    start, end = start.replace(day=1).strftime("%Y%m%d00"), end.strftime("%Y%m%d00")
    t0, tiles, n, got = time.time(), 0, 0, 0
    fresh = iso(utcnow() - dt.timedelta(days=180))[:10]
    for f in sorted(sd.glob("*_*.json"), key=lambda f: (od / f.name).exists()):
        if time.time() - t0 > budget_min * 60:
            open(".more", "w").write("1"); break
        if (read_json(od / f.name, {}) or {}).get("_at", "") >= fresh: continue
        spots = [s for s in (read_json(f, {}) or {}).get("spots", []) if s.get("wd")]
        titles = _titles(sorted({s["wd"] for s in spots})) if spots else {}
        out = {"_at": iso(utcnow())[:10]}; cache = {}
        for s in spots:
            t = titles.get(s["wd"])
            if not t: continue
            if t not in cache: cache[t] = _views(t, start, end); time.sleep(0.12)
            if cache[t]: out[s["id"]] = cache[t]; got += 1
            n += 1
        (od / f.name).write_text(json.dumps(out, separators=(",", ":")))
        tiles += 1
    (od / "index.json").write_text(json.dumps(sorted(f.stem for f in od.glob("*_*.json"))))
    left = sum(1 for f in sd.glob("*_*.json") if not (od / f.name).exists())
    return f"{tiles} tiles, {n} spots with an English article, {got} with views; {left} tiles left"
