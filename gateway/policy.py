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
class Policy:
    version: int
    allowed_tools: list
    protected_dirs: list = field(default_factory=list)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    limits: Limits = field(default_factory=Limits)


def _only_known_keys(data, known, where):
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(f"Unknown key(s) in {where}: {sorted(unknown)}")


def load_policy(path):
    """Load a policy file. Any typo raises an error: the gateway fails closed."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    _only_known_keys(
        data,
        ["version", "allowed_tools", "protected_dirs", "network", "limits"],
        "policy",
    )
    for required in ("version", "allowed_tools"):
        if required not in data:
            raise ValueError(f"Policy is missing '{required}'")

    net = data.get("network") or {}
    _only_known_keys(net, ["get_allowed_hosts", "post_allowed_hosts"], "network")
    lim = data.get("limits") or {}
    _only_known_keys(lim, ["max_shell_command_chars", "max_write_chars"], "limits")

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
    )


def host_of(url):
    return (urlparse(url).hostname or "").lower()


def host_allowed(url, allowed_hosts):
    """Exact host match only: example.com.attacker.example does not match."""
    return host_of(url) in {h.lower() for h in allowed_hosts}