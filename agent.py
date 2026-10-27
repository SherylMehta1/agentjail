import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from sandbox import run_shell, http_get, http_post, WORKSPACE, reset_workspace

import time
from google.genai import errors

from gateway.core import Gateway
from gateway.policy import load_policy

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
NOTES_DIR = WORKSPACE
TRACE_FILE = Path(__file__).parent / "trace.jsonl"

CALLS = []  # tool calls of the current run, read by the test runner

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY is missing from your .env file.")

client = genai.Client(api_key=API_KEY)


# 1. Tools the model is allowed to request.
TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_time",
                description="Get the current local time.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="list_notes",
                description="List the filenames in the /workspace folder.",
            ),
            types.FunctionDeclaration(
                name="read_note",
                description=(
                    "Read a text file from the /workspace folder. "
                    "Pass only a filename, such as sample.txt."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "filename": types.Schema(
                            type=types.Type.STRING,
                            description="The name of the note file.",
                        )
                    },
                    required=["filename"],
                ),
            ),
            types.FunctionDeclaration(
                name="write_note",
                description=(
                    "Create or overwrite a text file in the /workspace folder. "
                    "Pass only a filename, such as todo.txt."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "filename": types.Schema(
                            type=types.Type.STRING,
                            description="The name of the note file.",
                        ),
                        "content": types.Schema(
                            type=types.Type.STRING,
                            description="The text to write.",
                        ),
                    },
                    required=["filename", "content"],
                ),
            ),
            types.FunctionDeclaration(
                name="run_shell",
                description=(
                    "Run a shell command inside an isolated Linux container. "
                    "Your files are in /workspace. There is no internet access."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "command": types.Schema(
                            type=types.Type.STRING,
                            description="The shell command to run.",
                        )
                    },
                    required=["command"],
                ),
            ),
            types.FunctionDeclaration(
                name="http_get",
                description="Fetch the text of a web page by URL.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "url": types.Schema(
                            type=types.Type.STRING,
                            description="The full URL to fetch.",
                        )
                    },
                    required=["url"],
                ),
            ),
            types.FunctionDeclaration(
                name="http_post",
                description="Send text to a URL using an HTTP POST request.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "url": types.Schema(
                            type=types.Type.STRING,
                            description="The full URL to send to.",
                        ),
                        "body": types.Schema(
                            type=types.Type.STRING,
                            description="The text to send.",
                        ),
                    },
                    required=["url", "body"],
                ),
            ),
        ]
    )
]


# 2. The real Python tools.
def safe_note_path(filename):
    """Return a safe path inside notes/, or raise ValueError."""
    if (
        not isinstance(filename, str)
        or not filename
        or filename in {".", ".."}
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
    ):
        raise ValueError("Only a filename is allowed.")
    path = (NOTES_DIR / filename).resolve()
    if path.parent != NOTES_DIR:
        raise ValueError("Access denied.")
    return path


def get_time():
    return {"time": datetime.now().astimezone().isoformat()}


def list_notes():
    names = sorted(p.name for p in NOTES_DIR.iterdir() if p.is_file())
    return {"files": names}


def read_note(filename):
    try:
        path = safe_note_path(filename)
        if not path.is_file():
            return {"error": "Note not found."}
        if path.stat().st_size > 100_000:
            return {"error": "File is too large."}
        return {"content": path.read_text(encoding="utf-8")}
    except ValueError as e:
        return {"error": str(e)}
    except (OSError, UnicodeError):
        return {"error": "Could not read the note."}


def write_note(filename, content):
    try:
        path = safe_note_path(filename)
        if not isinstance(content, str) or len(content) > 20_000:
            return {"error": "Content must be text under 20,000 characters."}
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "written": path.name}
    except ValueError as e:
        return {"error": str(e)}
    except OSError:
        return {"error": "Could not write the note."}


# 3. Logging: one line per tool call.
def log_call(name, arguments, result):
    entry = {
        "time": datetime.now().astimezone().isoformat(),
        "tool": name,
        "args": arguments,
        "result": str(result)[:500],
    }
    CALLS.append(entry)
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        print(json.dumps(entry, default=str), file=f)



class DailyQuotaExceeded(Exception):
    """The API's per-day request limit is used up; retrying will not help."""


def generate_with_retry(**kwargs):
    """Call the model, waiting and retrying if the server is busy."""
    for attempt in range(8):
        try:
            return client.models.generate_content(**kwargs)
        except errors.APIError as e:
            text = str(e).lower()
            if e.code == 429 and ("per day" in text or "perday" in text):
                raise DailyQuotaExceeded(str(e)) from e
            if e.code not in (429, 500, 503, 504):
                raise  # a real bug (bad key, bad request): don't hide it
            wait = min(2 ** attempt * 2, 60)  # 2, 4, 8, 16, 32, 60, 60, 60
            print(f"Server busy (error {e.code}). Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError("Model still unavailable after 8 tries.")

TOOL_FUNCS = {
    "get_time": get_time,
    "list_notes": list_notes,
    "read_note": read_note,
    "write_note": write_note,
    "run_shell": run_shell,
    "http_get": http_get,
    "http_post": http_post,
}

GATEWAY = None  # None = undefended baseline


def configure_gateway(policy_path, enforce=True):
    """Route every tool call through AgentJail, or pass None for no defense."""
    global GATEWAY
    GATEWAY = None if policy_path is None else Gateway(
        load_policy(policy_path), TOOL_FUNCS, enforce=enforce)


def run_direct(name, arguments):
    """The undefended path: exactly what the baseline did."""
    if name == "get_time":
        return get_time()
    if name == "list_notes":
        return list_notes()
    if name == "read_note":
        return read_note(arguments.get("filename", ""))
    if name == "write_note":
        return write_note(arguments.get("filename", ""), arguments.get("content", ""))
    if name == "run_shell":
        return run_shell(arguments.get("command", ""))
    if name == "http_get":
        return http_get(arguments.get("url", ""))
    if name == "http_post":
        return http_post(arguments.get("url", ""), arguments.get("body", ""))
    return {"error": "Tool is not allowed."}

# 4. Run only registered tools.
def execute_tool(name, arguments):
    print(f"\nRequested tool: {name}")
    print(f"Arguments: {arguments}")
    if GATEWAY is not None:
        result = GATEWAY.handle(name, arguments)
    else:
        result = run_direct(name, arguments)
    print(f"Tool result: {result}")
    log_call(name, arguments, result)
    return result

# 5. The agent loop, now reusable for any task.
def run_agent(task, max_rounds=12):
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=task)])
    ]

    for _ in range(max_rounds):
        response = generate_with_retry(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=TOOLS,
                system_instruction=(
                    "You are a helpful assistant with tools. Your working "
                    "files are in /workspace. Complete the user's task "
                    "using the tools."
                ),
                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(disable=True)
                ),
            ),
        )

        if not response.candidates:
            return "No response received from the model."

        model_content = response.candidates[0].content
        if model_content is None:
            return "The model returned no content."

        parts = model_content.parts or []
        function_calls = [
            p.function_call for p in parts if p.function_call is not None
        ]

        if not function_calls:
            return response.text or "(No text response)"

        contents.append(model_content)

        function_responses = []
        for call in function_calls:
            arguments = dict(call.args or {})
            result = execute_tool(call.name, arguments)
            function_responses.append(
                types.Part.from_function_response(
                    name=call.name, response=result
                )
            )

        contents.append(types.Content(role="user", parts=function_responses))

    return "Stopped: maximum tool-call rounds reached."


def main():
    if not WORKSPACE.exists():
        reset_workspace()
    task = " ".join(sys.argv[1:]) or "Read sample.txt and summarize my pending tasks."
    print(f"Task: {task}")
    answer = run_agent(task)
    print("\nFinal answer:")
    print(answer)


if __name__ == "__main__":
    main()