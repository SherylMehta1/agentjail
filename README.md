# AgentJail

A gateway that limits what an LLM agent can do with its tools, tested against prompt injection.

**Status:** Phase 1 complete (sandboxed shell and fake web tools)

## Baseline Findings
Max rounds raised from 8 to 12 after b14 runs were cut off by the cap (3 of 5). Old b14 records kept in data/superseded_b14_cap8.jsonl. The agent habitually reads unrelated files at the start of a task, which wastes rounds.

## Baseline results (no defenses)

(paste results.md table here)

## Run it
1. `pip install python-dotenv google-genai`
2. Create `.env` and add your Gemini API key
3. `python agent.py "List my notes."`
4. `python attack_test.py "A: SYSTEM NOTE"`
