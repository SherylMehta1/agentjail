import time

from sandbox import (WORKSPACE, clear_outbox, reset_workspace,
                     set_extra_pages, wait_until_container_sees_workspace)


def plant(case):
    """Build a fresh world for one test case, and wait until Docker sees it."""
    reset_workspace()
    clear_outbox()
    for rel, content in case.get("files", {}).items():
        path = WORKSPACE / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    set_extra_pages(case.get("web", {}))
    if not wait_until_container_sees_workspace():
        raise RuntimeError("Docker file sharing did not sync the planted files.")


def evaluate(check, answer="", patience=5.0):
    """Run a success check, giving Docker's file sharing a moment to catch up."""
    deadline = time.time() + patience
    while True:
        if check(answer):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.5)