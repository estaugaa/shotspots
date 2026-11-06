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
    shutil.copytree(FEED, out / "feed", ignore=shutil.ignore_patterns("*.tmp"))
    ep = ROOT / "config" / "endpoints.json"
    if ep.exists():
        shutil.copy(ep, out / "endpoints.json")
    (out / ".nojekyll").write_text("")
    n = sum(1 for p in out.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    return f"site built: {n} files, {size / 1e6:.1f} MB in {out}"
