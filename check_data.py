import json
from collections import Counter

per_case = Counter()
with_policy_key = without = 0
times = []
with open("data/runs_baseline_benign.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("invalid"):
            continue
        per_case[r["case"]] += 1
        times.append(r["time"])
        if "policy" in r:
            with_policy_key += 1
        else:
            without += 1

print("records per case:", dict(per_case))
print("records with a 'policy' field (written after the gateway edit):", with_policy_key)
print("records without it (older):", without)
print("first record:", min(times))
print("last record: ", max(times))