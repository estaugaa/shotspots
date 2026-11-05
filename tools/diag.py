"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite."""
import time, sys
sys.path.insert(0, ".")
from pipeline import trails
from pipeline.common import spots
S = {s["id"]: s for s in spots()}
for sid in ["angels-rest", "vista-house", "steigerwald", "larch-mtn", "ecola"]:
    t = time.time()
    try:
        els = trails.fetch(S[sid]["lat"], S[sid]["lon"]); t1 = time.time() - t
        r = trails.route(S[sid], els)
        if r.get("pts") and r["kind"] == "walk":
            r["up_m"], r["down_m"], r["z_park"], r["z_spot"] = trails.profile(r["pts"])
        r.pop("pts", None)
        print("TRAIL", sid, f"overpass {t1:.1f}s total {time.time()-t:.1f}s", len(els), r)
    except Exception as e:
        import traceback; traceback.print_exc(); print("TRAIL", sid, "ERR", e)
