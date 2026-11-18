"""Long-term archive (pipeline/archive.py) and the readers that use it."""
import datetime as dt, gzip, json
from pipeline import archive, goes, metar


def _use(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "ROOT", tmp_path / "archive")
    monkeypatch.setattr(goes, "DATA", tmp_path)


def test_append_dedup_months_and_stable_bytes(tmp_path, monkeypatch):
    _use(tmp_path, monkeypatch)
    f, when, key = ["id", "t", "v", "fog"], (lambda r: r["t"]), (lambda r: (r["id"], r["t"]))
    rows = [{"id": "KPDX", "t": "2026-10-31T14:00", "v": 1.5, "fog": True}, {"id": "KPDX", "t": "2026-11-01T14:00", "v": None, "fog": False}]
    assert archive.append("obs", f, rows, when, key) == 2
    b = archive.path("obs", "2026-11").read_bytes()
    assert archive.append("obs", f, rows, when, key) == 0          # same reports again: nothing added
    assert archive.path("obs", "2026-11").read_bytes() == b         # and the file is byte-identical (no empty commits)
    assert [p.name for p in archive.months("obs")] == ["2026-10.csv.gz", "2026-11.csv.gz"]
    got = archive.read("obs", "2026-11-01", "t")
    assert len(got) == 1 and got[0]["v"] == "" and archive.flag(got[0]["fog"]) is False
    assert archive.num(archive.read("obs")[0]["v"]) == 1.5 and archive.flag(archive.read("obs")[0]["fog"])
    archive.append("obs", f + ["new"], [{"id": "KTTD", "t": "2026-11-02T14:00", "new": 3}], when, key)   # a new column
    r = archive.read("obs", "2026-11")
    assert r[0]["new"] == "" and r[-1]["new"] == "3"


def test_jsonl(tmp_path, monkeypatch):
    _use(tmp_path, monkeypatch)
    archive.append_jsonl("predictions", [{"a": 1}], "2026-11"); archive.append_jsonl("predictions", [{"a": 2}], "2026-11")
    assert [x["a"] for x in archive.read_jsonl("predictions", "2026-11")] == [1, 2]


def test_metar_history_window(tmp_path, monkeypatch):
    _use(tmp_path, monkeypatch)
    now = dt.datetime.now(dt.timezone.utc)
    t = lambda d: (now - dt.timedelta(days=d)).strftime("%Y-%m-%dT%H:00")
    rows = [{"id": "KPDX", "name": "Portland", "lat": 45.6, "lon": -122.6, "t": t(d), "vis_mi": 0.5, "wx": "FG", "base_ft": 200, "fog": True} for d in (1, 70)]
    archive.append("obs", metar.OBS_FIELDS, rows, lambda r: r["t"], lambda r: (r["id"], r["t"]))
    h = metar.history(60)
    assert len(h) == 1 and h[0]["fog"] is True and h[0]["vis_mi"] == 0.5 and h[0]["base_ft"] == 200.0


def test_goes_migration_and_lookup(tmp_path, monkeypatch):
    _use(tmp_path, monkeypatch)
    (tmp_path / "goes_history_202611051752.txt").write_text("#ids a,b\n2026-11-05T10:00:00.3Z 1234\n")
    goes.keep_history(["b", "c"], [("2026-11-05T10:20:00.1Z", "5678")])
    assert not list(tmp_path.glob("goes_history*.txt"))             # old files moved in, then removed
    t = dt.datetime(2026, 11, 5, 10, 18, tzinfo=dt.timezone.utc)
    assert goes.history_at("b", t)[1:] == (55, 66)                  # nearest scan covering b is the new one
    assert goes.history_at("a", t)[1:] == (11, 22)
    assert goes.history_at("c", t + dt.timedelta(hours=3)) is None
