"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite."""
import sys, requests, collections
sys.path.insert(0, ".")
from pipeline import forms
W = "https://shotspots-forms.shotspots-eric.workers.dev"
print("HEALTH", requests.get(W + "/health", timeout=20).text)
r = requests.post(W + "/f/spot_feedback", data={"id": "diag-test", "vote": "clear", "name": "pipeline self-test"}, headers={"Origin": "https://estaugaa.github.io"}, timeout=20)
print("POST", r.status_code, r.text, r.headers.get("Access-Control-Allow-Origin"))
s = forms.submissions()
print("READ", len(s), collections.Counter(x["form_name"] for x in s), [x["id"] for x in s][-3:])
print("D1 rows", forms.d1("SELECT COUNT(*) AS n FROM submissions"))
