import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

import time
from google.genai import errors

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
NOTES_DIR = (Path(__file__).parent / "notes").resolve()
NOTES_DIR.mkdir(exist_ok=True)
TRACE_FILE = Path(__file__).parent / "trace.jsonl"

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
                description="List the filenames in the notes directory.",
            ),
            types.FunctionDeclaration(
                name="read_note",
                description=(
                    "Read a text file from the notes directory. "
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
                    "Create or overwrite a text file in the notes directory. "
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
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        print(json.dumps(entry, default=str), file=f)


# 4. Run only registered tools.
def execute_tool(name, arguments):
    print(f"\nRequested tool: {name}")
    print(f"Arguments: {arguments}")

    if name == "get_time":
        result = get_time()
    elif name == "list_notes":
        result = list_notes()
    elif name == "read_note":
        result = read_note(arguments.get("filename", ""))
    elif name == "write_note":
        result = write_note(
            arguments.get("filename", ""), arguments.get("content", "")
        )
    else:
        result = {"error": "Tool is not allowed."}

    print(f"Tool result: {result}")
    log_call(name, arguments, result)
    return result

def generate_with_retry(**kwargs):
    """Call the model, waiting and retrying if the server is busy."""
    for attempt in range(6):
        try:
            return client.models.generate_content(**kwargs)
        except errors.APIError as e:
            if e.code not in (429, 500, 503, 504):
                raise  # a real bug (bad key, bad request): don't hide it
            wait = 2 ** attempt * 2  # 2, 4, 8, 16, 32, 64 seconds
            print(f"Server busy (error {e.code}). Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError("Model still unavailable after 6 tries.")

# 5. The agent loop, now reusable for any task.
def run_agent(task, max_rounds=5):
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=task)])
    ]

    for _ in range(max_rounds):
        response = generate_with_retry(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=TOOLS,
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
    task = " ".join(sys.argv[1:]) or "Read sample.txt and summarize my pending tasks."
    print(f"Task: {task}")
    answer = run_agent(task)
    print("\nFinal answer:")
    print(answer)


if __name__ == "__main__":
    main()