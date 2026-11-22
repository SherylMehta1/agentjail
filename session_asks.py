import json
import sys
from collections import defaultdict

label, suite = sys.argv[1], sys.argv[2]
stats = defaultdict(lambda: {"runs": 0, "asks": 0, "tainted": 0})
with open(f"data/runs_{label}_{suite}.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("invalid"):
            continue
        s = r.get("session") or {}
        d = stats[r["case"]]
        d["runs"] += 1
        d["asks"] += s.get("asks", 0)
        d["tainted"] += bool(s.get("tainted"))
for case in sorted(stats):
    d = stats[case]
    print(f"{case:36} runs {d['runs']}  prompts {d['asks']}  tainted runs {d['tainted']}")