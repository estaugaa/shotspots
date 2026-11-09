"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite. Read problem reports."""
import sys; sys.path.insert(0, ".")
from pipeline import forms
rows = forms.submissions("debug")
for r in rows[-3:]:
    print("=====")
    for k, v in r.items():
        print(f"{k}: {v}")
