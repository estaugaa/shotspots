"""Start daily jobs that are due. GitHub's own cron drops and delays runs (Nov 17: the 3:23 AM nightly check never
ran; job.yml's three daily schedules fired once a day, hours late), while "GOES fog now" runs every ~30 minutes, so
this runs after it and dispatches whatever is due and hasn't run since its due time. Each job's last run is read from
its own record in the repo."""
import json, os, subprocess, datetime as dt
NOW = dt.datetime.now(dt.timezone.utc)
# name, due hour (UTC), how to tell when it last ran, how to start it
JOBS = [
    ("nightly check", 11, ("history", "data/test_history.jsonl"), ["regress.yml"]),
    ("fog chance", 3, ("status", "fogprob"), ["job.yml", "-f", "job=fogprob"]),
    ("walking routes", 10, ("status", "deeproutes"), ["job.yml", "-f", "job=deeproutes"]),
    ("forecast check", 20, ("status", "skill"), ["job.yml", "-f", "job=skill"]),
]
def last_run(kind, ref):
    try:
        if kind == "history":
            line = open(ref).read().strip().splitlines()[-1]; return dt.datetime.fromisoformat(json.loads(line)["at"])
        return dt.datetime.fromisoformat(json.load(open(f"feed/status/{ref}.json"))["at"].replace("Z", "+00:00"))
    except Exception:
        return None
for name, hour, (kind, ref), cmd in JOBS:
    due = NOW.replace(hour=hour, minute=0, second=0, microsecond=0)
    if due > NOW: due -= dt.timedelta(days=1)
    last = last_run(kind, ref)
    if last is None or last < due:
        # skip if a run for this job has already been started since it fell due (job.yml runs are named "job: <name>")
        title = "job: " + cmd[-1].split("=")[1] if cmd[0] == "job.yml" else None
        runs = json.loads(subprocess.run(["gh", "run", "list", "-w", cmd[0], "--json", "displayTitle,createdAt,status", "-L", "30"], capture_output=True, text=True).stdout or "[]")
        started = [r for r in runs if (title is None or r["displayTitle"] == title) and dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) > due]
        if started: print(f"{name}: due, already started {started[0]['createdAt']} ({started[0]['status']})"); continue
        print(f"{name}: due since {due:%m-%d %H:%M}Z, last ran {last}; starting"); subprocess.run(["gh", "workflow", "run", *cmd], check=False)
    else:
        print(f"{name}: ran {last:%m-%d %H:%M}Z, next due {(due + dt.timedelta(days=1)):%m-%d %H:%M}Z")
