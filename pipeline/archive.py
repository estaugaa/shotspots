"""Long-term archive of what the jobs observe, so seasons and years can be compared and the app's predictions checked
against outcomes. data/archive/<kind>/<YYYY-MM>.csv.gz: one row per report, gzip CSV, kept indefinitely (data branch).

kinds: obs (airport reports near sunrise/sunset, metar.py), nwsfog (NWS fog advisories, natdata.py), goes (one line per
satellite scan, goes.py; spot lists in goes/sets.json), camtruth (webcam colour, camtruth.py), skill (day-ahead forecast vs
airport cloud, skill.py). Predictions (tools/scoretest.py --live) are JSON lines in predictions/<YYYY-MM>.jsonl.gz.

append() rewrites only the months it touches, with mtime=0 so an unchanged month gives identical bytes (no empty commits).
Values are stored as text; readers convert (num(), flag())."""
import csv, gzip, io, json
from .common import DATA

ROOT = DATA / "archive"


def path(kind, month, ext="csv.gz"):
    return ROOT / kind / f"{month}.{ext}"


def _cell(v):
    if v is None: return ""
    if isinstance(v, bool): return "1" if v else "0"
    if isinstance(v, (list, dict)): return json.dumps(v, separators=(",", ":"))
    return str(v)


def num(x):
    try: return float(x) if x not in (None, "", "None") else None
    except ValueError: return None


def flag(x):
    return str(x) in ("1", "True", "true")


def _load(p):
    with gzip.open(p, "rt", newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def append(kind, fields, rows, when, key):
    """Add rows (dicts) to their month files. when(row) -> ISO time string (month = first 7 characters); key(row) -> a
    tuple that identifies a report (rows already archived are skipped; computed on the text values). Returns rows added."""
    by = {}
    for r in rows:
        r = {f: _cell(r.get(f)) for f in fields}
        w = when(r)
        if w and len(w) >= 7: by.setdefault(w[:7], []).append(r)
    added = 0
    for m, rs in sorted(by.items()):
        p = path(kind, m)
        head, old = _load(p) if p.exists() else (list(fields), [])
        head += [f for f in fields if f not in head]   # a new column: older rows get it empty
        have = {key(r) for r in old}
        new = []
        for r in rs:
            k = key(r)
            if k not in have: have.add(k); new.append(r)
        if not new: continue
        buf = io.StringIO(); w = csv.DictWriter(buf, head, extrasaction="ignore", lineterminator="\n")
        w.writeheader(); w.writerows(old + new)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp"); tmp.write_bytes(gzip.compress(buf.getvalue().encode("utf-8"), 9, mtime=0)); tmp.replace(p)
        added += len(new)
    return added


def months(kind, since="", until="9999", ext="csv.gz"):
    """Month files of a kind from the month of `since` to the month of `until` (ISO strings), oldest first."""
    d = ROOT / kind
    if not d.exists(): return []
    return [p for p in sorted(d.glob(f"*.{ext}")) if since[:7] <= p.name[:7] <= until[:7]]


def read(kind, since="", field=None, until="9999"):
    """Rows (text dicts) of the months covering since..until; with `field`, only rows whose field is in [since, until]."""
    out = []
    for p in months(kind, since, until):
        out += [r for r in _load(p)[1] if not field or since <= (r.get(field) or "") <= until]
    return out


def append_jsonl(kind, records, month):
    """Append JSON records to <kind>/<month>.jsonl.gz (one record per line). Used for the prediction log."""
    p = path(kind, month, "jsonl.gz"); p.parent.mkdir(parents=True, exist_ok=True)
    old = gzip.decompress(p.read_bytes()).decode("utf-8") if p.exists() else ""
    new = "".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n" for r in records)
    tmp = p.with_suffix(".tmp"); tmp.write_bytes(gzip.compress((old + new).encode("utf-8"), 9, mtime=0)); tmp.replace(p)
    return len(records)


def read_jsonl(kind, since="", until="9999"):
    out = []
    for p in months(kind, since, until, "jsonl.gz"):
        out += [json.loads(l) for l in gzip.decompress(p.read_bytes()).decode("utf-8").splitlines() if l.strip()]
    return out
