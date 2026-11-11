"""Scratch API probe (run via Diagnostic workflow). Prints shapes, not data."""
import os, json, requests
os.makedirs("ux", exist_ok=True); out = []
def p(*a): out.append(" ".join(str(x) for x in a))
def get(u, **kw):
    try:
        r = requests.get(u, timeout=60, **kw); p("\n##", u[:120], r.status_code, len(r.content)); return r
    except Exception as e: p("\n##", u[:120], "ERR", e); return None
K = os.environ.get("NPS_API_KEY") or "DEMO_KEY"
for ep in ["parks?limit=1", "alerts?limit=3", "feespasses?limit=2"]:
    r = get(f"https://developer.nps.gov/api/v1/{ep}&api_key={K}")
    if r is not None and r.ok:
        j = r.json(); p("total", j.get("total")); d = j.get("data") or []
        if d: p("keys", sorted(d[0].keys())); p(json.dumps(d[0])[:1500])
for u in ["https://services1.arcgis.com/fBc8EJBxQRMcHlei/arcgis/rest/services/NPS_Land_Resources_Division_Boundary_and_Tract_Data_Service/FeatureServer/2/query?where=1%3D1&outFields=UNIT_CODE,UNIT_NAME&returnGeometry=false&resultRecordCount=2&f=json",
          "https://services1.arcgis.com/fBc8EJBxQRMcHlei/arcgis/rest/services/NPS_Land_Resources_Division_Boundary_and_Tract_Data_Service/FeatureServer?f=json"]:
    r = get(u)
    if r is not None: p(r.text[:900])
r = get("https://services.usanpn.org/npn_portal/phenophases/getPhenophases.json")
if r is not None and r.ok:
    ph = r.json(); p("n", len(ph)); p([x for x in ph if any(w in json.dumps(x).lower() for w in ["color", "flower", "open flowers"])][:12])
r = get("https://services.usanpn.org/npn_portal/observations/getSummarizedData.json", params={"request_src": "shotspots", "start_date": "2026-10-20", "end_date": "2026-11-10", "phenophase_id[0]": 498, "climate_data": 0})
if r is not None and r.ok:
    j = r.json(); p("rows", len(j)); p(json.dumps(j[:2])[:1200])
open("ux/probe.txt", "w").write("\n".join(out))
