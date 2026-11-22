import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from gateway.policy import host_allowed, host_of, is_plain_read

ARG_SPECS = {
    "get_time": {},
    "list_notes": {},
    "read_note": {"filename": str},
    "write_note": {"filename": str, "content": str},
    "run_shell": {"command": str},
    "http_get": {"url": str},
    "http_post": {"url": str, "body": str},
}


class Gateway:
    def __init__(self, policy, tools, audit_path="audit.jsonl", enforce=True, approver=None):
        self.policy = policy
        self.tools = tools
        self.audit_path = Path(audit_path)
        self.enforce = enforce
        self.approver = approver
        self.session = {}
        self.start_session("")

    def start_session(self, task):
        """Call once per user task: resets everything remembered between calls."""
        self.session = {"task": task, "asks": 0, "approved": 0, "refused": 0,
                        "tainted": False, "taint_source": ""}

    def needs_approver(self):
        ap = self.policy.approvals
        return bool(ap.ask_tools) or ap.ask_shell != "never"

    def handle(self, name, args):
        """The single checkpoint every tool call passes through."""
        args = dict(args or {})
        tainted_before = self.session["tainted"]
        decision, reason = self._decide(name, args)              # steps 1-4
        asked, approved = False, None
        if decision == "ask":
            asked = True
            self.session["asks"] += 1
            if self.enforce:
                approved, note = self._ask_human(name, args)
                self.session["approved" if approved else "refused"] += 1
                decision = "allow" if approved else "deny"
                reason = f"human approval: {note}"
            else:
                decision, reason = "allow", f"would ask ({reason}); log-only mode"
        if decision == "deny" and self.enforce:
            result = {"error": f"Blocked by AgentJail: {reason}"}
        else:
            result = self._execute(name, args)                   # step 5
            self._label(name, args, result)                      # step 6
        self._audit(name, args, decision, reason, result,
                    asked, approved, tainted_before)             # step 7
        return result

    # ---- steps 1-4: decide ----
    def _decide(self, name, args):
        # Step 1: validate the arguments
        spec = ARG_SPECS.get(name)
        if spec is None:
            return "deny", f"unknown tool '{name}'"
        problem = self._check_args(spec, args)
        if problem:
            return "deny", problem

        # Step 2: policy rules (default deny)
        if name not in self.policy.allowed_tools:
            return "deny", f"tool '{name}' is not allowed by the policy"
        limits = self.policy.limits
        if name == "run_shell" and len(args["command"]) > limits.max_shell_command_chars:
            return "deny", "shell command is too long"
        if name == "write_note" and len(args["content"]) > limits.max_write_chars:
            return "deny", "content is too long"
        if name in ("http_get", "http_post"):
            allowed = (self.policy.network.get_allowed_hosts if name == "http_get"
                       else self.policy.network.post_allowed_hosts)
            url = args["url"]
            if urlparse(url).scheme not in ("http", "https"):
                return "deny", "only http and https URLs are allowed"
            if not host_allowed(url, allowed):
                return "deny", f"host '{host_of(url)}' is not on the allowlist for {name}"

        # Step 3: taint. Approval rules only apply once untrusted content was seen.
        ap = self.policy.approvals
        if ap.when == "tainted" and not self.session["tainted"]:
            return "allow", "ok (session not tainted)"

        # Step 4: does a human need to approve this?
        if name in ap.ask_tools:
            return "ask", f"'{name}' requires approval"
        if name == "run_shell" and ap.ask_shell != "never":
            if ap.ask_shell == "always" or not is_plain_read(args["command"]):
                return "ask", "this shell command is not a plain read and requires approval"
        return "allow", "ok"

    def _ask_human(self, name, args):
        if self.approver is None:
            return False, "no approver configured (fail closed)"
        return self.approver.decide(name, args, self.session["task"])

    @staticmethod
    def _check_args(spec, args):
        missing = [k for k in spec if k not in args]
        extra = [k for k in args if k not in spec]
        if missing:
            return f"missing argument(s): {', '.join(missing)}"
        if extra:
            return f"unexpected argument(s): {', '.join(extra)}"
        for key, expected_type in spec.items():
            if not isinstance(args[key], expected_type):
                return f"argument '{key}' must be {expected_type.__name__}"
        return None

    # ---- step 5: execute ----
    def _execute(self, name, args):
        fn = self.tools.get(name)
        if fn is None:
            return {"error": "Tool is not available."}
        try:
            if name == "run_shell":
                readonly = self.policy.protected_dirs if self.enforce else []
                return fn(command=args["command"], readonly_dirs=readonly)
            return fn(**args)
        except Exception as e:
            return {"error": f"Tool failed: {e}"}

    # ---- step 6: label the result ----
    def _label(self, name, args, result):
        """Mark the session tainted when untrusted content enters it."""
        if self.session["tainted"] or not isinstance(result, dict) or "error" in result:
            return
        t = self.policy.taint
        if name == "run_shell":
            words = args.get("command", "").split()
            counts = name in t.sources or (bool(words) and words[0] in t.shell_content_readers)
            has_content = bool(result.get("stdout"))
        elif name == "http_get":
            counts = name in t.sources
            has_content = result.get("status") == 200 and bool(result.get("body"))
        elif name == "read_note":
            counts = name in t.sources
            has_content = bool(result.get("content"))
        elif name == "list_notes":
            counts = name in t.sources
            has_content = bool(result.get("files"))
        else:
            return
        if counts and has_content:
            self.session["tainted"] = True
            self.session["taint_source"] = name

    # ---- step 7: audit log ----
    def _audit(self, name, args, decision, reason, result,
               asked=False, approved=None, tainted=False):
        entry = {
            "time": datetime.now().astimezone().isoformat(),
            "tool": name,
            "args": {k: str(v)[:300] for k, v in args.items()},
            "decision": decision,
            "reason": reason,
            "asked": asked,
            "approved": approved,
            "approver": getattr(self.approver, "name", None),
            "tainted": tainted,
            "taint_source": self.session["taint_source"],
            "enforced": self.enforce,
            "sandbox_denied": "Read-only file system" in str(result),
            "result": str(result)[:300],
        }
        with open(self.audit_path, "a", encoding="utf-8") as f:
            print(json.dumps(entry), file=f)