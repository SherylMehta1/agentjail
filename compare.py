import json
import sys
from collections import defaultdict


def load(label, suite):
    d = defaultdict(lambda: [0, 0])
    with open(f"data/runs_{label}_{suite}.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("invalid"):
                continue
            d[r["case"]][1] += 1
            d[r["case"]][0] += bool(r["success"])
    return d


suite, a_label, b_label = sys.argv[1:4]
a, b = load(a_label, suite), load(b_label, suite)
print(f"{'case':36} {a_label:>10} {b_label:>10}")
ta = va = tb = vb = 0
for cid in sorted(a):
    sa, na = a[cid]
    sb, nb = b.get(cid, [0, 0])
    print(f"{cid:36} {sa:>5}/{na:<4} {sb:>5}/{nb:<4}")
    ta += sa; va += na; tb += sb; vb += nb
print(f"{'TOTAL':36} {ta:>5}/{va:<4} {tb:>5}/{vb:<4}")