"""python -m pipeline <job>   jobs: goes | conditions | daily | weekly | monthly | astrometry | build_site | all"""
import sys
from .common import run_module, write_json, utcnow, iso, FEED, read_json, all_status


def job_goes():
    from . import goes
    run_module("goes", goes.run, "MEASURED", "GOES-18 clear-sky mask + cloud-top height")
    from . import metar
    run_module("obs", metar.run, "MEASURED", "airport weather reports: visibility, fog, cloud base")
    from . import natdata
    run_module("nwsfog", natdata.nws_fog, "MEASURED", "NWS dense/freezing fog advisories with zone outlines")
    job_alerts()  # every 30 min: catches a geomagnetic storm in progress
    from . import reports
    run_module("reports", reports.run, "MEASURED", "conditions photos from the in-app camera (last 48 h)")


def job_conditions():
    from . import fogabove
    run_module("fogabove", fogabove.run, "MODELED", "viewpoints above forecast fog at sunrise (pressure-level cloud + terrain)")
    from . import birds
    run_module("birds", birds.run, "MEASURED", "iNaturalist notable bird sightings (rare here, first of season, targets)")
    from . import hrrr
    run_module("hrrr", hrrr.run, "MODELED", "HRRR neighbourhood + time-lagged probabilities")
    job_alerts()
    job_weekend()


def job_alerts():
    from . import alerts
    run_module("alerts", alerts.run, "MODELED", "fog / colour / alignment / dark-sky / smoke alerts from HRRR, planner and climatology")


def job_weekend():
    from . import weekend
    run_module("weekend", weekend.run, "MODELED", "weekend plan: alert rules over 4 days (HRRR, then Open-Meteo), wildlife peaks, satellite colour")


def job_daily():
    job_verifyobs()
    from . import viirs
    run_module("darkgrid", viirs.national, "MODELED", "VIIRS national sky-brightness grid (skips while fresh; retries daily if NASA's server was down)")
    from . import terrain, light, obs, sentinel, access, wildlife
    run_module("terrain", lambda: terrain.run(budget_min=25), "MODELED", "USGS 3DEP horizons")
    run_module("light", light.daily, "MODELED", "terrain-aware sun/moon/Milky Way, 14 days")
    run_module("sounding", obs.sounding, "MEASURED", "Salem radiosonde")
    run_module("flow", obs.flow, "MEASURED", "USGS discharge vs daily percentiles")
    run_module("sentinel", sentinel.run, "ESTIMATED", "Sentinel-2 colour/snow vs summer baseline")
    run_module("access", access.run, "MEASURED", "PAD-US land status + USFS alerts")
    run_module("fish", lambda: (wildlife.fish() and "ok"), "MEASURED", "DART Bonneville counts")
    from . import snow
    run_module("snow", snow.run, "MEASURED", "SNOTEL snow depth + researched seasonal road/permit rules")
    job_alerts()


def job_flickr_top():
    from . import flickr
    run_module("photos", flickr.top_photos, "MEASURED", "Flickr most-interesting photos per spot")


def job_photostats():
    from . import photostats
    run_module("photostats", photostats.run, "MEASURED", "best light and months learned from Commons photo times")


def job_verifyobs():
    from . import verify_obs
    run_module("verify_obs", verify_obs.run, "MEASURED", "forecast scored against airport reports at sunrise/sunset")


def job_weekly():
    job_flickr_top()
    job_photostats()
    from . import light, obs, wildlife, viirs, flickr
    run_module("planner", light.plan_year, "MODELED", "365-day landmark alignments")
    run_module("climatology", obs.climatology, "MEASURED", "10-year ASOS climatology")
    run_module("phenology", obs.phenology, "MEASURED", "USA-NPN observations")
    run_module("wildlife", wildlife.run, "ESTIMATED", "encounter rates")
    run_module("darksky", viirs.run, "MODELED", "VIIRS Black Marble sky brightness")
    run_module("darkgrid", viirs.national, "MODELED", "VIIRS national sky-brightness grid (annual)")
    run_module("originality", flickr.run, "MEASURED", "Flickr geotagged photos")


def job_trails():
    from . import trails
    run_module("trails", lambda: trails.run(budget_min=300), "MEASURED", "OpenStreetMap walking route from parking + DEM climb")


def job_seedlight():
    from . import seedlight
    run_module("seedlight", lambda: seedlight.run(budget_min=300), "MODELED", "terrain facing for starter spots (USGS 3DEP)")


def job_gonowtest():
    """Dry run of go-now alerts for sample places (nothing is sent): logs what each would get right now and over the next day."""
    import datetime as dt
    from . import gonow
    from .common import utcnow
    places = {"Seattle": (47.61, -122.33), "Denver": (39.74, -104.99), "Moab": (38.57, -109.55), "Bend": (44.06, -121.31), "Sedona": (34.87, -111.76), "Spokane": (47.66, -117.43)}
    out = []
    for name, (la, lo) in places.items():
        sub = {"lat": la, "lon": lo, "travel": "drive", "limit": 60, "kinds": ["color", "dark"], "utc_offset": -7 * 3600 if lo > -115 else -8 * 3600}
        for h in range(0, 30, 2):   # step through the next 30 hours as if the job ran then (forecast is current)
            t = utcnow() + dt.timedelta(hours=h)
            c = gonow.color_alerts(sub, t) if True else []
            lh = (t + dt.timedelta(seconds=sub["utc_offset"])).hour
            d = gonow.dark_alerts(sub, t, lh)
            for a in c + d:
                out.append(f"{name} @+{h}h: {a['title']} | {a['body']}")
    print("\n".join(out) or "no alerts would fire for the sample places in the next 30 h")
    return f"{len(out)} would-be alerts"


def job_seedpop():
    from . import seedpop
    run_module("seedpop", lambda: seedpop.run(budget_min=300), "MEASURED", "starter-spot popularity: Commons, Flickr, iNaturalist")


def job_hours():
    from . import hours
    run_module("hours", hours.run, "MEASURED", "opening hours from OpenStreetMap (researched + starter spots)")


def job_darkgrid():
    from . import viirs
    run_module("darkgrid", lambda: viirs.national(force=True), "MODELED", "VIIRS national sky-brightness grid (annual)")


def job_natdata():
    from . import natdata
    run_module("tidestations", natdata.tide_stations, "MEASURED", "NOAA CO-OPS tide-prediction stations")
    run_module("nwsfog", natdata.nws_fog, "MEASURED", "NWS dense/freezing fog advisories with zone outlines")


def job_monthly():
    job_natdata()
    from . import verify
    run_module("verify_positions", verify.positions, "MEASURED", "JPL Horizons + USNO")
    run_module("verify_outcomes", verify.outcomes, "MEASURED", "outing logs vs independent observations")


def job_outcomes():
    from . import verify
    run_module("verify_outcomes", verify.outcomes, "MEASURED", "outing logs vs independent observations")


def job_astrometry():
    from . import verify
    run_module("astrometry", verify.astrometry, "MEASURED", "nova.astrometry.net plate solving")


def manifest():
    st = all_status()
    files = sorted(p.name for p in FEED.glob("*.json") if p.name not in ("manifest.json", "status.json"))
    write_json("manifest.json", {"gen": iso(utcnow()), "files": files, "status": st})


JOBS = {"goes": job_goes, "conditions": job_conditions, "daily": job_daily, "weekly": job_weekly, "monthly": job_monthly,
        "outcomes": job_outcomes, "alerts": job_alerts, "weekend": job_weekend, "trails": job_trails, "astrometry": job_astrometry, "photostats": job_photostats, "verifyobs": job_verifyobs, "natdata": job_natdata, "darkgrid": job_darkgrid, "seedlight": job_seedlight, "gonowtest": job_gonowtest, "seedpop": job_seedpop, "hours": job_hours}

if __name__ == "__main__":
    for j in sys.argv[1:]:
        if j == "all":
            for f in JOBS.values():
                f()
        elif j == "research_plan":
            from . import research
            research.plan()
            sys.exit(0)
        elif j == "seed":
            from . import seed
            run_module("seed", lambda: seed.run([x for x in sys.argv[2:] if x] or ["WA", "OR"]), "MODELED", "OpenStreetMap + Wikidata starter spots")
            manifest()
            sys.exit(0)
        elif j == "research_add":
            from . import research
            research.add(sys.argv[2])
            research.export()
            sys.exit(0)
        elif j == "research_import":
            import json as _j
            from . import research
            print(research.ingest(_j.load(open(sys.argv[2]))))
            research.export()
            sys.exit(0)
        elif j == "research_sync":
            from . import research
            run_module("research_sync", research.sync, "MEASURED", "requests and limits from the app")
        elif j in ("deploy", "build_site"):
            from . import deploy, research
            try:
                research.export()
            except Exception as e:
                print("research export failed:", e)
            manifest()
            print(deploy.build_site())
        else:
            JOBS[j]()
    manifest()
