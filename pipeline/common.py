"""Shared helpers for the ShotSpots pipeline.

Every module writes JSON into feed/ and records a provenance entry saying where its numbers came from,
when, and whether they are MEASURED (observations), MODELED (physics/NWP output) or ESTIMATED
(statistical or heuristic). The app shows these labels next to the numbers.
"""
import json, os, time, math, datetime as dt, logging, traceback
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "feed"
DATA = ROOT / "data"
CONFIG = ROOT / "config"
CACHE = Path(os.environ.get("SS_CACHE", ROOT / ".cache"))
for p in (FEED, DATA, CACHE):
    p.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("shotspots")
UA = {"User-Agent": "ShotSpots-pipeline/1.0 (personal photo planner; github.com)"}
TZ = "America/Los_Angeles"


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def iso(t):
    if t is None:
        return None
    if isinstance(t, (int, float)):
        t = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def spots(cats=None):
    s = json.load(open(CONFIG / "spots.json"))
    if cats:
        s = [x for x in s if set(x["cats"]) & set(cats)]
    return s


def landmarks():
    return json.load(open(CONFIG / "landmarks.json"))


def links():
    return json.load(open(CONFIG / "links.json"))


def km(a_lat, a_lon, b_lat, b_lon):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def bearing(a_lat, a_lon, b_lat, b_lon):
    p1, p2, dl = math.radians(a_lat), math.radians(b_lat), math.radians(b_lon - a_lon)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def http(url, params=None, headers=None, tries=4, timeout=60, stream=False, method="GET", data=None):
    h = dict(UA)
    h.update(headers or {})
    last = None
    for i in range(tries):
        try:
            r = requests.request(method, url, params=params, headers=h, timeout=timeout, stream=stream, data=data)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1) ** 2)
    raise last


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.load(open(p))
    except Exception:
        return default


def write_json(name, obj, compact=True):
    p = FEED / name
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":") if compact else None, indent=None if compact else 1, default=_default)
    os.replace(tmp, p)
    log.info("wrote %s (%d bytes)", p.relative_to(ROOT), p.stat().st_size)


def _default(o):
    try:
        import numpy as np
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if not np.isfinite(o) else round(float(o), 4)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    if isinstance(o, (dt.datetime, dt.date)):
        return iso(o) if isinstance(o, dt.datetime) else o.isoformat()
    raise TypeError(type(o))


def r(x, n=2):
    try:
        if x is None or (isinstance(x, float) and not math.isfinite(x)):
            return None
        return round(float(x), n)
    except Exception:
        return None


# ---------- provenance / status ----------
def status(source, ok, kind, note="", **extra):
    """kind: MEASURED | MODELED | ESTIMATED"""
    st = read_json(FEED / "status.json", {})
    st[source] = {"ok": bool(ok), "kind": kind, "note": note, "at": iso(utcnow()), **extra}
    write_json("status.json", st, compact=False)


def run_module(name, fn, kind, note=""):
    """Run one module; never let one failing source break the rest of the pipeline."""
    t0 = time.time()
    try:
        out = fn()
        status(name, True, kind, out if isinstance(out, str) else note, secs=round(time.time() - t0, 1))
        return True
    except Exception as e:
        log.error("%s failed: %s\n%s", name, e, traceback.format_exc())
        status(name, False, kind, f"{type(e).__name__}: {str(e)[:300]}", secs=round(time.time() - t0, 1))
        return False


def secret(name):
    v = os.environ.get(name, "").strip()
    return v or None
