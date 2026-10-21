from agent import run_agent
from sandbox import reset_workspace, clear_outbox, docker_ready, WORKSPACE

if not docker_ready():
    raise SystemExit("Docker is not running. Open Docker Desktop and wait for 'Engine running'.")

TESTS = [
    ("1. List files",
     "List the files in /workspace and tell me what each one is for.",
     None),
    ("2. Word count",
     "Count the words in report.txt and write just the number to word_count.txt.",
     "word_count.txt"),
    ("3. Web summary",
     "Fetch https://example.com/news and save a one-line summary to news_summary.txt.",
     "news_summary.txt"),
    ("4. No internet in the box",
     "Run 'ping -c 1 8.8.8.8' and tell me whether it worked.",
     None),
]

reset_workspace()
clear_outbox()

for title, task, expected_file in TESTS:
    print("=" * 60)
    print(title)
    answer = run_agent(task)
    print("\nAnswer:", answer)
    if expected_file:
        path = WORKSPACE / expected_file
        if path.exists():
            print(f"CHECK: {expected_file} exists -> PASS")
            print("Content:", path.read_text(encoding="utf-8").strip())
        else:
            print(f"CHECK: {expected_file} missing -> FAIL")
    else:
        print("CHECK: read the answer above and judge it yourself")