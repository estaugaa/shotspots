"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite."""
import sys, os, json; sys.path.insert(0, ".")
from pipeline import forms
rows = forms.submissions()
print("TOTAL", len(rows))
from collections import Counter
print("FORMS", Counter(r.get("form-name") or r.get("_form") or r.get("form") for r in rows))
for r in sorted(rows, key=lambda r: str(r.get("_at") or r.get("created_at") or r.get("t") or ""))[-6:]:
    print("ROW", {k: (str(v)[:70] if k != "img" else f"<{len(str(v))}>") for k, v in r.items()})
import requests
for path in ["/health"]:
    try: print("WORKER", requests.get("https://shotspots-forms.shotspots-eric.workers.dev" + path, timeout=20).text[:300])
    except Exception as e: print("WORKER ERR", e)
r = requests.post("https://shotspots-forms.shotspots-eric.workers.dev/f/conditions", headers={"Origin": "https://estaugaa.github.io", "content-type": "application/json"},
                  data=json.dumps({"_dev": "1", "spot": "diag-test", "sky": "clear", "img": "data:image/jpeg;base64," + "A" * 150000}), timeout=30)
print("POST conditions", r.status_code, r.text[:200])
