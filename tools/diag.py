"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite."""
import sys; sys.path.insert(0, ".")
from pipeline import forms
rows = [r for r in forms.submissions("conditions")]
print("CONDITIONS", len(rows))
for r in rows[-5:]:
    print("ROW", {k: (str(v)[:80] if k != "img" else f"<{len(str(v))} chars>") for k, v in r.items()})
