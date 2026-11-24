"""Prediction evaluation (tools/predeval.py): one prediction per window, current webcam colour measure only."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import predeval   # noqa: E402
from pipeline import archive   # noqa: E402


def test_latest_keeps_last_prediction_before_the_window():
    ps = [{"at": "2026-11-20T02:00:00Z", "w": "2026-11-20T15:00:00Z", "v": 1},
          {"at": "2026-11-20T11:45:00Z", "w": "2026-11-20T15:00:00Z", "v": 2},
          {"at": "2026-11-20T15:30:00Z", "w": "2026-11-20T15:00:00Z", "v": 3}]   # made after the window started: not a forecast
    got = predeval.latest(ps, lambda p: p["w"], lambda p: p["w"])
    assert [p["v"] for p in got] == [2] and got[0]["lead_h"] == 3.2


def test_cam_frames_current_measure_only(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "ROOT", tmp_path)
    f = ["date", "cam", "event", "sky_warm", "sky_blue", "sky_grey", "mv"]
    rows = [{"date": "2026-11-20", "cam": "a", "event": "sunset", "sky_warm": 9, "sky_blue": 30, "sky_grey": 0, "mv": ""},
            {"date": "2026-11-22", "cam": "a", "event": "sunset", "sky_warm": 4, "sky_blue": 30, "sky_grey": 0, "mv": "2"},
            {"date": "2026-11-22", "cam": "b", "event": "sunset", "sky_warm": 4, "sky_blue": 5, "sky_grey": 5, "mv": "2"}]   # no sky
    archive.append("camtruth", f, rows, lambda r: r["date"], lambda r: (r["date"], r["cam"]))
    assert [(r["cam"], r["date"]) for r in predeval.cam_frames("2026-11-01")] == [("a", "2026-11-22")]
