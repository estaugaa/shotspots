"""Rebuild feed/seed/index.json from the tile files, so parallel state batches can't overwrite each other's entries."""
import json, pathlib, sys, datetime as dt
sd = pathlib.Path("feed/seed")
try:
    idx = json.loads((sd / "index.json").read_text())
except Exception:
    idx = {"tiles": {}, "states": {}}
idx["tiles"], counts = {}, {}
for f in sorted(sd.glob("*_*.json")):
    sp = json.loads(f.read_text()).get("spots", [])
    idx["tiles"][f.stem] = len(sp)
    for x in sp:
        counts[x.get("state")] = counts.get(x.get("state"), 0) + 1
for st, n in counts.items():
    if st:
        idx.setdefault("states", {}).setdefault(st, {})["spots"] = n
idx["gen"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
if "--missing" in sys.argv:
    ALL = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
    print(" ".join(st for st in ALL if counts.get(st, 0) < 50))
    sys.exit(0)
(sd / "index.json").write_text(json.dumps(idx, separators=(",", ":")))
print(len(idx["tiles"]), "tiles")

