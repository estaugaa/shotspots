"""Apply config/ (pins, landmarks, road dates) to app/data.js in the repo. See pipeline/spotsync.py.

    python tools/sync_data.py          write the changes
    python tools/sync_data.py --check  list them and exit 1 if any (used by the nightly check)
"""
import sys
sys.path.insert(0, ".")
from pipeline import spotsync

head, D, tail = spotsync.load_app()
D, ch = spotsync.overlay(D)
for c in ch:
    print(c)
orph = spotsync.orphans(D)
if orph:
    print("in app/data.js but not config/spots.json (no forecasts):", ", ".join(orph))
if "--check" in sys.argv:
    sys.exit(1 if ch else 0)
if ch:
    (spotsync.ROOT / "app" / "data.js").write_text(spotsync.dump_app(head, D, tail))
print(f"{len(ch)} change(s) {'written' if ch else ''}".strip())
