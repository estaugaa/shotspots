"""Nightly accuracy audit (Nov 2026). Each test is one class of mistake found by hand in the first audit,
so it can't come back silently. Run: python -m pytest -q tests/test_audit.py  (needs node for the alignment test)."""
import datetime as dt, json, re, shutil, subprocess, sys, pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import spotsync

HEAD, D, TAIL = spotsync.load_app()
TODAY = dt.date.today()


def texts():
    """(where, text) for every user-facing sentence in app/data.js."""
    for s in D["spots"]:
        for f in ("tip", "alert"):
            if s.get(f):
                yield f"{s['id']}.{f}", s[f]
    for k, v in D.get("PRO", {}).items():
        for f, x in v.items():
            if isinstance(x, str):
                yield f"PRO {k}.{f}", x
    for e in D.get("WEVENTS", []):
        for f in ("what", "count", "tips"):
            if e.get(f):
                yield f"event {e['id']}.{f}", e[f]
    for r in D.get("SEASONAL_ROADS", []):
        yield f"road {r['id']}", r.get("text", "")


def test_app_matches_config():
    """Pins, alignment targets and road dates come from config/. Fix: python tools/sync_data.py"""
    _, ch = spotsync.overlay(json.loads(json.dumps(D)))
    assert not ch, "app/data.js differs from config/ (run python tools/sync_data.py):\n" + "\n".join(ch[:30])


def test_every_spot_is_in_config():
    assert not spotsync.orphans(D), "spots with no config entry get no forecasts"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_alignments_still_line_up():
    """Every stored sun/moon alignment must still line up with its target (catches moved or wrong targets)."""
    r = subprocess.run(["node", str(ROOT / "tools" / "align_check.js"), str(ROOT)], capture_output=True, text=True)
    rep = json.loads(r.stdout)
    assert rep["failed"] == 0, f"{rep['failed']} of {rep['checked']} alignments no longer line up: {rep['bad'][:5]}"


def test_references_exist():
    ids = {s["id"] for s in D["spots"]}
    bad = [f"event {e['id']}: {x}" for e in D["WEVENTS"] for x in e["spots"] if x not in ids]
    bad += [f"road {r['id']}: {x}" for r in D["SEASONAL_ROADS"] for x in r["spots"] if x not in ids]
    bad += [f"vantage {k}: {v.get('spot')}" for k, v in D["VANT"].items() if v.get("spot") not in ids]
    bad += [f"PRO {k}" for k in D.get("PRO", {}) if k not in ids]
    bad += [f"src {s['id']}: {k}" for s in D["spots"] for k in s.get("src", []) if k not in D["SRC"]]
    assert not bad, bad


STALE = re.compile(r"\b(this (year|month|week|season)(?!'s)|about now|right now|as of this writing|last chance|"
                   r"so (no permit is needed|it's open|it's closed) now)\b", re.I)


def test_no_wording_that_goes_stale():
    """Text is written once and read for months: say the dates, not 'this month' or 'about now'."""
    bad = [f"{w}: …{x[max(0, m.start() - 50):m.end() + 30]}…" for w, x in texts() for m in STALE.finditer(x)]
    assert not bad, "\n".join(bad)


MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? (\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?(?:,? | in )(20\d\d)\b", re.I)
SCHEDULE = re.compile(r"\b(runs?|ran|open|opens|reopen\w*|clos\w*|through|until|expected|scheduled|registration|festival|tours?|permit|from)\b", re.I)


def test_no_expired_schedules():
    """A schedule whose date has passed ('runs March 18-21, 2026', 'closed until Oct 1, 2026') is now wrong.
    Dated history ('record 409 on Dec 20, 2023') is fine: only dates near schedule words are checked."""
    bad = []
    for w, x in texts():
        for m in DATE.finditer(x):
            day = int(m.group(3) or m.group(2))
            try:
                d = dt.date(int(m.group(4)), MONTHS[m.group(1).lower()[:3]], day)
            except ValueError:
                continue
            if d < TODAY and SCHEDULE.search(x[max(0, m.start() - 60):m.start()]):
                bad.append(f"{w}: …{x[max(0, m.start() - 60):m.end()]}…")
    rules = json.load(open(ROOT / "config" / "access_rules.json"))["rules"]
    bad += [f"access rule {r['spots']}: until {r['until']}" for r in rules if r.get("until") and r["until"] < TODAY.isoformat()]
    assert not bad, "\n".join(bad)
