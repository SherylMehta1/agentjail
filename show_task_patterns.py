import json
from collections import Counter, defaultdict

patterns = defaultdict(Counter)
with open("data/runs_baseline_benign.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("invalid"):
            continue
        steps = []
        for c in r["calls"]:
            if c["tool"] == "run_shell":
                words = c["args"].get("command", "").split()
                steps.append("shell:" + (words[0] if words else "?"))
            else:
                steps.append(c["tool"])
        patterns[r["case"]][" > ".join(steps)] += 1

for case in sorted(patterns):
    print(case)
    for seq, n in patterns[case].most_common(3):
        print(f"   {n}x  {seq}")