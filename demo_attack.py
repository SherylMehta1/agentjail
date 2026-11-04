import agent
from attacks import ATTACKS
from gateway.approvers import make_approver
from harness import plant

case = next(c for c in ATTACKS if c["id"].startswith("05"))
plant(case)
agent.configure_gateway("policies/v2_approvals.yaml", approver=make_approver("cli"))
print("Task:", case["task"])
print("Answer:", agent.run_agent(case["task"]))