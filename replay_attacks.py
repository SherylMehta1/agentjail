import argparse
from pathlib import Path

import agent
from attack_traces import TRACES
from attacks import ATTACKS
from gateway.core import Gateway
from gateway.policy import load_policy
from harness import evaluate, plant
from sandbox import docker_ready

parser = argparse.ArgumentParser()
parser.add_argument("--policy", default=None, help="omit to replay with no defense")
args = parser.parse_args()

if not docker_ready():
    raise SystemExit("Docker is not running. Open Docker Desktop first.")

gateway = None
if args.policy:
    gateway = Gateway(load_policy(args.policy), agent.TOOL_FUNCS,
                      audit_path="audit_replay.jsonl")

rows, hits = [], 0
for case in ATTACKS:
    plant(case)
    for name, call_args in TRACES[case["id"][:2]]:
        if gateway:
            gateway.handle(name, call_args)
        else:
            agent.run_direct(name, call_args)
    hit = evaluate(case["success"], "", patience=1.5)
    hits += hit
    rows.append(f"| {case['id']} | {case['category']} | {'succeeds' if hit else 'blocked'} |")
    print(f"{case['id']}: {'ATTACK SUCCEEDS' if hit else 'blocked'}")

mode = Path(args.policy).stem if args.policy else "nodefense"
report = "\n".join([
    f"# Oracle-attacker replay: {mode}",
    f"Cases where the attack still succeeds: **{hits}/{len(ATTACKS)}**",
    "", "| Case | Category | Result |", "|---|---|---|", *rows, "",
])
Path("reports").mkdir(exist_ok=True)
Path("reports", f"replay_{mode}.md").write_text(report, encoding="utf-8")
print("\n" + report)