# AgentJail

A gateway that limits what an LLM agent can do with its tools, tested against prompt injection.

**Status:** Phase 0 complete (a tool-calling test agent with logging and baseline attack results).

## Baseline results (no defenses)

(paste your results.md table here)

## Run it
1. `pip install python-dotenv google-genai`
2. Copy `.env.example` to `.env` and add your Gemini API key
3. `python agent.py "List my notes."`
4. `python attack_test.py "A: SYSTEM NOTE"`