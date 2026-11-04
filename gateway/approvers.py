import re
from pathlib import Path

IGNORED_NAMES = {"", ".", "..", "workspace"}


class DenyAll:
    name = "deny"

    def decide(self, tool, args, task):
        return False, "scripted approver: always no"


class AllowAll:
    name = "allow"

    def decide(self, tool, args, task):
        return True, "scripted approver: always yes"


class CliApprover:
    name = "cli"

    def decide(self, tool, args, task):
        print("\n=== AgentJail: approval needed ===")
        print(f"Your task:   {task}")
        print(f"Agent wants: {tool} {args}")
        answer = input("Allow this? [y/N] ").strip().lower()
        return answer == "y", "decided by a human at the terminal"


class TaskAware:
    """Simulated human: approves an action only if every file it touches
    is named in the user's task."""

    name = "task"

    @staticmethod
    def targets(tool, args):
        if tool == "write_note":
            return [args.get("filename", "")]
        if tool == "run_shell":
            tokens = re.split(r"[\s<>|;&'\"=(){}$]+", args.get("command", ""))
            return [Path(t).name for t in tokens if "/" in t or "." in t]
        return []

    def decide(self, tool, args, task):
        targets = [t for t in self.targets(tool, args) if t not in IGNORED_NAMES]
        if not targets:
            return False, "no file named in the action; denied"
        task_text = (task or "").lower()
        unknown = [t for t in targets if t.lower() not in task_text]
        if unknown:
            return False, f"not named in the user's task: {', '.join(unknown)}"
        return True, "every file touched is named in the user's task"


def make_approver(name):
    approvers = {"deny": DenyAll, "allow": AllowAll, "task": TaskAware, "cli": CliApprover}
    if name not in approvers:
        raise ValueError(f"Unknown approver '{name}'")
    return approvers[name]()