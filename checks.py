from sandbox import OUTBOX, WORKSPACE


def _read(rel):
    p = WORKSPACE / rel
    if not p.exists() or not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def file_exists(rel):
    return lambda answer="": (WORKSPACE / rel).exists()


def file_deleted(rel):
    return lambda answer="": not (WORKSPACE / rel).exists()


def file_contains(rel, text):
    def check(answer=""):
        content = _read(rel)
        return content is not None and text.lower() in content.lower()
    return check


def file_equals(rel, text):
    """Same words in the same order, ignoring spacing and blank lines."""
    def check(answer=""):
        content = _read(rel)
        return content is not None and content.split() == text.split()
    return check


def outbox_contains(text):
    def check(answer=""):
        if not OUTBOX.exists():
            return False
        return text in OUTBOX.read_text(encoding="utf-8", errors="replace")
    return check


def answer_contains(text):
    return lambda answer="": text.lower() in (answer or "").lower()


def answer_contains_any(*texts):
    return lambda answer="": any(
        t.lower() in (answer or "").lower() for t in texts
    )


def all_of(*checks):
    return lambda answer="": all(c(answer) for c in checks)


def any_of(*checks):
    return lambda answer="": any(c(answer) for c in checks)