import json
import sys
from collections import defaultdict
from pathlib import Path

src = Path("data/runs_baseline_benign.jsonl")
rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
valid = [r for r in rows if not r.get("invalid")]
invalid = [r for r in rows if r.get("invalid")]

by_case = defaultdict(list)
for r in valid:
    by_case[r["case"]].append(r)

first, second = [], []
for case, rs in by_case.items():
    rs.sort(key=lambda r: r["time"])
    if len(rs) != 10:
        raise SystemExit(f"{case} has {len(rs)} records, expected 10. Nothing changed.")
    first += rs[:5]
    second += rs[5:]


def summary(name, rs):
    times = sorted(r["time"] for r in rs)
    passed = sum(bool(r["success"]) for r in rs)
    capped = sum(r["answer"].startswith("Stopped:") for r in rs)
    b14 = [bool(r["success"]) for r in rs if r["case"] == "b14-missing-file"]
    print(f"{name}: {len(rs)} runs, {passed} passed, {capped} hit the round cap, "
          f"{times[0][:16]} to {times[-1][:16]}")
    print(f"    b14-missing-file: {sum(b14)}/{len(b14)}")


summary("first batch ", first)
summary("second batch", second)
print("invalid records:", len(invalid))

if "--write" in sys.argv:
    Path("data/runs_baseline_rerun_benign.jsonl").write_text(
        "\n".join(json.dumps(r) for r in second) + "\n", encoding="utf-8")
    src.write_text(
        "\n".join(json.dumps(r) for r in first + invalid) + "\n", encoding="utf-8")
    print("Written: baseline keeps the first batch; second batch saved as baseline_rerun.")
else:
    print("Dry run only. Add --write to split the file.")