import argparse
from pathlib import Path

import agent
from attack_traces import TRACES
from attacks import ATTACKS
from gateway.approvers import make_approver
from gateway.core import Gateway
from gateway.policy import load_policy
from harness import evaluate, plant
from sandbox import docker_ready

parser = argparse.ArgumentParser()
parser.add_argument("--policy", default=None, help="omit to replay with no defense")
parser.add_argument("--approver", default=None, choices=["deny", "allow", "task"])
args = parser.parse_args()

if not docker_ready():
    raise SystemExit("Docker is not running. Open Docker Desktop first.")

gateway = None
if args.policy:
    gateway = Gateway(load_policy(args.policy), agent.TOOL_FUNCS,
                      audit_path="audit_replay.jsonl",
                      approver=make_approver(args.approver) if args.approver else None)

rows, hits, asks = [], 0, 0
for case in ATTACKS:
    plant(case)
    if gateway:
        gateway.start_session(case["task"])
    for name, call_args in TRACES[case["id"][:2]]:
        if gateway:
            gateway.handle(name, call_args)
        else:
            agent.run_direct(name, call_args)
    hit = evaluate(case["success"], "", patience=1.5)
    n_asks = gateway.session["asks"] if gateway else 0
    hits += hit
    asks += n_asks
    rows.append(f"| {case['id']} | {case['category']} | "
                f"{'succeeds' if hit else 'blocked'} | {n_asks} |")
    print(f"{case['id']}: {'ATTACK SUCCEEDS' if hit else 'blocked'} (asked {n_asks}x)")

mode = "nodefense"
if args.policy:
    mode = Path(args.policy).stem + (f"_{args.approver}" if args.approver else "")
report = "\n".join([
    f"# Oracle-attacker replay: {mode}",
    f"Cases where the attack still succeeds: **{hits}/{len(ATTACKS)}**; "
    f"approval prompts: {asks}",
    "", "| Case | Category | Result | Asked |", "|---|---|---|---|", *rows, "",
])
Path("reports").mkdir(exist_ok=True)
Path("reports", f"replay_{mode}.md").write_text(report, encoding="utf-8")
print("\n" + report)