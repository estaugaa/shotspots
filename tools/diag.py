"""Scratch diagnostics run on Actions (workflow 'Diagnostic'). Safe to overwrite."""
import requests
B = "https://estaugaa.github.io/shotspots/"
for p in ["", "index.html", "feed/manifest.json", "feed/widget.json", "feed/hrrr.json", "endpoints.json", "widget/ShotSpots.js", "sw.js", "forms.js", "manifest.webmanifest"]:
    r = requests.get(B + p, timeout=30)
    print("SITE", r.status_code, p or "/", len(r.content), r.headers.get("content-type", "")[:30], (r.text[:70].replace("\n", " ") if p.endswith(".json") and r.ok and len(r.text) < 400 else ""))
import json
m = requests.get(B + "feed/manifest.json", timeout=30).json(); print("SITE manifest gen", m.get("gen"), len(m.get("files", [])), "files")
