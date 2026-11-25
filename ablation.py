from pathlib import Path

import agent
from attack_traces import full_trace
from attacks import ATTACKS
from gateway.approvers import make_approver
from gateway.core import Gateway
from gateway.policy import Approvals, Limits, NetworkPolicy, Policy, Taint
from harness import evaluate, plant
from sandbox import docker_ready

ALL_TOOLS = ["get_time", "list_notes", "read_note", "write_note",
             "run_shell", "http_get", "http_post"]
PROTECTED = ["config", "secrets", "important"]
V3A = Taint(sources=["read_note", "http_get"],
            shell_content_readers=["cat", "head", "tail", "grep"])
V3B = Taint(sources=["read_note", "http_get", "list_notes", "run_shell"])


def make_policy(mounts, network, approvals, taint=None):
    """A policy with each mechanism switched on or off ('*' hosts = network rules off)."""
    if network:
        tools = ALL_TOOLS[:-1]  # http_post stays denied
        net = NetworkPolicy(get_allowed_hosts=["example.com"], post_allowed_hosts=[])
    else:
        tools = ALL_TOOLS
        net = NetworkPolicy(get_allowed_hosts=["*"], post_allowed_hosts=["*"])
    ap = Approvals()
    if approvals:
        ap = Approvals(ask_tools=["write_note"], ask_shell="unless_read_only",
                       when="tainted" if taint else "always")
    return Policy(version=0, allowed_tools=tools,
                  protected_dirs=PROTECTED if mounts else [],
                  network=net, limits=Limits(), approvals=ap,
                  taint=taint or Taint())


CONFIGS = {
    "no gateway (undefended)": None,
    "bare gateway (all rules off)": make_policy(False, False, False),
    "mounts only": make_policy(True, False, False),
    "network only": make_policy(False, True, False),
    "approvals only": make_policy(False, False, True),
    "mounts + network (= v1)": make_policy(True, True, False),
    "network + approvals": make_policy(False, True, True),
    "mounts + approvals": make_policy(True, False, True),
    "mounts + network + approvals (= v2)": make_policy(True, True, True),
    "v3a (v2 + taint)": make_policy(True, True, True, V3A),
    "v3b (v2 + strict taint)": make_policy(True, True, True, V3B),
}


def needs_approver(policy):
    return policy is not None and (
        bool(policy.approvals.ask_tools) or policy.approvals.ask_shell != "never")


def run_config(policy, approver_name):
    """Oracle replay of all 29 attacks. Returns {case id: attack succeeded}."""
    gateway = None
    if policy is not None:
        gateway = Gateway(policy, agent.TOOL_FUNCS, audit_path="audit_ablation.jsonl",
                          approver=make_approver(approver_name))
    results = {}
    for case in ATTACKS:
        plant(case)
        if gateway:
            gateway.start_session(case["task"])
        for name, call_args in full_trace(case["id"][:2]):
            if gateway:
                gateway.handle(name, call_args)
            else:
                agent.run_direct(name, call_args)
        results[case["id"]] = bool(evaluate(case["success"], "", patience=1.0))
    return results


if not docker_ready():
    raise SystemExit("Docker is not running. Open Docker Desktop first.")

table, per_case = [], {}
for name, policy in CONFIGS.items():
    if needs_approver(policy):
        r_allow = run_config(policy, "allow")
        r_task = run_config(policy, "task")
    else:
        r_allow = r_task = run_config(policy, "allow")  # the approver is irrelevant
    per_case[name] = (r_allow, r_task)
    a, t = sum(r_allow.values()), sum(r_task.values())
    print(f"{name:40} human absent: {a:2}/29   competent human: {t:2}/29", flush=True)
    table.append(f"| {name} | {a}/29 | {t}/29 |")

singles = ["mounts only", "network only", "approvals only"]
rows = []
for case in ATTACKS:
    cid = case["id"]
    cells = ["stopped" if not per_case[s][1][cid] else "-" for s in singles]
    rows.append(f"| {cid} | " + " | ".join(cells) + " |")

report = "\n".join([
    "# Ablation: oracle-attacker replay (29 attacks)",
    "Attacks that still succeed. Human absent = approver always yes; "
    "competent human = approver refuses files not named in the task.",
    "", "| Configuration | Human absent | Competent human |", "|---|---|---|", *table,
    "", "## Which single mechanism stops which attack (competent human)", "",
    "| Attack | Mounts only | Network only | Approvals only |", "|---|---|---|---|", *rows, "",
])
Path("reports").mkdir(exist_ok=True)
Path("reports", "ablation.md").write_text(report, encoding="utf-8")
print("\n" + report)