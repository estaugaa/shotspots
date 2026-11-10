"""Which way starter spots face: a terrain horizon for each starter viewpoint, peak, beach, arch and lighthouse.

One USGS 3DEP chunk (~90 m) per 1-degree seed tile (plus a 0.25-degree margin), rays out to 25 km every 5 degrees.
The sunrise sector is 60-125 deg azimuth and the sunset sector 235-300 deg, wide enough for any season in the US.
A sector is "open" when the median horizon there is under 2 deg. Results go into the seed tile itself:
  light: "sunrise" | "sunset" | "both" | "blocked",  hz: [east deg, west deg]
Bare-earth terrain: trees and buildings aren't in it, so "open" means the land doesn't block the low sun.
"""
import json, time
import numpy as np
from .common import log, FEED
from .terrain import fetch_dem, apparent_alt, destination

KINDS = {"peak", "viewpoint", "beach", "arch", "lighthouse", "lake", "pass", "lookout"}
AZS = np.arange(0, 360, 5)
D = np.geomspace(200, 25000, 70)
E_SEC, W_SEC = (AZS >= 60) & (AZS <= 125), (AZS >= 235) & (AZS <= 300)
OPEN = 2.0
VERSION = 1


def _horizon(g, lat, lon):
    h0 = float(g.sample(np.array([lat]), np.array([lon]))[0])
    h0 = (0.0 if not np.isfinite(h0) or h0 < -100 else h0) + 2.0
    alt = np.empty(AZS.shape)
    for i, az in enumerate(AZS):
        la, lo = destination(lat, lon, az, D)
        z = g.sample(la, lo)
        z = np.where(np.isfinite(z) & (z > -100), z, 0.0)
        alt[i] = apparent_alt(h0, z, D).max()
    return alt


def run(budget_min=25):
    sd = FEED / "seed"
    t0, done, spots = time.time(), 0, 0
    for f in sorted(sd.glob("*_*.json")):
        if time.time() - t0 > budget_min * 60:
            break
        tile = json.loads(f.read_text())
        if tile.get("lightv") == VERSION:
            continue
        todo = [s for s in tile.get("spots", []) if s.get("kind") in KINDS]
        if todo:
            la0, lo0 = (int(v) for v in f.stem.split("_"))
            bbox = (lo0 - 0.25, la0 - 0.25, lo0 + 1.25, la0 + 1.25)
            try:
                g = fetch_dem(bbox, (1500, 1500), f"seedtile_{f.stem}")
            except Exception as e:
                log.warning("seed tile %s DEM: %s", f.stem, e); continue
            for s in todo:
                a = _horizon(g, s["lat"], s["lon"])
                e, w = float(np.median(a[E_SEC])), float(np.median(a[W_SEC]))
                eo, wo = e < OPEN, w < OPEN
                s["light"] = "both" if eo and wo else "sunrise" if eo else "sunset" if wo else "blocked"
                s["hz"] = [round(e, 1), round(w, 1)]
            spots += len(todo)
        tile["lightv"] = VERSION
        f.write_text(json.dumps(tile, separators=(",", ":")))
        done += 1
    left = sum(1 for f in sd.glob("*_*.json") if json.loads(f.read_text()).get("lightv") != VERSION)
    return f"{done} tiles, {spots} spots given a facing; {left} tiles left"
