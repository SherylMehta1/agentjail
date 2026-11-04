import argparse
import json
from collections import defaultdict
from pathlib import Path

import agent
from benign import BENIGN
from gateway.approvers import make_approver
from gateway.core import Gateway
from gateway.policy import load_policy
from harness import evaluate, plant
from sandbox import docker_ready

parser = argparse.ArgumentParser()
parser.add_argument("--policy", default="policies/default.yaml")
parser.add_argument("--approver", default=None, choices=["deny", "allow", "task"])
parser.add_argument("--data", default="data/runs_baseline_benign.jsonl")
args = parser.parse_args()

if not docker_ready():
    raise SystemExit("Docker is not running. Open Docker Desktop first.")

by_id = {c["id"]: c for c in BENIGN}
gateway = Gateway(load_policy(args.policy), agent.TOOL_FUNCS,
                  audit_path="audit_replay.jsonl",
                  approver=make_approver(args.approver) if args.approver else None)

stats = defaultdict(lambda: {"runs": 0, "passed": 0, "prompted": 0,
                             "asks": 0, "refused": 0, "blocked": 0})
with open(args.data, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("invalid"):
            continue
        case = by_id[r["case"]]
        plant(case)
        gateway.start_session(case["task"])
        s = stats[case["id"]]
        s["runs"] += 1
        for call in r["calls"]:
            text = str(gateway.handle(call["tool"], call["args"]))
            s["blocked"] += ("Blocked by AgentJail" in text and "human approval" not in text)
        s["asks"] += gateway.session["asks"]
        s["refused"] += gateway.session["refused"]
        s["prompted"] += gateway.session["asks"] > 0
        s["passed"] += evaluate(case["success"], r["answer"], patience=1.5)

lines = [f"{'case':26} runs passed prompted_runs asks refused policy_blocked"]
tot = defaultdict(int)
for cid in sorted(stats):
    s = stats[cid]
    lines.append(f"{cid:26} {s['runs']:4} {s['passed']:6} {s['prompted']:13} "
                 f"{s['asks']:4} {s['refused']:7} {s['blocked']:14}")
    for k, v in s.items():
        tot[k] += v
mode = Path(args.policy).stem + (f"_{args.approver}" if args.approver else "")
summary = (f"Replayed utility: {tot['passed']}/{tot['runs']} | runs with a prompt: "
           f"{tot['prompted']}/{tot['runs']} | prompts: {tot['asks']} "
           f"(refused {tot['refused']}) | policy-blocked calls: {tot['blocked']}")
print("\n".join(lines) + "\n\n" + summary)
Path("reports").mkdir(exist_ok=True)
Path("reports", f"replay_benign_{mode}.md").write_text(
    "```\n" + "\n".join(lines) + "\n```\n\n" + summary + "\n", encoding="utf-8")