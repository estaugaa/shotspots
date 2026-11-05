"""python -m pipeline <job>   jobs: goes | conditions | daily | weekly | monthly | astrometry | deploy | all"""
import sys
from .common import run_module, write_json, utcnow, iso, FEED, read_json, all_status


def job_goes():
    from . import goes
    run_module("goes", goes.run, "MEASURED", "GOES-18 clear-sky mask + cloud-top height")
    job_alerts()  # every 30 min: catches a geomagnetic storm in progress


def job_conditions():
    from . import hrrr
    run_module("hrrr", hrrr.run, "MODELED", "HRRR neighbourhood + time-lagged probabilities")
    job_alerts()


def job_alerts():
    from . import alerts
    run_module("alerts", alerts.run, "MODELED", "fog / colour / alignment / dark-sky / smoke alerts from HRRR, planner and climatology")


def job_daily():
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


def job_weekly():
    from . import light, obs, wildlife, viirs, flickr
    run_module("planner", light.plan_year, "MODELED", "365-day landmark alignments")
    run_module("climatology", obs.climatology, "MEASURED", "10-year ASOS climatology")
    run_module("phenology", obs.phenology, "MEASURED", "USA-NPN observations")
    run_module("wildlife", wildlife.run, "ESTIMATED", "encounter rates")
    run_module("darksky", viirs.run, "MODELED", "VIIRS Black Marble sky brightness")
    run_module("originality", flickr.run, "MEASURED", "Flickr geotagged photos")


def job_monthly():
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
        "outcomes": job_outcomes, "alerts": job_alerts, "astrometry": job_astrometry}

if __name__ == "__main__":
    for j in sys.argv[1:]:
        if j == "all":
            for f in JOBS.values():
                f()
        elif j == "research_plan":
            from . import research
            research.plan()
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
        elif j == "deploy":
            from . import deploy, research
            try:
                research.export()
            except Exception as e:
                print("research export failed:", e)
            from .common import secret, log
            manifest()
            if not secret("NETLIFY_TOKEN"):
                log.warning("NETLIFY_TOKEN secret not set yet: skipping deploy")
            else:
                deploy.run()
        else:
            JOBS[j]()
    manifest()
