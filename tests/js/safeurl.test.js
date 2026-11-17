// safeUrl (app/app.js) must keep web/mail/phone/map/relative links and neutralise script URLs. Run: node tests/js/safeurl.test.js
const fs = require("fs"), path = require("path"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "..", "..", "app", "app.js"), "utf8");
const pick = name => { const m = src.match(new RegExp("^const " + name + " = .*$", "m")); assert(m, name + " not found in app.js"); return m[0]; };
const { esc, safeUrl } = new Function(pick("esc") + "\n" + pick("safeUrl") + "\nreturn { esc, safeUrl };")();
const cases = [
  ["https://www.nps.gov/a?b=1&c=2", "https://www.nps.gov/a?b=1&amp;c=2"],
  ["http://example.org", "http://example.org"],
  ["mailto:x@example.org", "mailto:x@example.org"],
  ["tel:+15555550100", "tel:+15555550100"],
  ["feed/reports/a.jpg", "feed/reports/a.jpg"],
  ["#spot=abc", "#spot=abc"],
  ["/shotspots/", "/shotspots/"],
  ["javascript:alert(1)", "#"],
  [" JavaScript:alert(1)", "#"],
  ["data:text/html,<b>x</b>", "#"],
  ["vbscript:x", "#"],
  ['https://x.org/"onmouseover="a', "https://x.org/&quot;onmouseover=&quot;a"],
  [null, ""],
  [undefined, ""],
];
for (const [inp, want] of cases) assert.strictEqual(safeUrl(inp), want, `safeUrl(${JSON.stringify(inp)})`);
console.log(`safeUrl: ${cases.length} cases pass`);
