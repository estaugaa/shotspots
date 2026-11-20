"""Historical photo timing from the Wikimedia Commons database dumps (MEASURED), for the validation set: on which
evenings and mornings did people photograph the sky, and in what weather (joined later with historical weather).

Three public dumps of the same date are streamed (~25 GB, never stored); only these facts are kept:
  geo_tags  file page id -> camera location (primary geotag on Earth, inside a box around the US and its states)
  page      page id -> file name (files only, only ids found above)
  image     file name -> EXIF capture time (DateTimeOriginal, camera clock as written), exposure, words in the name
Output data/archive/commons/photos_<dump date>.csv.gz, one row per photo with a capture time:
  lat, lon (4 dp), taken ("YYYY-MM-DD HH:MM", the camera's local clock), ev (scene brightness, EV at ISO 100, from
  shutter/aperture/ISO; blank when missing), words (s sunset/sunrise/dusk/dawn/golden/afterglow/alpenglow, f fog/mist,
  r rainbow, t storm/lightning, w snow, n night sky: aurora/milky way/stars/star trails), who (uploader's account
  number from the dump, so the analysis counts photographers rather than photos: one person's 200 frames of a sunset
  are one vote)
Time zone, country and sun position are worked out later (the analysis step), not here.

Stages are checkpointed in .cache/commons, so a run that runs short of time continues where it stopped (.more).
Only re-done when a newer complete dump exists (Commons dumps monthly; the scheduler asks every 30 days).
The API (photostats.py) is not used: bulk queries there are rate-limited (HTTP 429, Nov 20).
Source: Wikimedia Commons contributors (dumps.wikimedia.org); only place/time facts are kept, no images or text.

    python -m pipeline commonsphotos
"""
import csv, gzip, io, json, math, pickle, re, subprocess, time
from .common import http, soft_fail, log, utcnow, iso, DATA, CACHE

BASE = "https://dumps.wikimedia.org/commonswiki/"
H = {"User-Agent": "ShotSpots/1.0 (https://github.com/estaugaa/shotspots; photo-timing statistics from dumps)"}
OUT = DATA / "archive" / "commons"
CK = CACHE / "commons"
VERSION = 2               # 2: uploader column
BUDGET_MIN = 320          # job.yml allows 340
IMAGE_MIN = 200           # don't start the image pass with less time than this left
# lat/lon boxes: lower 48, Alaska, Hawaii (neighbouring Canada/Mexico is removed later by time zone)
BOXES = [(24.3, 49.5, -125.0, -66.8), (51.0, 71.6, -180.0, -129.9), (18.8, 22.4, -160.6, -154.7)]
WORDS = [("s", rb"sunset|sunrise|dusk|dawn|golden.hour|afterglow|alpenglow"), ("f", rb"fog|mist"), ("r", rb"rainbow"),
         ("t", rb"storm|lightning"), ("w", rb"snow"), ("n", rb"aurora|milky.way|star.?trail|night.sky|starry")]
WORD_RE = [(k, re.compile(p, re.I)) for k, p in WORDS]
GEO_RE = re.compile(rb"^\(\d+,(\d+),'earth',1,(-?\d+\.\d+),(-?\d+\.\d+),")
PAGE_RE = re.compile(rb"^\((\d+),6,'((?:[^'\\]|\\.)*)',")
NAME_RE = re.compile(rb"^\('((?:[^'\\]|\\.)*)',")
ACTOR_RE = re.compile(rb",\d+,(\d+),'\d{14}','[0-9a-z]*'\)[,;]?\s*$")   # img_description_id, img_actor, img_timestamp, img_sha1 end each row
# EXIF is stored as JSON (\"DateTimeOriginal\":\"2015:11:29 16:13:35\") or, in older rows, PHP-serialised
# (s:16:\"DateTimeOriginal\";s:19:\"2013:07:05 21:07:11\"); both are matched
DTO_RE = re.compile(rb'DateTimeOriginal\\"(?::|;s:\d+:)\\"(\d{4}):(\d\d):(\d\d) (\d\d):(\d\d)')
EXP_RE = {k: re.compile(rb'"' + k.encode() + rb'\\"(?::|;[sid]:(?:\d+:)?)\\?"?([\d./]+)') for k in ("ExposureTime", "FNumber", "ISOSpeedRatings")}


def _in_us(la, lo):
    return any(a <= la <= b and c <= lo <= d for a, b, c, d in BOXES)


def latest_dump():
    """Newest dump date whose geo_tags, page and image tables are all finished."""
    dates = sorted(set(re.findall(r'href="(\d{8})/"', http(BASE, headers=H).text)), reverse=True)
    for d in dates[:4]:
        try:
            jobs = http(f"{BASE}{d}/dumpstatus.json", headers=H).json()["jobs"]
            if all(jobs.get(j, {}).get("status") == "done" for j in ("geotagstable", "pagetable", "imagetable")):
                return d
        except Exception as e:
            soft_fail("commonsphotos: dump status", e)
    return None


def _lines(url):
    """The dump's rows, one per line (mysqldump writes one row a line), streamed and unzipped by curl/gzip."""
    p = subprocess.Popen(f"curl -sfL --retry 5 -A '{H['User-Agent']}' '{url}' | gzip -dc", shell=True, stdout=subprocess.PIPE, bufsize=1 << 20)
    try:
        yield from p.stdout
    finally:
        p.stdout.close(); p.wait()
        if p.returncode not in (0, None):
            raise RuntimeError(f"stream ended with code {p.returncode}: {url}")


def _ev(line):
    try:
        v = {k: r.search(line) for k, r in EXP_RE.items()}
        if not all(v.values()):
            return ""
        f = lambda m: (lambda a: float(a[0]) / float(a[1]) if len(a) == 2 else float(a[0]))(m.group(1).decode().split("/"))
        t, n, iso_ = f(v["ExposureTime"]), f(v["FNumber"]), f(v["ISOSpeedRatings"])
        return f"{math.log2(n * n / t) - math.log2(iso_ / 100):.1f}" if t > 0 and n > 0 and iso_ > 0 else ""
    except Exception:
        return ""


def run():
    t0 = time.time(); left = lambda: BUDGET_MIN - (time.time() - t0) / 60
    dump = latest_dump()
    if not dump:
        return "no complete dump found"
    out = OUT / f"photos_{dump}_v{VERSION}.csv.gz"
    if out.exists():
        return f"dump {dump} already done ({out.name})"
    CK.mkdir(parents=True, exist_ok=True)
    url = lambda t: f"{BASE}{dump}/commonswiki-{dump}-{t}.sql.gz"
    # 1-2: file name -> location, for files with a primary geotag in the US boxes
    ckf = CK / f"names_{dump}.pkl.gz"
    if ckf.exists():
        names = pickle.load(gzip.open(ckf, "rb"))
    else:
        geo, n = {}, 0
        for line in _lines(url("geo_tags")):
            m = GEO_RE.match(line)
            if not m:
                continue
            n += 1; la, lo = float(m.group(2)), float(m.group(3))
            if _in_us(la, lo):
                geo[int(m.group(1))] = (round(la, 4), round(lo, 4))
        log.info("commonsphotos: %d primary geotags, %d in the US boxes (%.0f min)", n, len(geo), (time.time() - t0) / 60)
        names = {}
        for line in _lines(url("page")):
            m = PAGE_RE.match(line)
            if m and int(m.group(1)) in geo:
                names[m.group(2)] = geo[int(m.group(1))]
        del geo
        with gzip.open(ckf, "wb", compresslevel=3) as f:
            pickle.dump(names, f, protocol=pickle.HIGHEST_PROTOCOL)
        log.info("commonsphotos: %d US files by name (%.0f min)", len(names), (time.time() - t0) / 60)
    if left() < IMAGE_MIN:
        open(".more", "w").write("1")
        return f"dump {dump}: {len(names)} US geotagged files found; image pass next run"
    # 3: capture times from the image table
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    rows = seen = 0
    with gzip.open(tmp, "wt", newline="") as f:
        w = csv.writer(f); w.writerow(["lat", "lon", "taken", "ev", "words", "who"])
        for line in _lines(url("image")):
            m = NAME_RE.match(line)
            if not m:
                continue
            loc = names.get(m.group(1))
            if loc is None:
                continue
            seen += 1
            d = DTO_RE.search(line)
            if not d:
                continue
            y, mo, da, hh, mi = (int(x) for x in d.groups())
            if not (1990 <= y <= 2030 and 1 <= mo <= 12 and 1 <= da <= 31 and hh < 24 and mi < 60) or (hh == 0 and mi == 0):
                continue   # unset camera clocks and date-only stamps carry no time of day
            nm = m.group(1).replace(b"_", b" ")
            words = "".join(k for k, r in WORD_RE if r.search(nm))
            w.writerow([loc[0], loc[1], f"{y:04d}-{mo:02d}-{da:02d} {hh:02d}:{mi:02d}", _ev(line), words, (lambda a: a.group(1).decode() if a else "")(ACTOR_RE.search(line))]); rows += 1
    tmp.rename(out)
    for p in CK.glob("names_*.pkl.gz"):
        p.unlink()
    json.dump({"dump": dump, "version": VERSION, "file": out.name, "at": iso(utcnow()), "us_geotagged": len(names), "us_files_seen": seen, "with_time": rows},
              open(OUT / "index.json", "w"), indent=1)
    return f"dump {dump}: {rows} US photos with a capture time ({seen} US geotagged files in the image table, {len(names)} names) in {(time.time() - t0) / 60:.0f} min"
