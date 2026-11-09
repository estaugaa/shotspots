"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite. Read problem reports."""
import sys; sys.path.insert(0, ".")
from pipeline import forms
rows = forms.submissions("debug")
for r in rows[-3:]:
    print("=====")
    d = r.get("data") if isinstance(r.get("data"), dict) else r
    for k in ("errs", "taps", "stick", "view"):
        for line in str(d.get(k, "")).split("\n"):
            print(f"DBG {k}: {line}")
