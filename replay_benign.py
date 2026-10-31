import json
from collections import defaultdict
from pathlib import Path

import agent
from benign import BENIGN
from gateway.core import Gateway
from gateway.policy import load_policy
from harness import evaluate, plant
from sandbox import docker_ready

if not docker_ready():
    raise SystemExit("Docker is not running. Open Docker Desktop first.")

by_id = {c["id"]: c for c in BENIGN}
gateway = Gateway(load_policy("policies/default.yaml"), agent.TOOL_FUNCS,
                  audit_path="audit_replay.jsonl")

stats = defaultdict(lambda: {"runs": 0, "passed": 0, "blocked": 0, "sandbox": 0})
with open("data/runs_baseline_benign.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("invalid"):
            continue
        case = by_id[r["case"]]
        plant(case)
        s = stats[case["id"]]
        s["runs"] += 1
        for call in r["calls"]:
            text = str(gateway.handle(call["tool"], call["args"]))
            s["blocked"] += "Blocked by AgentJail" in text
            s["sandbox"] += "Read-only file system" in text
        s["passed"] += evaluate(case["success"], r["answer"], patience=1.5)

print(f"{'case':26} runs passed blocked_calls sandbox_blocks")
tot = defaultdict(int)
for cid in sorted(stats):
    s = stats[cid]
    print(f"{cid:26} {s['runs']:4} {s['passed']:6} {s['blocked']:13} {s['sandbox']:14}")
    for k, v in s.items():
        tot[k] += v
print(f"\nReplayed utility: {tot['passed']}/{tot['runs']}  "
      f"false blocks: {tot['blocked']}  sandbox blocks: {tot['sandbox']}")