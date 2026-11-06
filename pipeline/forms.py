"""Form submissions from the app (outing logs, settings, research requests, votes, push sign-ups).

New submissions land in Cloudflare D1 via the forms Worker (worker/); this module reads them through the
Cloudflare REST API with CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID. Submissions made before the move still
live in Netlify Forms and are read from there while NETLIFY_TOKEN is set (reading doesn't cost Netlify credits).
Both come back in the Netlify shape: {"id", "form_name", "created_at", "data": {...}}, oldest first.
"""
import json
from .common import http, secret, log

DB_NAME = "shotspots"
_cache = {}


def _cf(path, method="GET", body=None):
    tok, acct = secret("CLOUDFLARE_API_TOKEN"), secret("CLOUDFLARE_ACCOUNT_ID")
    r = http(f"https://api.cloudflare.com/client/v4/accounts/{acct}/{path}", method=method,
             headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
             data=json.dumps(body) if body is not None else None, timeout=60)
    j = r.json()
    if not j.get("success"):
        raise RuntimeError(f"Cloudflare API: {j.get('errors')}")
    return j["result"]


def d1(sql, params=None):
    if "db" not in _cache:
        dbs = _cf(f"d1/database?name={DB_NAME}")
        db = next((d for d in dbs if d["name"] == DB_NAME), None)
        if not db:
            raise RuntimeError("D1 database 'shotspots' not found; run the Cloudflare workflow")
        _cache["db"] = db["uuid"]
    res = _cf(f"d1/database/{_cache['db']}/query", "POST", {"sql": sql, "params": params or []})
    return res[0]["results"] if res else []


def _from_d1(form):
    if not (secret("CLOUDFLARE_API_TOKEN") and secret("CLOUDFLARE_ACCOUNT_ID")):
        return []
    rows = d1("SELECT id, form, created_at, data FROM submissions" + (" WHERE form = ?" if form else "") + " ORDER BY id",
              [form] if form else [])
    out = []
    for r in rows:
        try:
            data = json.loads(r["data"])
        except Exception:
            data = {}
        out.append({"id": f"cf-{r['id']}", "form_name": r["form"], "created_at": r["created_at"], "data": data})
    return out


def _from_netlify(form):
    tok, site = secret("NETLIFY_TOKEN"), secret("NETLIFY_SITE_ID")
    if not tok or not site:
        return []
    out, page = [], 1
    while page <= 20:
        j = http(f"https://api.netlify.com/api/v1/sites/{site}/submissions", params={"per_page": 100, "page": page},
                 headers={"Authorization": f"Bearer {tok}"}).json()
        if not j:
            break
        out += [x for x in j if not form or (x.get("form_name") or "") == form]
        page += 1
    return out


def submissions(form=None):
    """All submissions (optionally of one form), oldest first, from Netlify (legacy) and Cloudflare D1."""
    key = form or "*"
    if key in _cache:
        return _cache[key]
    out = []
    for src in (_from_netlify, _from_d1):
        try:
            out += src(form)
        except Exception as e:
            log.warning("forms: %s failed: %s", src.__name__, e)
    out.sort(key=lambda x: x.get("created_at") or "")
    _cache[key] = out
    return out
