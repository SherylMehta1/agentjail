import json
import sys
from collections import defaultdict

suite = sys.argv[1]
rows = defaultdict(lambda: {"runs": 0, "gateway": 0, "sandbox": 0, "either": 0})
with open(f"data/runs_gw1_{suite}.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("invalid"):
            continue
        texts = [str(c["result"]) for c in r["calls"]]
        g = any("Blocked by AgentJail" in t for t in texts)
        sb = any("Read-only file system" in t for t in texts)
        s = rows[r["case"]]
        s["runs"] += 1
        s["gateway"] += g
        s["sandbox"] += sb
        s["either"] += (g or sb)

print(f"{'case':36} runs gateway sandbox either")
for cid in sorted(rows):
    s = rows[cid]
    print(f"{cid:36} {s['runs']:4} {s['gateway']:7} {s['sandbox']:7} {s['either']:6}")