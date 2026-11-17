"""Wildlife as probability.

Best source (MEASURED, effort-corrected): the eBird Basic Dataset. If EBD_URL points at your downloaded
EBD + sampling-event zip, we compute detection frequency = complete checklists within RADIUS_KM of a spot that
reported the species / all complete checklists there, by week and by 3-hour time block. That is a true
encounter rate for a birder standing there.

Fallback (ESTIMATED, presence-only): GBIF occurrences (includes eBird EOD and iNaturalist research grade)
within RADIUS_KM, as the species' share of all records that month. Not effort-corrected: popular, easy-to-see
species are over-represented, and a flock of thousands counts the same as one bird.

Accuracy over coverage (Nov 2026 audit):
* A tight circle (default 0.75 km, per-spot "wl_km" override) so a spot doesn't borrow birds from a
  different habitat nearby. The old ~3 km box gave Hathaway Park the Columbia River's cormorants and scaup.
* Every species is counted in every month (no per-month top-N cut), so a zero means no records, not
  "fell out of that month's top 40".
* Months with too few records are unknown (null), not zero; spots with too few records get no list.
* "wl": false in a spot's config suppresses the list where records near the pin don't describe the
  attraction (a crane-festival town centre, a swift roost on a residential street).

Also: daily Bonneville fish-ladder counts (Columbia Basin Research DART).
"""
import csv, io, json, zipfile, datetime as dt, math, re
import numpy as np
from zoneinfo import ZoneInfo
from .common import soft_fail, http, spots, write_json, read_json, CACHE, log, utcnow, iso, r, km, secret

LA = ZoneInfo("America/Los_Angeles")
GBIF = "https://api.gbif.org/v1/occurrence/search"
LIFE = {"birds", "wildlife"}
RADIUS_KM = 0.75      # default search radius around a spot
MIN_TOTAL = 150       # records in 10 years before a spot gets a species list
MIN_MONTH = 12        # records in a calendar month (all years) before that month's shares are shown
MIN_SPECIES = 8       # records of a species before it's listed


def radius(s):
    return float(s.get("wl_km") or RADIUS_KM)


def life_spots():
    return [s for s in spots() if set(s["cats"]) & LIFE and s.get("wl", True) is not False]


def week_of(date_str):
    try:
        d = dt.date.fromisoformat(date_str[:10])
    except Exception as e:
        soft_fail("wildlife: bad date", e)
        return None
    return min(51, (d.timetuple().tm_yday - 1) // 7)


def hour_of(ed):
    m = re.search(r"T(\d\d):(\d\d)", ed)
    if not m:
        return None
    h = int(m.group(1))
    # GBIF eventDate times are usually local for iNat/eBird; treat as local
    return h


_names = {}


def _name(key):
    """English name: GBIF's preferred vernacular name for the species, else the scientific name."""
    if key not in _names:
        try:
            j = http(f"https://api.gbif.org/v1/species/{key}").json()
            v = j.get("vernacularName")
            _names[key] = v if v else (j.get("canonicalName") or str(key))
        except Exception:
            _names[key] = str(key)
    return _names[key]


def gbif_profiles():
    """Monthly species shares from GBIF facets (no record cap, every year 10 years back), interpolated to weeks."""
    out = {}
    y1 = utcnow().year
    for s in life_spots():
        rk = radius(s)
        base = {"geoDistance": f'{s["lat"]},{s["lon"]},{int(rk * 1000)}m', "year": f"{y1-10},{y1}",
                "classKey": [212, 359], "occurrenceStatus": "PRESENT", "hasCoordinate": "true", "hasGeospatialIssue": "false", "limit": 0}
        try:
            tot = np.zeros(12)
            cnt = {}
            for m in range(1, 13):
                j = http(GBIF, params={**base, "month": m, "facet": "speciesKey", "facetLimit": 1000}).json()
                tot[m - 1] = j.get("count", 0)
                for f in (j.get("facets") or [{}])[0].get("counts", []):
                    cnt.setdefault(int(f["name"]), np.zeros(12))[m - 1] = f["count"]
        except Exception as e:
            log.warning("gbif %s: %s", s["id"], e)
            continue
        if tot.sum() < MIN_TOTAL:
            continue
        ok = tot >= MIN_MONTH
        top = [k for k in sorted(cnt, key=lambda k: -cnt[k].sum()) if cnt[k].sum() >= MIN_SPECIES][:30]
        wk_mid = (np.arange(52) + 0.5) * 7 / 30.44  # week centre in months (0-12)
        xs = np.arange(-0.5, 13.0, 1.0)
        okx = np.r_[ok[-1], ok, ok[0]]
        rows = []
        for k in top:
            share = np.where(ok, cnt[k] / np.where(tot > 0, tot, 1), np.nan)
            ext = np.r_[share[-1], share, share[0]]
            wk = np.interp(wk_mid, xs, np.nan_to_num(ext))
            # a week is known only if both months it is interpolated between are known
            lo = np.clip(np.floor(wk_mid + 0.5).astype(int), 0, 13)
            hi = np.clip(lo + 1, 0, 13)
            known = okx[lo] & okx[hi]
            peak = float(np.nanmax(share)) if np.any(ok) else 0
            if peak <= 0:
                continue
            rows.append({"sp": _name(k), "n": int(cnt[k].sum()),
                         "wk": [int(round(x * 100)) if kn else None for x, kn in zip(wk, known)],
                         "rel": [round(float(x) / peak, 2) if kn else None for x, kn in zip(wk, known)], "hr": None})
        out[s["id"]] = {"n": int(tot.sum()), "r": rk, "kind": "presence-only share of records (GBIF: eBird EOD + iNaturalist)", "species": rows}
    return out


def ebd_profiles(url):
    """Effort-corrected detection frequency from an EBD custom download (zip with ebd_*.txt and ebd_sampling_*.txt)."""
    import pandas as pd
    p = CACHE / "ebd.zip"
    if not p.exists():
        with http(url, stream=True, timeout=600) as resp, open(p, "wb") as f:
            for ch in resp.iter_content(1 << 20):
                f.write(ch)
    z = zipfile.ZipFile(p)
    obs_name = next(n for n in z.namelist() if re.search(r"ebd_.*\.txt$", n) and "sampling" not in n)
    smp_name = next(n for n in z.namelist() if "sampling" in n and n.endswith(".txt"))
    ss = life_spots()
    rad = np.array([radius(s) for s in ss])
    lat = np.array([s["lat"] for s in ss]); lon = np.array([s["lon"] for s in ss])
    cols = ["SAMPLING EVENT IDENTIFIER", "LATITUDE", "LONGITUDE", "OBSERVATION DATE", "TIME OBSERVATIONS STARTED", "ALL SPECIES REPORTED", "PROTOCOL TYPE"]
    near = {}
    for ch in pd.read_csv(z.open(smp_name), sep="\t", usecols=cols, chunksize=200000, dtype=str, quoting=3):
        ch = ch[ch["ALL SPECIES REPORTED"] == "1"]
        la = ch["LATITUDE"].astype(float).values; lo = ch["LONGITUDE"].astype(float).values
        for i, s in enumerate(ss):
            dkm = np.hypot((la - lat[i]) * 111.2, (lo - lon[i]) * 111.2 * math.cos(math.radians(lat[i])))
            sel = ch[dkm <= rad[i]]
            for _, row in sel.iterrows():
                near.setdefault(row["SAMPLING EVENT IDENTIFIER"], []).append((s["id"], row["OBSERVATION DATE"], row["TIME OBSERVATIONS STARTED"]))
    chk = {}
    for sid, lst in near.items():
        for spot_id, d, t in lst:
            w = week_of(d)
            hb = int(t[:2]) // 3 if isinstance(t, str) and len(t) >= 2 and t[:2].isdigit() else None
            chk[sid] = chk.get(sid, []) + [(spot_id, w, hb)]
    n_w = {}
    det = {}
    for sid, lst in chk.items():
        for spot_id, w, hb in lst:
            if w is None:
                continue
            n_w.setdefault(spot_id, np.zeros(52))[w] += 1
    for ch in pd.read_csv(z.open(obs_name), sep="\t", usecols=["SAMPLING EVENT IDENTIFIER", "COMMON NAME", "CATEGORY"], chunksize=500000, dtype=str, quoting=3):
        ch = ch[ch["SAMPLING EVENT IDENTIFIER"].isin(chk.keys()) & (ch["CATEGORY"].isin(["species", "issf", "form"]))]
        for _, row in ch.iterrows():
            for spot_id, w, hb in chk[row["SAMPLING EVENT IDENTIFIER"]]:
                if w is None:
                    continue
                a = det.setdefault(spot_id, {}).setdefault(row["COMMON NAME"], np.zeros((52, 9)))
                a[w, 8] += 1
                if hb is not None:
                    a[w, hb] += 1
    out = {}
    for spot_id, sp in det.items():
        nw = n_w.get(spot_id)
        if nw is None or nw.sum() < 20:
            continue
        sm = lambda a: np.convolve(np.r_[a[-2:], a, a[:2]], np.ones(5) / 5, "valid")
        nws = sm(nw)
        rows = []
        for name, a in sorted(sp.items(), key=lambda kv: -kv[1][:, 8].sum())[:40]:
            with np.errstate(invalid="ignore", divide="ignore"):
                f = np.where(nws > 0, sm(a[:, 8]) / nws, 0)
            hr = a[:, :8].sum(0)
            rows.append({"sp": name, "n": int(a[:, 8].sum()), "wk": [int(round(x * 100)) for x in f], "hr": hr.astype(int).tolist() if hr.sum() >= 10 else None})
        rk = next(radius(s) for s in ss if s["id"] == spot_id)
        out[spot_id] = {"n": int(nw.sum()), "r": rk, "kind": f"eBird detection frequency (% of complete checklists within {rk:g} km)", "species": rows}
    return out


def fish():
    """Daily adult counts at Bonneville from DART. URL pattern verified at runtime; failure is reported in status."""
    y = utcnow().year
    url = "https://www.cbr.washington.edu/dart/cs/php/rpt/adult_daily.php"
    params = {"sc": 1, "outputFormat": "csv", "year": y, "proj": "BON", "span": "no", "startdate": "1/1", "enddate": "12/31", "run": ""}
    txt = http(url, params=params, timeout=120).text
    rows = [r_ for r_ in csv.reader(io.StringIO(txt)) if r_]
    hdr = next(i for i, r_ in enumerate(rows) if any("Chinook" in c or "Chin" in c for c in r_))
    H = [c.strip() for c in rows[hdr]]
    data = [dict(zip(H, r_)) for r_ in rows[hdr + 1:] if len(r_) == len(H)]
    keep = [k for k in H if any(x in k for x in ("Chin", "Coho", "Stlhd", "Steel", "Sock", "Lamprey", "Shad", "Date"))]
    last = [{k: d.get(k) for k in keep} for d in data if any((d.get(k) or "").strip() not in ("", "0") for k in keep if "Date" not in k)][-14:]
    return {"site": "Bonneville Dam", "cols": keep, "last14": last}


def run():
    url = secret("EBD_URL")
    prof, kind = {}, "ESTIMATED"
    if url:
        try:
            prof = ebd_profiles(url)
            kind = "MEASURED"
        except Exception as e:
            log.warning("EBD failed, falling back to GBIF: %s", e)
    g = gbif_profiles()
    for k, v in g.items():
        prof.setdefault(k, v)
    fishd = None
    try:
        fishd = fish()
    except Exception as e:
        log.warning("DART fish counts failed: %s", e)
    write_json("wildlife.json", {"gen": iso(utcnow()), "v": 2, "spots": prof, "fish": fishd,
                                 "hawkwatch": "Bonney Butte HawkWatch monitoring is suspended for the 2026 season (hawkwatch.org); historical peak is mid-September to early October."})
    return f"{len(prof)} spots ({'eBird EBD' if kind == 'MEASURED' else 'GBIF presence-only'}); fish={'ok' if fishd else 'unavailable'}"
