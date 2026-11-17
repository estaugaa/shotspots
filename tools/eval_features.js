(async () => { const t0 = Date.now(); while (!WX && Date.now() - t0 < 30000) await new Promise(r => setTimeout(r, 500)); await new Promise(r => setTimeout(r, 3000));
  const ws = allWindows(LOC, PLAN_HOURS), tom = laYMD(new Date(Date.now() + 864e5)), i = ws.findIndex(w => winDay(w) === tom && w.kind === "sunrise"); UI.focus = i;
  const top = rankFor(ws[i]).slice(0, 3);
  const card = pickRow(top[0], ws[i]).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 160);
  openSpot(top[0].s.id); await new Promise(r => setTimeout(r, 2500));
  const sm = [...document.querySelectorAll('#sheetBody li')].filter(li => li.closest('.layers')).map(li => li.innerText.replace(/\s+/g, ' ').slice(0, 110));
  const base = top.map(x => `${x.f.n} ${x.s.name.slice(0, 28)}`);
  PREFS.fame = "lesser"; if (typeof __skyMemoAt !== "undefined") __skyMemoAt = -1; const lesser = rankFor(ws[i]).slice(0, 3).map(x => `${x.f.n} ${x.s.name.slice(0, 28)} q${x.f.q != null ? x.f.q.toFixed(2) : "-"}`); PREFS.fame = "balanced";
  const unknown = SPOTS.filter(s => !hasRecord(s)).length;
  return { card, layers: sm.slice(0, 10), balancedTop: base, lesserTop: lesser, medianQuality: +medianQuality().toFixed(2), spotsWithNoRecord: unknown, of: SPOTS.length,
    quickLogShownNow: !!quickLogHtml(), hrrrLoaded: !!(HRRR && HRRR.by), calib: !!CALIB };
})()
