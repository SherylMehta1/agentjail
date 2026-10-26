import argparse
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import agent
from agent import DailyQuotaExceeded, MODEL, run_agent
from attacks import ATTACKS
from benign import BENIGN
from harness import evaluate, plant
from sandbox import docker_ready

SUITES = {"attacks": ATTACKS, "benign": BENIGN}

parser = argparse.ArgumentParser()
parser.add_argument("suite", choices=SUITES)
parser.add_argument("--runs", type=int, default=5)
parser.add_argument("--only", default="", help="only cases whose id starts with this")
parser.add_argument("--label", default="baseline", help="name of this configuration")
parser.add_argument("--resume", action="store_true",
                    help="skip runs already saved for this label and suite")
args = parser.parse_args()

if not docker_ready():
    raise SystemExit("Docker is not running. Open Docker Desktop and wait for 'Engine running'.")

cases = [c for c in SUITES[args.suite] if c["id"].startswith(args.only)]
if not cases:
    raise SystemExit("No cases match --only " + args.only)

Path("data").mkdir(exist_ok=True)
runs_file = Path("data") / f"runs_{args.label}_{args.suite}.jsonl"
is_attack = args.suite == "attacks"

done = Counter()  # valid runs already saved, per case
if args.resume and runs_file.exists():
    with open(runs_file, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if not r.get("invalid"):
                done[r["case"]] += 1

with open(runs_file, "a", encoding="utf-8") as log:
    for case in cases:
        for i in range(done[case["id"]], args.runs):
            answer = None
            for attempt in range(3):
                try:
                    plant(case)
                    agent.CALLS.clear()
                    answer = run_agent(case["task"])
                    break
                except DailyQuotaExceeded as e:
                    print("\nDAILY QUOTA EXHAUSTED: stopping. Finished runs are saved.")
                    print("Continue later with the same command plus --resume.")
                    print(str(e)[:300])
                    raise SystemExit(1)
                except Exception as e:
                    print(f"  error (attempt {attempt + 1}/3): {str(e)[:120]}")
                    time.sleep(10)

            if answer is None:  # all 3 attempts crashed: invalid, not a failure
                print(f"{case['id']} run {i + 1}/{args.runs}: INVALID (not counted)")
                log.write(json.dumps({
                    "time": datetime.now().astimezone().isoformat(),
                    "label": args.label, "suite": args.suite, "model": MODEL,
                    "case": case["id"], "category": case["category"],
                    "channel": case.get("channel", "-"),
                    "run": i + 1, "invalid": True,
                }) + "\n")
                log.flush()
                continue

            ok = evaluate(case["success"], answer)
            word = ("ATTACK SUCCEEDED" if ok else "attack failed") if is_attack \
                else ("PASS" if ok else "FAIL")
            print(f"{case['id']} run {i + 1}/{args.runs}: {word}")
            log.write(json.dumps({
                "time": datetime.now().astimezone().isoformat(),
                "label": args.label, "suite": args.suite, "model": MODEL,
                "case": case["id"], "category": case["category"],
                "channel": case.get("channel", "-"),
                "run": i + 1, "success": ok,
                "answer": (answer or "")[:1000],
                "calls": list(agent.CALLS),
            }, default=str) + "\n")
            log.flush()
            time.sleep(2)

print(f"\nDone. Build the report with: python make_report.py {args.label} {args.suite}")