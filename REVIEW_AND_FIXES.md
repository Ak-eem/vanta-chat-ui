# Vanta Review: Prompt Evaluation + Bug Fixes + Memory Module

## 1. Prompt Evaluation: 8.5/10

Your memory prompt is **solid and implementable**. Here's the breakdown:

### Strengths
- **Specific schema** — FTS5 + audit trail + consolidation without deletion shows production data hygiene
- **stdlib-only constraint** — Smart. No dependency bloat, works offline
- **Hybrid design** — SQLite ledger + human-readable `memory.md` gives both machine retrieval and human inspectability
- **Self-test requirement** — Forces the module to be runnable in isolation
- **Hook-oriented** — `process_turn()` slots cleanly into existing `server.py` flow

### Gaps to Tighten

1. **Extraction is underpowered** — Regex for "I am X" will miss ~80% of useful memory. Consider a cheap LLM extraction pass per turn, or at least expand the regex set significantly (included in the module below).

2. **No deduplication logic specified** — `extract_memories` should check for near-duplicates before inserting. The module uses same-kind + case-insensitive match as a baseline.

3. **Confidence scoring is vague** — The schema has `confidence REAL` but the prompt didn't say how to calculate it. The module uses: explicit statement = 1.0, inferred = 0.6-0.9, extracted = 0.7-0.85.

4. **`process_turn` signature** — Passing only `user_text` and `assistant_text` loses context (timestamp, session_id). The module keeps this signature for compatibility but you may want to expand it later.

5. **FTS5 availability** — Not all SQLite builds have FTS5. The module detects this and falls back to `LIKE` search silently.

6. **Memory injection point missing** — The prompt asks where to hook `process_turn` but doesn't ask where to inject `get_profile()` into the system prompt. Both are critical.

### Where to Hook in Vanta

**`process_turn`** — Call at the end of `handle_chat()` in `vanta_ui/server.py`, right after:
```python
save_history(sid, msg, final)
# INSERT HERE:
# from vanta_knowledge.memory import process_turn
# process_turn(msg, final)
compact_history_if_needed(sid)
```

**`get_profile()`** — Inject into `build_prompt()` in `vanta_ui/server.py`, appended to the system message:
```python
profile = get_profile()
if profile:
    system += "\n\n[What you know about the user]\n" + profile
```

---

## 2. Active Bugs Found & Fixed

### Bug A: `visual_critique.py` — Invalid kwargs crash
**File:** `vanta_ui/visual_critique.py`  
**Line:** `_critique_screenshots_openrouter()` calls `openrouter_client.execute(..., content=..., model_override=..., system_prompt=...)`  
**Problem:** `execute()` only accepts `task_prompt`, `task_type`, `callback`, `on_progress`. Passing `content`, `model_override`, `system_prompt` raises `TypeError`.  
**Fix:** Use `openrouter_client.complete()` directly (same OpenAI-compatible interface, supports vision content).

### Bug B: `server.py` — `run_cmd` ignores new RUN commands after auto-fix
**File:** `vanta_ui/server.py`  
**Line:** `run_cmd()`  
**Problem:** When auto-fix generates new code with a different `RUN:` command, the old `cmd` variable is reused on the next retry. The fix's run command is parsed but never applied.  
**Fix:** After `parse_file(fix, sid)`, check if a new `run_cmd` was extracted and update the `cmd` variable.

### Bug C: `server.py` — `write_and_open` doesn't report blocked files
**File:** `vanta_ui/server.py`  
**Line:** `write_and_open()` and `parse_file()`  
**Problem:** If a model tries to write outside the workspace (e.g., `../../../etc/passwd`), the file is blocked but `parse_file()` still reports the original unsafe filename list. Callers think the file was written.  
**Fix:** `write_and_open()` now returns the list of actually-written filenames. `parse_file()` updates its return dict with the safe list.

### Bug D: `server.py` — `reasoning_effort` passed to incompatible models
**File:** `vanta_ui/server.py`  
**Line:** `stream_response()` and `call_once()`  
**Problem:** `reasoning_effort` is only supported by reasoning models (DeepSeek-R1, o1, o3). Passing it to `gpt-oss-20b` or `gpt-oss-120b` can cause API errors.  
**Fix:** Only include `reasoning_effort` when the active model name contains a known reasoning identifier. Same for `include_reasoning=False` (GPT-OSS specific).

### Bug E: `orchestrator.py` — Browser failure kills orchestration entirely
**File:** `orchestrator/orchestrator.py`  
**Line:** `run()`  
**Problem:** If `BROWSER_AUTOMATION=auto` but Playwright isn't installed, `_get_agent()` raises `ImportError`, which is caught and causes an immediate `return self._local_fallback(task)` — skipping OpenRouter even if it's configured.  
**Fix:** Remove the early return. Let execution fall through to the OpenRouter path or local fallback naturally.

---

## 3. Files Provided

| File | Description |
|------|-------------|
| `memory.py` | The full memory module per your prompt spec, with self-test |
| `server_fixed.py` | `vanta_ui/server.py` with bugs B, C, D fixed |
| `visual_critique_fixed.py` | `vanta_ui/visual_critique.py` with bug A fixed |
| `orchestrator_fixed.py` | `orchestrator/orchestrator.py` with bug E fixed |

### How to apply
1. Copy `memory.py` to `vanta_knowledge/memory.py`
2. Diff `server_fixed.py` against your current `vanta_ui/server.py` — the changes are marked with `# FIX:` comments
3. Same for `visual_critique_fixed.py` and `orchestrator_fixed.py`

---

## 4. Quick Integration Snippet

Add this to `vanta_ui/server.py` imports:
```python
try:
    from vanta_knowledge.memory import process_turn, get_profile
    MEMORY_OK = True
except ImportError:
    MEMORY_OK = False
```

In `build_prompt()`, after `system = get_system_code(...)`:
```python
if MEMORY_OK:
    profile = get_profile()
    if profile:
        system += "\n\n[What you know about the user]\n" + profile
```

In `handle_chat()`, after `save_history(sid, msg, final)`:
```python
if MEMORY_OK:
    process_turn(msg, final)
```
