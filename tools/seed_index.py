"""Rebuild feed/seed/index.json from the tile files, so parallel state batches can't overwrite each other's entries."""
import json, pathlib, datetime as dt
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
(sd / "index.json").write_text(json.dumps(idx, separators=(",", ":")))
print(len(idx["tiles"]), "tiles")
