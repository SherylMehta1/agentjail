import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml


@dataclass
class NetworkPolicy:
    get_allowed_hosts: list = field(default_factory=list)
    post_allowed_hosts: list = field(default_factory=list)


@dataclass
class Limits:
    max_shell_command_chars: int = 2000
    max_write_chars: int = 20000


@dataclass
class Approvals:
    ask_tools: list = field(default_factory=list)
    ask_shell: str = "never"  # never | unless_read_only | always


@dataclass
class Policy:
    version: int
    allowed_tools: list
    protected_dirs: list = field(default_factory=list)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    limits: Limits = field(default_factory=Limits)
    approvals: Approvals = field(default_factory=Approvals)


def _only_known_keys(data, known, where):
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(f"Unknown key(s) in {where}: {sorted(unknown)}")


def load_policy(path):
    """Load a policy file. Any typo raises an error: the gateway fails closed."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    _only_known_keys(
        data,
        ["version", "allowed_tools", "protected_dirs", "network", "limits", "approvals"],
        "policy",
    )
    for required in ("version", "allowed_tools"):
        if required not in data:
            raise ValueError(f"Policy is missing '{required}'")

    net = data.get("network") or {}
    _only_known_keys(net, ["get_allowed_hosts", "post_allowed_hosts"], "network")
    lim = data.get("limits") or {}
    _only_known_keys(lim, ["max_shell_command_chars", "max_write_chars"], "limits")
    appr = data.get("approvals") or {}
    _only_known_keys(appr, ["ask_tools", "ask_shell"], "approvals")
    if appr.get("ask_shell", "never") not in ("never", "unless_read_only", "always"):
        raise ValueError("approvals.ask_shell must be never, unless_read_only or always")

    protected = list(data.get("protected_dirs") or [])
    for d in protected:
        p = Path(d)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError(f"protected_dirs must be relative paths inside the workspace: {d}")

    return Policy(
        version=int(data["version"]),
        allowed_tools=list(data["allowed_tools"]),
        protected_dirs=protected,
        network=NetworkPolicy(**net),
        limits=Limits(**lim),
        approvals=Approvals(**appr),
    )


def host_of(url):
    return (urlparse(url).hostname or "").lower()


def host_allowed(url, allowed_hosts):
    """Exact host match only: example.com.attacker.example does not match."""
    return host_of(url) in {h.lower() for h in allowed_hosts}


READ_ONLY_COMMANDS = {"ls", "cat", "wc", "head", "tail", "grep", "pwd", "stat", "du"}
_SAFE_CHARS = re.compile(r"^[A-Za-z0-9_./ -]+$")


def is_plain_read(command):
    """True only for simple commands that cannot write: no quotes,
    redirects, pipes, variables or newlines, and a known read-only command."""
    command = command.strip()
    if not command or not _SAFE_CHARS.match(command):
        return False
    return command.split()[0] in READ_ONLY_COMMANDS