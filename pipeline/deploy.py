"""Publish app/ + feed/ to Netlify as one zip deploy (site files at /, data feed at /feed/)."""
import io, zipfile, time
from .common import ROOT, FEED, http, secret, log


def run():
    tok, site = secret("NETLIFY_TOKEN"), secret("NETLIFY_SITE_ID")
    if not tok or not site:
        raise RuntimeError("NETLIFY_TOKEN / NETLIFY_SITE_ID not set")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in (ROOT / "app").rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(ROOT / "app"))
        for p in FEED.rglob("*"):
            if p.is_file() and not p.name.endswith(".tmp"):
                z.write(p, "feed/" + str(p.relative_to(FEED)))
        z.writestr("_headers", "/feed/*\n  Cache-Control: public, max-age=300\n  Access-Control-Allow-Origin: *\n/sw.js\n  Cache-Control: no-cache\n")
    r = http(f"https://api.netlify.com/api/v1/sites/{site}/deploys", method="POST", data=buf.getvalue(),
             headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/zip"}, timeout=300).json()
    dep = r["id"]
    for _ in range(30):
        time.sleep(4)
        st = http(f"https://api.netlify.com/api/v1/deploys/{dep}", headers={"Authorization": f"Bearer {tok}"}).json()
        if st["state"] in ("ready", "error"):
            log.info("deploy %s %s", dep, st["state"])
            if st["state"] == "error":
                raise RuntimeError(st.get("error_message"))
            return dep
    return dep
