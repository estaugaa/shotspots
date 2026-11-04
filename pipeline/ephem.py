"""Positions from Skyfield + JPL DE440s (MODELED, sub-arcminute).

Geocentric apparent RA/Dec are computed once per time array; per-spot alt/az then come from
fast spherical trig with Greenwich apparent sidereal time, plus lunar parallax. verify.py checks
these against JPL Horizons and USNO.
"""
import math
import numpy as np
from .common import CACHE

_ts = _eph = None
OBJ = {  # J2000 RA/Dec (deg)
    "mwcore": (266.405, -28.936),     # Sgr A*, centre of the Milky Way core
    "cygnus": (305.0, 40.0),          # Cygnus star clouds / Northern Cross
    "orion": (83.86, -1.2),           # Orion's Belt (Alnilam)
    "pleiades": (56.75, 24.12),
    "andromeda": (10.68, 41.27),
    "polaris": (37.95, 89.26),
}
OBJ_NAME = {"sun": "Sun", "moon": "Moon", "mwcore": "Milky Way core", "cygnus": "Cygnus Milky Way", "orion": "Orion", "pleiades": "the Pleiades", "andromeda": "the Andromeda Galaxy"}


def load():
    global _ts, _eph
    if _ts is None:
        from skyfield.api import Loader
        ld = Loader(str(CACHE / "skyfield"))
        _ts = ld.timescale()
        _eph = ld("de440s.bsp")
    return _ts, _eph


def times_utc(t0_unix, t1_unix, step_s):
    ts, _ = load()
    u = np.arange(t0_unix, t1_unix, step_s, dtype=np.float64)
    return u, ts.utc(1970, 1, 1, 0, 0, u)


def radec(body, t):
    """Apparent geocentric RA/Dec (deg, of date) and distance (km) for 'sun','moon', planets or fixed OBJ keys."""
    ts, eph = load()
    earth = eph["earth"]
    if body in OBJ:
        from skyfield.api import Star
        ra, dec = OBJ[body]
        st = Star(ra_hours=ra / 15.0, dec_degrees=dec)
        a = earth.at(t).observe(st).apparent()
        r_, d_, _ = a.radec(epoch="date")
        return r_.hours * 15.0, d_.degrees, None
    key = {"sun": "sun", "moon": "moon", "venus": "venus", "mars": "mars barycenter", "jupiter": "jupiter barycenter", "saturn": "saturn barycenter", "mercury": "mercury"}[body]
    a = earth.at(t).observe(eph[key]).apparent()
    r_, d_, dist = a.radec(epoch="date")
    return r_.hours * 15.0, d_.degrees, dist.km


def gast_deg(t):
    return (t.gast * 15.0) % 360.0


def altaz(ra, dec, gast, lat, lon, dist_km=None):
    """Vectorised alt/az (deg). Applies topocentric parallax for the moon when dist_km given."""
    H = np.radians((gast + lon - ra) % 360.0)
    d = np.radians(dec)
    p = math.radians(lat)
    sin_alt = np.sin(p) * np.sin(d) + math.cos(p) * np.cos(d) * np.cos(H)
    alt = np.degrees(np.arcsin(np.clip(sin_alt, -1, 1)))
    az = (np.degrees(np.arctan2(-np.sin(H) * np.cos(d), math.cos(p) * np.sin(d) - math.sin(p) * np.cos(d) * np.cos(H))) + 360) % 360
    if dist_km is not None:
        alt = alt - np.degrees(np.arcsin(6378.0 / np.asarray(dist_km) * np.cos(np.radians(alt))))
    return alt, az


def refract(alt):
    """Bennett refraction (deg) added to a geometric altitude."""
    a = np.asarray(alt, dtype=float)
    rr = 1.02 / np.tan(np.radians(a + 10.3 / (a + 5.11))) / 60.0
    return np.where(a > -2, a + rr, a)


def moon_illum(t):
    _, eph = load()
    from skyfield import almanac
    return almanac.fraction_illuminated(eph, "moon", t)
