(async () => { const t0 = Date.now(); while (!WX && Date.now() - t0 < 30000) await new Promise(r => setTimeout(r, 500)); await new Promise(r => setTimeout(r, 3000));
  const ws = allWindows(LOC, PLAN_HOURS), tom = laYMD(new Date(Date.now() + 864e5)), i = ws.findIndex(w => winDay(w) === tom && w.kind === "sunrise");
  UI.focus = i; SCORE_MATH = true; const list = rankFor(ws[i]).slice(0, 3);
  const cards = list.map(x => pickRow(x, ws[i]).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 220));
  openSpot(list[0].s.id); await new Promise(r => setTimeout(r, 2500));
  const m = document.querySelector('#sheetBody .scoremath'); const h3s = [...document.querySelectorAll('#sheetBody h3')].map(h => h.textContent).slice(0, 6);
  return { cards, page: m ? m.innerText.slice(0, 900) : "missing", order: h3s };
})()
