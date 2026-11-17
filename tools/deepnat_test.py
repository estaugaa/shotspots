"""Short test run of pipeline/deepnat.py (8 minutes) on Actions: how fast, and what a card looks like."""
import os, sys, json, glob
sys.path.insert(0, os.getcwd())
os.makedirs("ux", exist_ok=True)
from pipeline import deepnat
msg = deepnat.run(budget_min=8)
out = [msg]
for f in sorted(glob.glob("feed/deep/*_*.json"))[:2]:
    j = json.load(open(f)); k, c = next(iter(j["spots"].items())) if j["spots"] else (None, {})
    out.append(f"{f}: {len(j['spots'])} spots; e.g. {k}: light={c.get('light')} eff={c.get('eff')} mi={c.get('mi')} tip={c.get('tip')} hz[90]={c.get('hz', [None]*91)[90]} hz[270]={c.get('hz', [None]*271)[270]}")
open("ux/deepnat.txt", "w").write("\n".join(out)); print("\n".join(out))
