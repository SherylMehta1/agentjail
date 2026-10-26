import json
import sys

path, case_id = sys.argv[1], sys.argv[2]
for line in open(path, encoding="utf-8"):
    r = json.loads(line)
    if r["case"] != case_id:
        continue
    print("=" * 60)
    print(f"run {r['run']}  success={r['success']}")
    for c in r["calls"]:
        print(f"  {c['tool']}  {c['args']}")
    print("  ANSWER:", r["answer"][:300])