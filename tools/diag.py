"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite."""
import os, requests, base64, json
t = os.environ.get("EARTHDATA_TOKEN", "")
print("TOKEN len", len(t), "stripped len", len(t.strip()), "dots", t.count("."), "starts", t[:3] + "…" if t else "")
if t.count(".") == 2:   # JWT (Earthdata EDL token): show non-secret claims
    try:
        pl = json.loads(base64.urlsafe_b64decode(t.split(".")[1] + "=="))
        print("JWT claims", {k: pl[k] for k in pl if k in ("type", "uid", "exp", "iat", "iss", "client_id")})
    except Exception as e:
        print("JWT decode", e)
u = "https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5200/VNP46A4/2024/001/VNP46A4.A2024001.h05v04.002.2025161222823.h5"
for label, hdr in [("bearer", {"Authorization": "Bearer " + t.strip()})]:
    r = requests.get(u, headers=hdr, allow_redirects=False, timeout=60, stream=True)
    print(label, "first hop", r.status_code, r.headers.get("location", "")[:160], r.headers.get("content-type"))
    r2 = requests.get(u, headers=hdr, timeout=120, stream=True)
    print(label, "chain", [(h.status_code, h.url[:90]) for h in r2.history], "->", r2.status_code, r2.url[:90], r2.headers.get("content-type"))
    print(label, "first bytes", r2.raw.read(8))
r = requests.get("https://urs.earthdata.nasa.gov/api/users/tokens", headers={"Authorization": "Bearer " + t.strip()}, timeout=30)
print("EDL check", r.status_code, r.text[:120].replace(t.strip(), "<tok>"))
r = requests.get("https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/README", headers={"Authorization": "Bearer " + t.strip()}, timeout=30, allow_redirects=False)
print("LAADS api README", r.status_code, r.headers.get("location", "")[:120])
