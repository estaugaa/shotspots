"""One source of truth for *where* things are and *when* roads close.

config/ is authoritative for spot pins and core fields (config/spots.json), alignment targets
(config/landmarks.json) and seasonal road dates (config/access_rules.json). app/data.js keeps the writing
(tips, alerts, sources, shooting notes) and gets those fields overlaid from config:

* on every publish (pipeline/deploy.py writes the overlaid copy into _site), so the live app always matches
  the pipeline even if someone only edited config/;
* in the repo with `python tools/sync_data.py`, so the checked-in app/data.js matches too
  (tests/test_consistency.py fails until it does).

Nov 2026 audit: 18 pins and 2 alignment targets had drifted apart because both files were edited by hand.
"""
import json, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPOT_FIELDS = ("name", "region", "cats", "lat", "lon", "light", "effort", "months")


def load_app(path=None):
    t = Path(path or ROOT / "app" / "data.js").read_text()
    i, j = t.index("{"), t.rindex("}") + 1
    return t[:i], json.loads(t[i:j]), t[j:]


def dump_app(head, D, tail):
    return head + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + tail


def _shift(md, days):
    d = dt.date(2001, *map(int, md.split("-"))) + dt.timedelta(days=days)   # non-leap year
    return d.strftime("%m-%d")


def overlay(D, root=ROOT):
    """Return (D, changes): D with config's pins, targets and road dates applied. Changes is a list of strings."""
    ch = []
    cfg = json.load(open(root / "config" / "spots.json"))
    by = {s["id"]: s for s in D["spots"]}
    for c in cfg:
        s = by.get(c["id"])
        if s is None:
            s = {"id": c["id"], "tip": ""}
            D["spots"].append(s)
            by[c["id"]] = s
            ch.append(f"spot added from config: {c['id']}")
        for k in SPOT_FIELDS:
            if k in c and s.get(k) != c[k]:
                ch.append(f"spot {c['id']}.{k}: {s.get(k)!r} -> {c[k]!r}")
                s[k] = c[k]
    lms = {x["id"]: x for x in json.load(open(root / "config" / "landmarks.json"))}
    for k, t in D.get("TARGETS", {}).items():
        lm = lms.get("t-" + k) or lms.get("peak-" + k)
        if not lm:
            continue
        for f in ("lat", "lon", "elev"):
            if lm.get(f) is not None and t.get(f) != lm[f]:
                ch.append(f"target {k}.{f}: {t.get(f)} -> {lm[f]}")
                t[f] = lm[f]
    rules = json.load(open(root / "config" / "access_rules.json"))["rules"]
    for r in D.get("SEASONAL_ROADS", []):
        src = [a for a in rules if a.get("from") and a["type"] in ("closed", "open_only") and set(r["spots"]) <= set(a["spots"])]
        if len(src) != 1:
            continue
        a = src[0]
        fr, to = (a["from"], a["to"]) if a["type"] == "closed" else (_shift(a["to"], 1), _shift(a["from"], -1))
        if (r["from"], r["to"]) != (fr, to):
            ch.append(f"road {r['id']}: {r['from']}..{r['to']} -> {fr}..{to}")
            r["from"], r["to"] = fr, to
    return D, ch


def orphans(D, root=ROOT):
    """Spots the app has but config doesn't (the pipeline never forecasts them)."""
    ids = {c["id"] for c in json.load(open(root / "config" / "spots.json"))}
    return [s["id"] for s in D["spots"] if s["id"] not in ids]


def write_overlaid(src, dst, root=ROOT):
    head, D, tail = load_app(src)
    D, ch = overlay(D, root)
    Path(dst).write_text(dump_app(head, D, tail))
    return ch
