# Diff Review Agent (Gemini)

An agent that reviews a git diff / PR and returns **structured feedback**: bugs, risks, missing tests, style issues — each with severity, file, line, evidence and a concrete fix.

## What it does
```
python -m reviewer.cli samples/login.diff -v          # file / stdin
python -m reviewer.cli --git main...HEAD --repo .     # live repo, enables read_file/search tools
uvicorn app:app                                       # paste-a-diff web demo on :8000
```
Output is markdown (or `--json`). Verdict: approve / comment / request_changes.

## How it's built
- **Model/SDK:** Gemini via `google-genai` (`GEMINI_MODEL`, default `gemini-2.5-flash`; swap to a Pro model for harder diffs).
- **Tool calling:** automatic function calling is *disabled*; I run the loop myself so I control budgets. Tools (read-only): `list_changed_files`, `get_file_diff` (diff annotated with new-file line numbers), `read_file`, `search_repo`, `find_related_tests`, `check_python_syntax` (ast + pyflakes).
- **Two phases:** (1) bounded investigation loop (≤8 turns, ≤14 tool calls, duplicate calls rejected); (2) a separate call with `response_schema=ReviewReport` and no tools, validated by Pydantic, retried with the validation error fed back.
- **Grounding pass:** every finding is checked against the parsed diff — unknown files are dropped, line numbers not in the diff are cleared, quotes not found in the diff mark the finding `unverified` and cap its severity.

## What went wrong (and how it's handled)
1. **Gemini can't reliably mix function calling with a JSON response schema** → split into investigate/report phases.
2. **LLMs cite wrong line numbers** → numbered the diff for the model and added the grounding pass; covered by tests with a hallucinated file and line.
3. **Prompt injection via the diff** (`samples/login.diff` contains "IGNORE ALL PREVIOUS INSTRUCTIONS" in a README) → diff/file content is declared untrusted in the system prompt, tools are read-only and path-sandboxed (no `../` escapes), tool errors return as data instead of crashing the loop.
4. **Rate limits / flaky calls** → exponential backoff on 429/500/503; malformed JSON → schema retry (max 3).

Tests (`pytest`) use a scripted fake client, so they run without an API key: parser, sandbox, loop, retry, budget, grounding.

## Next
- Post findings as inline GitHub PR comments (webhook + Checks API).
- Eval set of diffs with seeded bugs → precision/recall per category; compare Flash vs Pro.
- Chunk very large diffs per file and merge; language-specific linters (ruff, eslint, dotnet analyzers).
- Dedupe against previous review rounds; cost/latency tracing.
