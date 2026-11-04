"""Access: who manages the land under each pin (PAD-US) and current Forest Service alerts.

PAD-US (USGS Protected Areas Database, public-access layer) is MEASURED land status; a pin outside any
PAD-US polygon is reported as "not on mapped public land", which usually means private or road right-of-way:
check before you park. Forest Service alert titles are matched to spots by name keywords (ESTIMATED match).
"""
import re, json
from .common import http, spots, write_json, log, utcnow, iso

PADUS = "https://services1.arcgis.com/CD5mKowwN6nIaqd8/ArcGIS/rest/services/PADUS3_0_PublicAccess/FeatureServer/0/query"
ALERTS = {"crgnsa": "https://www.fs.usda.gov/alerts/crgnsa/alerts-notices",
          "mthood": "https://www.fs.usda.gov/alerts/mthood/alerts-notices",
          "giffordpinchot": "https://www.fs.usda.gov/alerts/giffordpinchot/alerts-notices"}
STOP = set("the and of at on in a to from road rd trail falls park area state point view viewpoint scout pick lake river mountain mt creek".split())


def padus(lat, lon):
    j = http(PADUS, params={"geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
                            "outFields": "*", "returnGeometry": "false", "f": "json"}).json()
    feats = j.get("features", [])
    if not feats:
        return None
    a = feats[0]["attributes"]
    pick = lambda *ks: next((a[k] for k in a for q in ks if k.lower() == q.lower()), None)
    return {"unit": pick("Unit_Nm", "Loc_Nm"), "manager": pick("Mang_Name", "Mang_Name_Desc", "d_Mang_Nam"), "access": pick("Pub_Access", "d_Pub_Acce"),
            "type": pick("Des_Tp", "d_Des_Tp")}


def alerts():
    out = []
    for forest, url in ALERTS.items():
        try:
            html = http(url).text
        except Exception as e:
            log.warning("alerts %s: %s", forest, e)
            continue
        for href, title in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{12,200})</a>', html):
            t = re.sub(r"\s+", " ", title).strip()
            if re.search(r"clos|restrict|fire|detour|gate|construction|permit", t, re.I):
                out.append({"forest": forest, "title": t, "url": href if href.startswith("http") else "https://www.fs.usda.gov" + href})
    return out


def run():
    al = alerts()
    res = {}
    for s in spots():
        rec = {}
        try:
            la, lo = s["park"] if s.get("park") else (s["lat"], s["lon"])
            rec["land"] = padus(la, lo)
        except Exception as e:
            rec["land"] = {"error": str(e)[:80]}
        words = [w for w in re.findall(r"[A-Za-z']{4,}", s["name"].lower()) if w not in STOP]
        hits = [a for a in al if sum(w in a["title"].lower() for w in words) >= 1 and len(words) > 0]
        if hits:
            rec["alerts"] = hits[:4]
        res[s["id"]] = rec
    write_json("access.json", {"gen": iso(utcnow()), "spots": res, "alerts_total": len(al),
                               "note": "Land status from PAD-US 3.0 public-access layer; alerts matched to spots by name keywords, so check the linked notice."})
    return f"{len(res)} spots, {len(al)} forest alerts"
