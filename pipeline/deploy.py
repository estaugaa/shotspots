"""Assemble the static site for GitHub Pages: app/ at the root, the data feed at feed/, plus endpoints.json
(the forms Worker URL written by the Cloudflare workflow). The Pages upload/deploy happens in
.github/workflows/publish.yml. (Netlify production deploys were dropped: the Free plan's 300 credits a month
cover only ~20 deploys, and this pipeline publishes every 30 minutes.)"""
import shutil
from .common import ROOT, FEED


def build_site(out=None):
    out = out or ROOT / "_site"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "app", out)
    # service-worker version = hash of the app files, so phones always pick up a changed app (no manual bump)
    import hashlib, re as _re
    h = hashlib.sha1()
    for p in sorted((ROOT / "app").rglob("*")):
        if p.is_file() and p.name != "sw.js":
            h.update(p.name.encode()); h.update(p.read_bytes())
    sw = out / "sw.js"
    sw.write_text(_re.sub(r'const V="ss2-v[^"]*"', f'const V="ss2-v{h.hexdigest()[:10]}"', sw.read_text(), count=1))
    shutil.copytree(FEED, out / "feed", ignore=shutil.ignore_patterns("*.tmp"))
    ep = ROOT / "config" / "endpoints.json"
    if ep.exists():
        shutil.copy(ep, out / "endpoints.json")
    (out / ".nojekyll").write_text("")
    n = sum(1 for p in out.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    return f"site built: {n} files, {size / 1e6:.1f} MB in {out}"
