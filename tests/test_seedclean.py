"""Starter-spot cleaning rules (pipeline/seed.py): control towers aren't lookouts; fame borrowed from another Wikidata item goes."""
import json
from pipeline import seed

TOWER = {"man_made": "tower", "tower:type": "observation", "name": "Former Stapleton Airport Control Tower", "wikidata": "Q1436575", "wikipedia": "en:Stapleton International Airport"}
AIRPORT = {"n": 30, "img": True, "c": (39.7744, -104.8797), "cl": ["Q1248784"], "lab": "Stapleton International Airport"}   # the airport's own item and point


def test_control_tower_is_not_a_lookout():
    kind = lambda t: next((x[0] for x in seed.TYPES if x[1](t)), None)
    assert kind(TOWER) is None and not seed._wanted("n", TOWER)
    fire = {"man_made": "tower", "tower:type": "observation", "name": "WWII Fire Control Tower"}
    assert kind(fire) == "lookout" and seed._wanted("n", fire)
    assert kind({"man_made": "tower", "tower:type": "fire_lookout", "name": "Red Mountain Lookout"}) == "lookout"
    for nm in ("Training Tower", "Fire Training Tower (09-210)", "Fire Drill Tower", "WCCC Fire Training Center"):   # fire-department drill towers
        assert kind({"man_made": "tower", "tower:type": "observation", "name": nm}) is None


def test_borrowed_fame():
    lat, lon = 39.76075, -104.89193
    P = {**AIRPORT, "cl": ["Q41176"]}   # a building: no class rule
    assert seed._borrowed("a", "lookout", lat, lon, AIRPORT, None) == "Wikidata item is an airport"
    assert seed._borrowed("a", "landmark", lat, lon, {"n": 40, "img": True, "c": None, "cl": ["Q1"]}, None).startswith("Wikidata item has no location")
    assert "km away" in seed._borrowed("a", "viewpoint", lat, lon, {**P, "c": (41.0, -104.75)}, None)
    assert seed._borrowed("a", "lake", lat, lon, {**P, "c": (41.0, -104.75)}, None) is None   # natural features: the item is the feature
    assert seed._borrowed("a", "peak", lat, lon, {**P, "c": None}, None) is None
    assert seed._borrowed("a", "lookout", lat, lon, {**P, "c": None}, None) is None   # fire lookouts often lack a point on Wikidata
    assert seed._borrowed("a", "bridge", lat, lon, {**P, "c": (39.9, -104.75)}, None) is None   # 20 km: a rough point, same bridge
    assert seed._borrowed("seed-r1", "landmark", lat, lon, {**P, "c": (41.0, -104.75)}, None) is None   # a mapped area: its point is its middle
    assert seed._borrowed("a", "landmark", lat, lon, P, "b") == "Wikidata item belongs to another spot"
    assert seed._borrowed("a", "viewpoint", lat, lon, {**P, "cl": ["Q8502"]}, "a") is None   # a mountain item, own spot
    assert seed._borrowed("a", "viewpoint", lat, lon, None, None) is None and seed._borrowed("a", "viewpoint", lat, lon, {"n": 3}, None) is None
    assert seed._borrowed("a", "refuge", lat, lon, {**P, "cl": ["Q43229"]}, None) is None   # a park filed as an organisation
    for q, label in seed.NOT_A_VIEW.items():
        assert label in seed._borrowed("a", "landmark", lat, lon, {**P, "cl": [q]}, None)


def test_score_without_borrowed_fame():
    full, bare = seed._score("landmark", 2, TOWER, AIRPORT), seed._score("landmark", 2, TOWER, None)
    assert bare == 2 and full > 18   # sitelinks, image and the Wikipedia tag all belonged to the airport


def test_owners_name_then_distance():
    wd = {"Q1": {"c": (40.0, -105.0), "cl": [], "lab": "Golden Gate Bridge"}, "Q2": {"c": (41.0, -105.0), "cl": []}, "Q1436575": AIRPORT}
    o = seed._owners([("near", 40.001, -105.0, "Golden Gate Bridge", "Q1"), ("far", 40.02, -105.0, "Golden Gate Bridge", "Q1"), ("only", 41.0, -105.0, "x", "Q2"),
                      ("none", 40.0, -105.0, "x", None), ("tower", 39.76075, -104.89193, TOWER["name"], "Q1436575"),
                      ("airport", 39.76175, -104.89162, "Stapleton International Airport (closed)", "Q1436575")], wd)
    assert o == {"Q1": "near", "Q1436575": "airport"}


def test_clean_in_place(tmp_path, monkeypatch):
    feed, data = tmp_path / "feed", tmp_path / "data"
    (feed / "seed").mkdir(parents=True); (feed / "seedviews").mkdir()
    monkeypatch.setattr(seed, "FEED", feed); monkeypatch.setattr(seed, "DATA", data)
    spots = [{"id": "seed-n1", "name": "Former Stapleton Airport Control Tower", "kind": "lookout", "lat": 39.76, "lon": -104.89, "score": 20.5, "wd": "Q1436575", "osm": "node/1", "hz": [0.2, 0.2]},
             {"id": "seed-n2", "name": "M4A3 Sherman Tank", "kind": "landmark", "lat": 43.0, "lon": -89.0, "score": 23.4, "wd": "Q191480", "osm": "node/2", "hz": [1, 1]},
             {"id": "seed-w4", "name": "Elitch Gardens Observation Tower", "kind": "lookout", "lat": 39.75087, "lon": -105.01086, "score": 5, "wd": None, "osm": "way/4"},
             {"id": "seed-n3", "name": "Multnomah Falls", "kind": "waterfall", "lat": 45.576, "lon": -122.116, "score": 25.0, "wd": "Q1061633", "osm": "node/3"}]
    (feed / "seed" / "39_-105.json").write_text(json.dumps({"tile": "39_-105", "spots": spots}))
    (feed / "seed" / "index.json").write_text(json.dumps({"tiles": {"39_-105": 4}}))
    (feed / "seedviews" / "39_-105.json").write_text(json.dumps({"_at": "2026-11-01", "seed-n1": 110572, "seed-n2": 5000, "seed-n3": 400000}))
    monkeypatch.setattr(seed, "wikidata", lambda ids: {"Q191480": {"n": 40, "img": True, "c": None, "cl": ["Q1"], "lab": "M4 Sherman"},
                                                        "Q1061633": {"n": 30, "img": True, "c": (45.5762, -122.1158), "cl": ["Q34038"], "lab": "Multnomah Falls"}})
    monkeypatch.setattr(seed, "_parks", lambda: [(39.7507, -105.0105)])   # Elitch Gardens
    monkeypatch.setattr(seed, "_osm_tags", lambda refs: {"node/2": {"historic": "monument", "name": "M4A3 Sherman Tank", "wikidata": "Q191480", "wikipedia": "en:M4 Sherman"}})
    msg = seed.clean()
    out = {s["id"]: s for s in json.loads((feed / "seed" / "39_-105.json").read_text())["spots"]}
    assert "seed-n1" not in out and "seed-w4" not in out   # control tower and park ride dropped
    tank = out["seed-n2"]
    assert tank["wd"] is None and tank["wdx"] == "Q191480" and tank["score"] == 2 and tank["hz"] == [1, 1]   # landmark base 2, horizon kept
    assert out["seed-n3"]["wd"] == "Q1061633" and out["seed-n3"]["score"] == 25.0   # a real place keeps its fame
    views = json.loads((feed / "seedviews" / "39_-105.json").read_text())
    assert views == {"_at": "2026-11-01", "seed-n3": 400000}
    assert json.loads((feed / "seed" / "index.json").read_text())["tiles"]["39_-105"] == 2
    rep = json.loads((data / "seedclean.json").read_text())
    assert rep["fame_removed"] == 1 and len(rep["dropped_lookouts"]) == 2 and rep["rides"] == 1, msg
    seed.clean()   # running again changes nothing
    assert {s["id"]: s for s in json.loads((feed / "seed" / "39_-105.json").read_text())["spots"]} == out


def test_rides():
    sp = [{"id": "ride", "kind": "lookout", "lat": 39.75087, "lon": -105.01086}, {"id": "far", "kind": "lookout", "lat": 39.76, "lon": -105.01086},
          {"id": "view", "kind": "viewpoint", "lat": 39.75087, "lon": -105.01086}]
    assert seed._rides(sp, [(39.7507, -105.0105)]) == {"ride"} and seed._rides(sp, []) == set()
