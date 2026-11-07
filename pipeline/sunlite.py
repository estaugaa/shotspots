"""Small NOAA-style sunrise/sunset calculator (±1–2 min), for jobs that need sun times at many places quickly."""
import math, datetime as dt


def sun_times(lat, lon, day):
    """UTC sunrise and sunset datetimes for a date (dt.date). None for polar day/night."""
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = 0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g)
    la = math.radians(lat)
    c = (math.cos(math.radians(90.833)) / (math.cos(la) * math.cos(decl))) - math.tan(la) * math.tan(decl)
    if abs(c) > 1:
        return None, None
    ha = math.degrees(math.acos(c))
    base = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc)
    rise = base + dt.timedelta(minutes=720 - 4 * (lon + ha) - eq)
    sett = base + dt.timedelta(minutes=720 - 4 * (lon - ha) - eq)
    return rise, sett


STATE_TZ = {"WA": "America/Los_Angeles", "OR": "America/Los_Angeles", "CA": "America/Los_Angeles", "NV": "America/Los_Angeles",
            "MT": "America/Denver", "WY": "America/Denver", "CO": "America/Denver", "UT": "America/Denver", "NM": "America/Denver", "AZ": "America/Phoenix"}


def tz_for(s):
    st = s.get("state")
    if st == "ID":
        return "America/Los_Angeles" if s["lat"] > 45.5 else "America/Boise"
    return STATE_TZ.get(st, "America/Los_Angeles")
