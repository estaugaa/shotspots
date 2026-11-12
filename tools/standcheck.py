"""Run the production stands analysis on the Gorge prototype spots; print results (ux/standcheck.txt)."""
import json, os, sys
sys.path.insert(0, ".")
from pipeline import stands
os.makedirs("ux", exist_ok=True)
CW = lambda b: ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"][int((b % 360) / 22.5 + .5) % 16]
out = []
for s in json.load(open("tools/stand_spots.json")):
    vps = stands.osm_viewpoints([s])
    r = stands.analyse(s, vps)
    out.append(f"{s['id']:<18} " + ("nothing" if not r else f"stand {r.get('d','-')} m from pin, {r.get('u','-')} people | face {CW(r['f']) if 'f' in r else '-'} ({r.get('f','-')}) via {r.get('fs','-')}"))
open("ux/standcheck.txt", "w").write("\n".join(out))
