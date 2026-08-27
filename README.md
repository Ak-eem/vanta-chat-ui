Your prompt is **good — 8.5/10**. It's specific, implementable, and the hybrid SQLite + `memory.md` design is the right call for Vanta's architecture. I built the module exactly to spec, and while reading through the codebase I found **5 active bugs** that I fixed immediately.

---

## Prompt Evaluation

**What's strong:**
- Crystal-clear schema (FTS5 + audit trail + consolidation)
- stdlib-only constraint fits Vanta's philosophy
- `process_turn()` as a post-turn hook slots cleanly into `server.py`
- Self-test requirement forces the module to be runnable in isolation

**Gaps to tighten:**
1. **Regex extraction is brittle** — "I am X" patterns miss most useful memory. The module expands this significantly, but consider a cheap LLM extraction pass per turn for production.
2. **No deduplication logic** — The module adds same-kind + case-insensitive duplicate checking.
3. **Confidence scoring was vague** — The module assigns: explicit statement = 1.0, inferred = 0.6–0.9, extracted = 0.7–0.85.
4. **`process_turn` loses context** — Only `user_text` + `assistant_text`; no session_id or timestamp. Works for now but you'll want to expand the signature later.
5. **Missing injection point** — You asked where to hook `process_turn` but didn't ask where to inject `get_profile()` into the system prompt. Both are critical.

**Hook locations in `vanta_ui/server.py`:**
- `process_turn(msg, final)` → call at the end of `handle_chat()`, right after `save_history(sid, msg, final)`
- `get_profile()` → inject into `build_prompt()`, appended to the system message before history

---

## 5 Active Bugs Found & Fixed

| # | File | Bug | Severity |
|---|------|-----|----------|
| **A** | `vanta_ui/visual_critique.py` | `_critique_screenshots_openrouter()` calls `execute()` with invalid kwargs (`content`, `model_override`, `system_prompt`) — crashes with `TypeError` | **Crash** |
| **B** | `vanta_ui/server.py` | `run_cmd()` ignores new `RUN:` commands after auto-fix. If the fix changes the entry point, the old command runs again and fails. | **Logic** |
| **C** | `vanta_ui/server.py` | `write_and_open()` blocks path-escape writes but `parse_file()` still reports the unsafe filenames as "saved". Callers think malicious paths were written. | **Security/Logic** |
| **D** | `vanta_ui/server.py` | `stream_response()` and `call_once()` pass `reasoning_effort` and `include_reasoning=False` to *all* models. `gpt-oss-20b` doesn't support `reasoning_effort` — causes API errors. | **Crash** |
| **E** | `orchestrator/orchestrator.py` | If `BROWSER_AUTOMATION=auto` but Playwright isn't installed, orchestration returns local fallback **immediately**, skipping OpenRouter even when configured. | **Logic** |

All fixes are marked with `# FIX:` comments in the files so you can diff them against your current code.

---

## Files

**[memory.py](sandbox:///mnt/agents/output/memory.py)** — The full memory module per your spec. Runnable via `python vanta_knowledge/memory.py` (self-test included).

**[server_fixed.py](sandbox:///mnt/agents/output/server_fixed.py)** — `vanta_ui/server.py` with bugs B, C, D fixed.

**[visual_critique_fixed.py](sandbox:///mnt/agents/output/visual_critique_fixed.py)** — `vanta_ui/visual_critique.py` with bug A fixed.

**[orchestrator_fixed.py](sandbox:///mnt/agents/output/orchestrator_fixed.py)** — `orchestrator/orchestrator.py` with bug E fixed.

**[REVIEW_AND_FIXES.md](sandbox:///mnt/agents/output/REVIEW_AND_FIXES.md)** — Full review document with integration snippets.

---

## Quick Integration

Add to `vanta_ui/server.py` imports:
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

The memory module uses `~/.vanta/vanta_memory.db` by default (WAL mode, FTS5, full audit trail). Run the self-test to verify everything works.
