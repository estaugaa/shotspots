"""Skipped errors must reach the module's status file, not vanish (pipeline/common.py soft_fail + run_module)."""
import json, sys
sys.path.insert(0, ".")
from pipeline import common


def test_soft_errors_are_counted_in_status(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "FEED", tmp_path)
    (tmp_path / "status").mkdir()

    def job():
        for v in ["1", "x", "y", "2"]:
            try:
                int(v)
            except ValueError as e:
                common.soft_fail("job: bad number", e)
        return "done"

    assert common.run_module("t_soft", job, "MEASURED")
    st = json.loads((tmp_path / "status" / "t_soft.json").read_text())
    assert st["ok"] and st["soft"]["job: bad number"]["n"] == 2
    assert "ValueError" in st["soft"]["job: bad number"]["first"]

    assert common.run_module("t_clean", lambda: "fine", "MEASURED")   # counts start fresh for each module
    assert "soft" not in json.loads((tmp_path / "status" / "t_clean.json").read_text())
