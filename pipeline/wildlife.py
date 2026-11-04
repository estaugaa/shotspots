"""Wildlife as probability.

Best source (MEASURED, effort-corrected): the eBird Basic Dataset. If EBD_URL points at your downloaded
EBD + sampling-event zip, we compute detection frequency = complete checklists within 2 km of a spot that
reported the species / all complete checklists there, by week and by 3-hour time block. That is a true
encounter rate for a birder standing there.

Fallback (ESTIMATED, presence-only): GBIF occurrences (includes eBird EOD and iNaturalist research grade)
within ~1.5 km, as the species' share of all records that week. Not effort-corrected: popular, easy-to-see
species are over-represented.

Also: daily Bonneville fish-ladder counts (Columbia Basin Research DART).
"""
import csv, io, json, zipfile, datetime as dt, math, re
import numpy as np
from zoneinfo import ZoneInfo
from .common import http, spots, write_json, read_json, CACHE, log, utcnow, iso, r, km, secret

LA = ZoneInfo("America/Los_Angeles")
GBIF = "https://api.gbif.org/v1/occurrence/search"
LIFE = {"birds", "wildlife"}


def gbif_spot(s, years=10, cap=3000):
    d = 0.0135
    dl = d / math.cos(math.radians(s["lat"]))
    recs, off = [], 0
    y1 = utcnow().year
    while off < cap:
        j = http(GBIF, params={"decimalLatitude": f'{s["lat"]-d},{s["lat"]+d}', "decimalLongitude": f'{s["lon"]-dl},{s["lon"]+dl}',
                               "year": f"{y1-years},{y1}", "limit": 300, "offset": off, "hasCoordinate": "true",
                               "classKey": [212, 359], "occurrenceStatus": "PRESENT"}).json()
        for o in j.get("results", []):
            sp = o.get("vernacularName") or o.get("species")
            ed = o.get("eventDate") or ""
            if not sp or len(ed) < 10:
                continue
            recs.append((sp, ed))
        off += 300
        if j.get("endOfRecords"):
            break
    return recs


def week_of(date_str):
    try:
        d = dt.date.fromisoformat(date_str[:10])
    except Exception:
        return None
    return min(51, (d.timetuple().tm_yday - 1) // 7)


def hour_of(ed):
    m = re.search(r"T(\d\d):(\d\d)", ed)
    if not m:
        return None
    h = int(m.group(1))
    # GBIF eventDate times are usually local for iNat/eBird; treat as local
    return h


def gbif_profiles():
    out = {}
    for s in spots():
        if not (set(s["cats"]) & LIFE):
            continue
        try:
            recs = gbif_spot(s)
        except Exception as e:
            log.warning("gbif %s: %s", s["id"], e)
            continue
        if len(recs) < 30:
            continue
        tot = np.zeros(52)
        by = {}
        hrs = {}
        for sp, ed in recs:
            w = week_of(ed)
            if w is None:
                continue
            tot[w] += 1
            by.setdefault(sp, np.zeros(52))[w] += 1
            h = hour_of(ed)
            if h is not None:
                hrs.setdefault(sp, np.zeros(8))[h // 3] += 1
        top = sorted(by, key=lambda k: -by[k].sum())[:30]
        sm = lambda a: np.convolve(np.r_[a[-2:], a, a[:2]], np.ones(5) / 5, "valid")
        tots = sm(tot)
        rows = []
        for sp in top:
            with np.errstate(invalid="ignore", divide="ignore"):
                share = np.where(tots > 0, sm(by[sp]) / tots, 0)
            rows.append({"sp": sp, "n": int(by[sp].sum()), "wk": [int(round(x * 100)) for x in share],
                         "hr": hrs[sp].astype(int).tolist() if sp in hrs and hrs[sp].sum() >= 10 else None})
        out[s["id"]] = {"n": len(recs), "kind": "presence-only share of records (GBIF: eBird EOD + iNaturalist)", "species": rows}
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
    ss = [s for s in spots() if set(s["cats"]) & LIFE]
    lat = np.array([s["lat"] for s in ss]); lon = np.array([s["lon"] for s in ss])
    cols = ["SAMPLING EVENT IDENTIFIER", "LATITUDE", "LONGITUDE", "OBSERVATION DATE", "TIME OBSERVATIONS STARTED", "ALL SPECIES REPORTED", "PROTOCOL TYPE"]
    near = {}
    for ch in pd.read_csv(z.open(smp_name), sep="\t", usecols=cols, chunksize=200000, dtype=str, quoting=3):
        ch = ch[ch["ALL SPECIES REPORTED"] == "1"]
        la = ch["LATITUDE"].astype(float).values; lo = ch["LONGITUDE"].astype(float).values
        for i, s in enumerate(ss):
            dkm = np.hypot((la - lat[i]) * 111.2, (lo - lon[i]) * 111.2 * math.cos(math.radians(lat[i])))
            sel = ch[dkm <= 2.0]
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
        out[spot_id] = {"n": int(nw.sum()), "kind": "eBird detection frequency (% of complete checklists within 2 km)", "species": rows}
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
    write_json("wildlife.json", {"gen": iso(utcnow()), "spots": prof, "fish": fishd,
                                 "hawkwatch": "Bonney Butte HawkWatch monitoring is suspended for the 2026 season (hawkwatch.org); historical peak is mid-September to early October."})
    return f"{len(prof)} spots ({'eBird EBD' if kind == 'MEASURED' else 'GBIF presence-only'}); fish={'ok' if fishd else 'unavailable'}"
