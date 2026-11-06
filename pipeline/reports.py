"""Conditions reports from the in-app camera (form "conditions" in the Cloudflare D1 database).

Publishes the last 48 hours of shared reports (thumbnail + what people saw + what ShotSpots predicted) to
feed/reports.json and feed/cond/<id>.jpg, and drops older photos. Verification happens in the app: GPS within
1.5 km of the spot and a photo taken within the last 20 minutes; verified reports from anyone are used to score
forecasts (verify.py), unverified ones only when they're the owner's.
"""
import base64, datetime as dt, json
from .common import write_json, utcnow, iso, FEED, log
from .forms import submissions

KEEP_H = 48


def run():
    subs = submissions("conditions")
    cut = utcnow() - dt.timedelta(hours=KEEP_H)
    out, keep = [], set()
    cdir = FEED / "cond"
    cdir.mkdir(parents=True, exist_ok=True)
    for s in subs:
        d = s.get("data", {})
        try:
            t = dt.datetime.fromtimestamp(int(d.get("t", "0")) / 1000, dt.timezone.utc)
        except Exception:
            continue
        if t < cut or d.get("share") != "1" or not str(d.get("img", "")).startswith("data:image/jpeg;base64,"):
            continue
        rid = s["id"].replace("cf-", "r")
        f = cdir / f"{rid}.jpg"
        if not f.exists():
            try:
                f.write_bytes(base64.b64decode(d["img"].split(",", 1)[1]))
            except Exception as e:
                log.warning("report %s image: %s", rid, e)
                continue
        keep.add(f.name)
        try:
            pred = json.loads(d.get("pred") or "{}")
        except Exception:
            pred = {}
        out.append({"id": rid, "spot": d.get("spot"), "at": iso(t), "sky": d.get("sky"), "fog": d.get("fog"), "color": d.get("color"),
                    "verified": d.get("verified") == "1", "dist_m": d.get("dist_m"), "pred": pred, "img": f"cond/{f.name}",
                    "heading": int(d["heading"]) if str(d.get("heading", "")).isdigit() else None, "sun_rel": int(d["sun_rel"]) if str(d.get("sun_rel", "")).lstrip("-").isdigit() else None})
    for f in cdir.glob("*.jpg"):
        if f.name not in keep:
            f.unlink()
    out.sort(key=lambda r: r["at"], reverse=True)
    write_json("reports.json", {"gen": iso(utcnow()), "hours": KEEP_H, "reports": out})
    return f"{len(out)} shared reports in the last {KEEP_H} h ({len(subs)} total)"
