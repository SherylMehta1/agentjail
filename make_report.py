import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

label, suite = sys.argv[1], sys.argv[2]
path = Path("data") / f"runs_{label}_{suite}.jsonl"
records = [json.loads(line) for line in path.open(encoding="utf-8")]

is_attack = suite == "attacks"
metric = "Attack success" if is_attack else "Task success"
models = sorted({r["model"] for r in records})

cases = {}
for r in records:
    c = cases.setdefault(r["case"], {
        "category": r["category"], "channel": r["channel"],
        "success": 0, "valid": 0, "invalid": 0, "capped": 0})
    if r.get("invalid"):
        c["invalid"] += 1
    else:
        c["valid"] += 1
        c["success"] += bool(r["success"])
        if str(r.get("answer", "")).startswith("Stopped:"):
            c["capped"] += 1

by_cat = defaultdict(lambda: [0, 0])
tot_s = tot_v = tot_i = tot_c = 0
rows = [f"| Case | Category | Channel | {metric} | Invalid | Hit round cap |",
        "|---|---|---|---|---|---|"]
for case_id in sorted(cases):
    c = cases[case_id]
    rows.append(f"| {case_id} | {c['category']} | {c['channel']} "
                f"| {c['success']}/{c['valid']} | {c['invalid']} | {c['capped']} |")
    by_cat[c["category"]][0] += c["success"]
    by_cat[c["category"]][1] += c["valid"]
    tot_s += c["success"]; tot_v += c["valid"]
    tot_i += c["invalid"]; tot_c += c["capped"]

cat_rows = [f"| Category | {metric} |", "|---|---|"]
for cat, (s, v) in sorted(by_cat.items()):
    cat_rows.append(f"| {cat} | {s}/{v} |")

rate = f"{100 * tot_s / tot_v:.0f}%" if tot_v else "n/a"
extra = []
if is_attack:
    for name, lo, hi in (("Original cases 01-20", 1, 20), ("Phase 2b cases 21-29", 21, 29)):
        s = v = 0
        for cid, c in cases.items():
            if lo <= int(cid[:2]) <= hi:
                s += c["success"]; v += c["valid"]
        if v:
            extra.append(f"{name}: {s}/{v}")
report = "\n".join([
    f"# {label} / {suite}",
    f"Model: {', '.join(models)} | Report date: {date.today()}",
    f"**Overall {metric.lower()}: {tot_s}/{tot_v} ({rate})**  "
    f"(invalid runs excluded: {tot_i}; runs that hit the round cap: {tot_c})",
    " | ".join(extra),
    "", *cat_rows, "", *rows, "",
])
Path("reports").mkdir(exist_ok=True)
Path("reports", f"{label}_{suite}.md").write_text(report, encoding="utf-8")
print(report)
if len(models) > 1:
    print("WARNING: more than one model appears in this file. "
          "Do not mix models in one baseline.")