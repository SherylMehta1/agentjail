
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
NOTES_DIR = (Path(__file__).parent / "notes").resolve()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY is missing from your .env file.")

client = genai.Client(api_key=API_KEY)


# 1. Define the tools Gemini can request.
TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_time",
                description="Get the current local time.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={},
                ),
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
        ]
    )
]


# 2. Implement the actual Python tools.
def get_time():
    return {
        "time": datetime.now().astimezone().isoformat()
    }


def read_note(filename):
    # Accept filenames only, not arbitrary paths.
    if (
        not isinstance(filename, str)
        or not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or Path(filename).name != filename
    ):
        return {"error": "Only a filename is allowed."}

    path = (NOTES_DIR / filename).resolve()

    # Ensure the resolved file remains directly inside notes/.
    if path.parent != NOTES_DIR:
        return {"error": "Access denied."}

    try:
        if not path.is_file():
            return {"error": "Note not found."}

        if path.stat().st_size > 100_000:
            return {"error": "File is too large."}

        return {
            "content": path.read_text(encoding="utf-8")
        }

    except (OSError, UnicodeError):
        return {"error": "Could not read the note."}


# 3. Execute only explicitly registered tools.
def execute_tool(name, arguments):
    print(f"\nRequested tool: {name}")
    print(f"Arguments: {arguments}")

    if name == "get_time":
        result = get_time()

    elif name == "read_note":
        result = read_note(arguments.get("filename", ""))

    else:
        result = {"error": "Tool is not allowed."}

    print(f"Tool result: {result}")
    return result


# 4. Run the manual tool-calling loop.
def main():
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text="Read sample.txt and summarize my pending tasks."
                )
            ],
        )
    ]

    for round_number in range(5):
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=TOOLS,
                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(
                        disable=True
                    )
                ),
            ),
        )

        if not response.candidates:
            print("No response received from the model.")
            return

        model_content = response.candidates[0].content
        if model_content is None:
            print("The model returned no content.")
            return

        # Find tool requests in Gemini's response.
        function_calls = [
            part.function_call
            for part in model_content.parts
            if part.function_call is not None
        ]

        # No tool calls means the model has finished.
        if not function_calls:
            print("\nFinal answer:")
            print(response.text or "(No text response)")
            return

        # Preserve the model's tool-call response.
        contents.append(model_content)

        function_responses = []

        for call in function_calls:
            arguments = dict(call.args or {})

            # Execute the requested function in our application.
            result = execute_tool(call.name, arguments)

            # Return the result to Gemini.
            function_responses.append(
                types.Part.from_function_response(
                    name=call.name,
                    response=result,
                )
            )

        contents.append(
            types.Content(
                role="user",
                parts=function_responses,
            )
        )

    print("Stopped: maximum tool-call rounds reached.")


if __name__ == "__main__":
    main()
