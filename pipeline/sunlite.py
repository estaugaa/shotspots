"""Small NOAA-style sunrise/sunset calculator (±1–2 min), for jobs that need sun times at many places quickly."""
import json, math, datetime as dt
from pathlib import Path


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



def sun_az(lat, lon, t):
    """Sun azimuth in degrees from north, clockwise, at UTC datetime t (same NOAA approximation as sun_times)."""
    n = t.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1 + (t.hour - 12) / 24)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = 0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g)
    ha = math.radians((t.hour * 60 + t.minute + t.second / 60 + eq + 4 * lon) / 4 - 180)
    la = math.radians(lat)
    return (math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(la) - math.tan(decl) * math.cos(la))) + 180) % 360

# main time zone per state (fallback; split states are handled by the nearest airport station below)
STATE_TZ = {"WA": "America/Los_Angeles", "OR": "America/Los_Angeles", "CA": "America/Los_Angeles", "NV": "America/Los_Angeles",
            "MT": "America/Denver", "WY": "America/Denver", "CO": "America/Denver", "UT": "America/Denver", "NM": "America/Denver",
            "AZ": "America/Phoenix", "ID": "America/Boise", "AK": "America/Anchorage", "HI": "Pacific/Honolulu",
            "ND": "America/Chicago", "SD": "America/Chicago", "NE": "America/Chicago", "KS": "America/Chicago", "OK": "America/Chicago",
            "TX": "America/Chicago", "MN": "America/Chicago", "IA": "America/Chicago", "MO": "America/Chicago", "AR": "America/Chicago",
            "LA": "America/Chicago", "WI": "America/Chicago", "IL": "America/Chicago", "MS": "America/Chicago", "AL": "America/Chicago",
            "TN": "America/Chicago", "KY": "America/New_York", "IN": "America/Indiana/Indianapolis", "MI": "America/Detroit",
            "OH": "America/New_York", "GA": "America/New_York", "FL": "America/New_York", "SC": "America/New_York",
            "NC": "America/New_York", "VA": "America/New_York", "WV": "America/New_York", "MD": "America/New_York",
            "DE": "America/New_York", "PA": "America/New_York", "NJ": "America/New_York", "NY": "America/New_York",
            "CT": "America/New_York", "RI": "America/New_York", "MA": "America/New_York", "VT": "America/New_York",
            "NH": "America/New_York", "ME": "America/New_York", "DC": "America/New_York"}
_STATIONS = None
_TZC = {}


def _station_tz(lat, lon):
    """Time zone of the nearest US airport station (Iowa Mesonet lists carry tzname; saved by photoweather.py), within
    ~150 km; None when the list isn't there."""
    global _STATIONS
    if _STATIONS is None:
        try:
            import numpy as np
            st = json.load(open(Path(__file__).resolve().parents[1] / "data" / "photoweather" / "stations.json"))
            _STATIONS = (np.array([x[0] for x in st]), np.array([x[1] for x in st]), [x[2] for x in st])
        except Exception:
            _STATIONS = False
    if not _STATIONS:
        return None
    k = (round(lat, 1), round(lon, 1))
    if k not in _TZC:
        import numpy as np
        la, lo, tz = _STATIONS
        d = np.hypot(la - lat, (lo - lon) * math.cos(math.radians(lat))); i = int(d.argmin())
        _TZC[k] = tz[i] if d[i] < 1.4 else None
    return _TZC[k]


def tz_for(s):
    """Local time zone of a spot. Was a 10-state western table defaulting to Pacific time, so every spot east of the
    Rockies had its camera times read 1-3 hours off (Cadillac Mountain sunrise photos fell outside sunrise; Nov 23)."""
    z = _station_tz(s["lat"], s["lon"]) if s.get("lat") is not None else None
    if z:
        return z
    st = s.get("state")
    if st == "ID":
        return "America/Los_Angeles" if s["lat"] > 45.5 else "America/Boise"
    return STATE_TZ.get(st, "America/Los_Angeles")
