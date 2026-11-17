(async () => { const t0 = Date.now(); while (!WX && Date.now() - t0 < 30000) await new Promise(r => setTimeout(r, 500)); await new Promise(r => setTimeout(r, 3000));
  SCORE_MATH = true; render(); await new Promise(r => setTimeout(r, 1500));
  const cards = [...document.querySelectorAll('#v-now .pick')].slice(0, 3).map(c => c.innerText.replace(/\s+/g, " ").slice(0, 200));
  const id = document.querySelector('#v-now .pick') && document.querySelector('#v-now .pick').dataset.spot; openSpot(id); await new Promise(r => setTimeout(r, 2500));
  const m = document.querySelector('#sheetBody .scoremath'); const h3s = [...document.querySelectorAll('#sheetBody h3')].map(h => h.textContent).slice(0, 6);
  return { cards, page: m ? m.innerText.slice(0, 900) : "missing", order: h3s };
})()
