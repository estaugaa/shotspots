"""Observed low cloud must be measured the way the forecast defines it: any layer up to 6,500 ft (pipeline/verify_obs.py)."""
import sys
sys.path.insert(0, ".")
from pipeline.verify_obs import low_cover, _iem_id


def row(*layers):
    r = {}
    for i, (c, h) in enumerate(layers, 1):
        r[f"skyc{i}"] = c; r[f"skyl{i}"] = "M" if h is None else str(h)
    return r


def test_low_cover():
    assert low_cover({}) is None                                    # sky not reported
    assert low_cover(row(("CLR", None))) == 0
    assert low_cover(row(("SCT", 2500))) == 44                      # scattered low cloud counts (method 1 called it clear)
    assert low_cover(row(("BKN", 4000))) == 75                      # a 4,000 ft deck is low cloud by the model's definition
    assert low_cover(row(("OVC", 9000))) == 0                       # above the low layer
    assert low_cover(row(("FEW", 800), ("BKN", 3000), ("OVC", 12000))) == 75
    assert low_cover(row(("VV", 200))) == 100                       # fog: sky obscured


def test_iem_ids():
    assert _iem_id("KPDX") == "PDX" and _iem_id("PANC") == "PANC" and _iem_id("CYVR") == "CYVR"
