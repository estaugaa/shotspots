import sys, datetime as dt
sys.path.insert(0, ".")
from pipeline import climonat
from pipeline.sunlite import sun_times

LAT, LON = 45.62, -121.17   # The Dalles, OR


def row(t, sky, vsby="10.00", wx="M"):
    r = {"valid": t.strftime("%Y-%m-%d %H:%M"), "vsby": vsby, "wxcodes": wx}
    for i in (1, 2, 3):
        c, h = sky[i - 1] if i <= len(sky) else ("M", "M")
        r[f"skyc{i}"], r[f"skyl{i}"] = c, str(h)
    return r


def test_sky_class():
    assert climonat.sky_class(row(dt.datetime(2024, 1, 1), [("CLR", "M")])) == (True, False, False, False)
    assert climonat.sky_class(row(dt.datetime(2024, 1, 1), [("FEW", 2000)])) == (True, False, False, False)
    assert climonat.sky_class(row(dt.datetime(2024, 1, 1), [("SCT", 3000), ("BKN", 5000)])) == (False, True, False, False)
    assert climonat.sky_class(row(dt.datetime(2024, 1, 1), [("BKN", 9000)])) == (False, False, False, False)   # high broken: neither
    assert climonat.sky_class(row(dt.datetime(2024, 1, 1), [("BKN", 900), ("OVC", 3000)])) == (False, False, True, False)
    assert climonat.sky_class(row(dt.datetime(2024, 1, 1), [("VV", 100)], vsby="0.25", wx="FG")) == (False, False, True, True)
    assert climonat.sky_class(row(dt.datetime(2024, 1, 1), [("CLR", "M")], vsby="4.00", wx="BR")) == (True, False, False, True)
    assert climonat.sky_class(row(dt.datetime(2024, 1, 1), [("FEW", 100)], wx="BCFG"))[3] is False   # fog patches don't count
    assert climonat.sky_class(row(dt.datetime(2024, 1, 1), [("M", "M")])) is None


def test_aggregate_picks_closest_report_per_event():
    day = dt.date(2024, 6, 20)
    rise, sett = sun_times(LAT, LON, day)
    rows = [
        row(rise - dt.timedelta(minutes=40), [("OVC", 800)]),   # in the window but farther than the next one
        row(rise + dt.timedelta(minutes=10), [("CLR", "M")]),   # closest to sunrise: counts
        row(rise + dt.timedelta(minutes=120), [("OVC", 800)]),  # outside the window: ignored
        row(sett - dt.timedelta(minutes=30), [("BKN", 4000)], vsby="0.50", wx="FG"),
    ]
    r, s, y0, y1 = climonat.aggregate(rows, LAT, LON)
    w = climonat.week_of(day)
    assert r[w] == [1, 1, 0, 0, 0]
    assert s[w] == [1, 0, 1, 0, 1]
    assert sum(c[0] for c in r) == 1 and sum(c[0] for c in s) == 1
    assert (y0, y1) == (2024, 2024)


def test_aggregate_counts_days_across_years_and_weeks():
    rows = []
    for y in (2017, 2020, 2025):
        for d in (dt.date(y, 1, 3), dt.date(y, 12, 31)):   # week 0 and the folded last week
            rise, sett = sun_times(LAT, LON, d)
            rows += [row(sett + dt.timedelta(minutes=5), [("CLR", "M")]), row(sett + dt.timedelta(minutes=20), [("OVC", 500)])]
    r, s, y0, y1 = climonat.aggregate(rows, LAT, LON)
    assert s[0] == [3, 3, 0, 0, 0] and s[51] == [3, 3, 0, 0, 0]
    assert sum(c[0] for c in r) == 0
    assert (y0, y1) == (2017, 2025)


def test_week_matches_app():
    # app weekIdx: floor(days since Jan 1 / 7), capped at 51
    assert climonat.week_of(dt.date(2025, 1, 1)) == 0
    assert climonat.week_of(dt.date(2025, 1, 8)) == 1
    assert climonat.week_of(dt.date(2024, 12, 31)) == 51


def test_tile_key_matches_seed():
    assert climonat.tile_key(45.6, -121.2) == "45_-122"
    assert climonat.tile_key(19.9, -155.1) == "19_-156"
