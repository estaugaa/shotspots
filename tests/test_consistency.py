"""The app (app/data.js) and the pipeline (config/) must describe the same places, or forecasts, alignments and
the map end up in different spots. Found Nov 2026: 18 pins and 2 alignment targets had drifted apart."""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]


def app_data():
    t = (ROOT / "app" / "data.js").read_text()
    return json.loads(t[t.index("{"):t.rindex("}") + 1])


def test_spot_pins_match():
    D = app_data(); C = {s["id"]: s for s in json.load(open(ROOT / "config" / "spots.json"))}
    bad = [s["id"] for s in D["spots"] if s["id"] in C and (abs(C[s["id"]]["lat"] - s["lat"]) > 1e-4 or abs(C[s["id"]]["lon"] - s["lon"]) > 1e-4)]
    assert not bad, f"pins differ between app/data.js and config/spots.json: {bad}"


def test_alignment_targets_match_landmarks():
    D = app_data(); L = {x["id"]: x for x in json.load(open(ROOT / "config" / "landmarks.json"))}
    bad = []
    for k, t in D["TARGETS"].items():
        lm = L.get("t-" + k) or L.get("peak-" + k)
        if lm and (abs(lm["lat"] - t["lat"]) > 2e-3 or abs(lm["lon"] - t["lon"]) > 2e-3):
            bad.append(k)
    assert not bad, f"alignment targets differ from config/landmarks.json: {bad}"
