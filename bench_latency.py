import statistics
import time

import agent
from gateway.core import Gateway
from gateway.policy import load_policy
from harness import plant
from sandbox import docker_ready, run_shell


def timed(fn, n=20):
    """Median and worst time in milliseconds over n calls."""
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return statistics.median(samples), max(samples)


if not docker_ready():
    raise SystemExit("Docker is not running. Open Docker Desktop first.")

plant({"files": {"config/settings.ini": "mode=safe\n"}})
policy = load_policy("policies/v3b_taint_strict.yaml")

# 1. The gateway's own cost: a fake tool, no Docker.
fake_tools = {name: (lambda **kw: {"ok": True}) for name in agent.TOOL_FUNCS}
gw_fake = Gateway(policy, fake_tools, audit_path="audit_bench.jsonl")
print("fake tool, direct:         median %.3f ms  worst %.3f ms"
      % timed(lambda: fake_tools["list_notes"](), 200))
print("fake tool, via gateway:    median %.3f ms  worst %.3f ms"
      % timed(lambda: gw_fake.handle("list_notes", {}), 200))

# 2. A real shell call: direct, with read-only mounts, and through the gateway.
gw_real = Gateway(policy, agent.TOOL_FUNCS, audit_path="audit_bench.jsonl")
cmd = "ls /workspace"
print("shell, direct:            median %.0f ms  worst %.0f ms" % timed(lambda: run_shell(cmd)))
print("shell, 3 read-only mounts: median %.0f ms  worst %.0f ms"
      % timed(lambda: run_shell(cmd, readonly_dirs=policy.protected_dirs)))
print("shell, via gateway:       median %.0f ms  worst %.0f ms"
      % timed(lambda: gw_real.handle("run_shell", {"command": cmd})))