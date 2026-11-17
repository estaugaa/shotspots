"""Forecast forwarder health: direct Open-Meteo vs the Cloudflare forwarder, same request."""
import requests, time, os, urllib.parse
os.makedirs("ux", exist_ok=True)
u = "https://api.open-meteo.com/v1/forecast?latitude=45.582,45.726&longitude=-122.353,-122.4&hourly=cloud_cover&forecast_days=1"
W = "https://shotspots-forms.shotspots-eric.workers.dev/om?u=" + urllib.parse.quote(u, safe="")
out = []
for name, url in [("direct", u), ("proxy", W), ("proxy again (cached)", W)]:
    t = time.time()
    try:
        r = requests.get(url, timeout=30, headers={"Origin": "https://estaugaa.github.io"})
        out.append(f"{name}: {r.status_code} {time.time()-t:.1f}s acao={r.headers.get('access-control-allow-origin')} stale={r.headers.get('x-stale')} {r.text[:150]}")
    except Exception as e: out.append(f"{name}: ERR {e}")
open("ux/proxytest.txt", "w").write("\n".join(out)); print("\n".join(out))
