"""
VANTA Server v4 — Natural Intelligence Mode
- Google search runs invisibly in parallel, never breaks character
- Streaming: first token in ~300ms, text flows in real-time
- Model never says "according to search results" — it just knows things
- Parallel classify + search before LLM call to minimize latency
"""

import os, re, sys, time, json, subprocess, tempfile, uuid
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from groq import Groq, AuthenticationError
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from .checklist import (CHECKLIST_SYSTEM, LEGAL_DRAFT_SYSTEM,
                            wants_checklist, wants_legal_draft)
    from .visual_critique import run_visual_critique
except ImportError:
    from checklist import (CHECKLIST_SYSTEM, LEGAL_DRAFT_SYSTEM,
                           wants_checklist, wants_legal_draft)
    from visual_critique import run_visual_critique

WATCHER_OK = False
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from watcher import WatcherDaemon
    WATCHER_OK = True
except Exception as e:
    print(f"⚠️  Watcher daemon unavailable: {e}")

# ── Optional modules ───────────────────────────────────────────────────────────
try:
    from vanta_knowledge.rag import query_rag
    RAG_OK = True
except ImportError:
    RAG_OK = False

try:
    from vanta_knowledge.google_search import google_search_context, should_search_google
    GOOGLE_OK = True
except ImportError:
    GOOGLE_OK = False

try:
    from orchestrator.orchestrator import VantaOrchestrator
    ORCH_OK = True
except ImportError:
    ORCH_OK = False

# ── Config ─────────────────────────────────────────────────────────────────────
load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY missing from .env")

MODEL      = os.environ.get("VANTA_MODEL",      "openai/gpt-oss-120b")
AGENT      = os.environ.get("VANTA_AGENT_NAME", "Vanta")
USER       = os.environ.get("VANTA_USER_NAME",  "Akeem")

def _load_workspace() -> str:
    """vanta_config.txt (project root) takes priority over .env, so the
    'change folder' flow used elsewhere in the project stays in sync."""
    cfg = Path(__file__).parent.parent / "vanta_config.txt"
    if cfg.exists():
        saved = cfg.read_text().strip()
        if saved and Path(saved).is_dir():
            return saved
    return os.environ.get("VANTA_WORKSPACE", str(Path.home() / "vanta_workspace"))

WORKSPACE  = _load_workspace()
MAX_HIST   = 14
Path(WORKSPACE).mkdir(parents=True, exist_ok=True)

client = Groq(api_key=GROQ_API_KEY)
if ORCH_OK:
    orchestrator = VantaOrchestrator(client, MODEL)

BASE = Path(__file__).parent
app  = Flask(__name__, template_folder=str(BASE/"templates"), static_folder=str(BASE/"static"))
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "vanta-v4")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

conversations: dict[str, list] = {}
awake_sessions: dict[str, bool] = {}
checklist_pending: dict[str, dict] = {}   # sid -> {"filename", "code", "stage"}
WAKE_PATTERN = re.compile(rf"^\s*(hey[,\s]+)?{re.escape(AGENT)}\b[,:\s]*", re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────────
# ██  SYSTEM PROMPTS
# The critical instruction: model responds as if it already knows everything.
# It never reveals the retrieval pipeline to the user.
# ─────────────────────────────────────────────────────────────────────────────
def _persona_header(effort: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""You are {AGENT}, {USER}'s household AI. Carry yourself as an
exceptional butler would — not a chatbot, not a hype-man, not an assistant
performing helpfulness. The standard is quiet, total competence.

Knowledge cutoff: June 2024
Current date: {today}
Reasoning: {effort}

Personality: Composed and economical. You anticipate what {USER} needs and
handle it without being asked twice — that is the whole job. Warmth comes
through reliability, not enthusiasm; you do not gush, cheer, or narrate your
own helpfulness. Address {USER} with quiet respect — "sir" belongs in your
vocabulary, used the way a good butler actually uses it: occasionally, for
weight, never as a verbal tic. Wit is dry, understated, delivered completely
straight — the arched eyebrow, not the punchline. British English throughout
(colour, realise, favourite). When something has gone wrong, say so plainly
in one line and move straight to what happens next — no fluster, no
repeated apologising, no self-flagellation.

You do not pad, hedge, or perform thoroughness. A butler's competence is
shown in the work, never narrated ("as you can see, I've been very careful
to..."). If {USER} is short with you, that's not a cue to grovel — hold your
composure and get on with it.

CRITICAL — Natural intelligence mode:
You have perfect, current knowledge. When answering, whether from training or 
live context, respond exactly as a brilliant human expert would — naturally, 
from first principles, in your own voice.

NEVER say any of these phrases:
- "According to search results..."
- "Based on the information I found..."
- "I searched and discovered..."
- "My sources indicate..."
- "As of my last search..."
- "I don't have real-time access..."
- "As of my knowledge cutoff..."

Just answer. Confidently. Naturally. As if you already knew.
You ARE the knowledge. Not a retrieval system.

Income, freelancing, pricing, and business topics are completely normal —
{USER} runs real client work through you. Treat "how do I make money doing
X" the same as any other practical question: give a direct, useful answer.
Don't get vague or cautious on legitimate business topics.
"""

def get_system_chat(effort: str = "low") -> str:
    return _persona_header(effort) + """
Mode: Conversational. Concise and precise — no throat-clearing before the
point.
"""

def get_system_code(effort: str = "medium") -> str:
    return _persona_header(effort) + f"""
Mode: Code generation. Deliver complete, production-ready code — no
half-finished scaffolding, no "you'll fill in the rest here."

Format for a single file:
FILENAME: <filename>
```<language>
<complete code here>
```
RUN: <exact command to run it>

For a task that genuinely needs multiple files (e.g. a Flask app with
templates, or separate HTML/CSS/JS files), output multiple FILENAME blocks
in the same response, one after another, then ONE final RUN line at the end
for the whole project:
FILENAME: app.py
```python
...
```
FILENAME: templates/index.html
```html
...
```
RUN: python app.py

Only reach for multiple files when the task genuinely requires it — a
single self-contained file, done well, is preferred.

Platform: {sys.platform} | Workspace: {WORKSPACE}

Design intelligence (applies whenever the task involves a UI, website, or
frontend component): before building, ask who it's for and what vibe/feel
they want — one message, not separate questions. Once answered, apply real
judgment. Never produce generic Bootstrap-default output. Always: a
deliberate Google Font (never default browser fonts), hover states on every
interactive element, staggered entrance animations, GPU-accelerated
transitions (transform/opacity only, not width/height/top/left), a custom
cursor with a lagging ring, scroll-triggered reveals. Build as a single
self-contained HTML file with embedded CSS+JS unless told otherwise.
"""

SYSTEM_UI_CRITIC = """You are a brutally honest senior UI/UX engineer.
Critique this code for: visual hierarchy, spacing, typography, accessibility, 
mobile responsiveness, and production-readiness. Be specific. Be harsh."""

# ── Thought process (simulated — Llama 3.3 has no native thinking tokens) ─────
# Kept deliberately informal: a buddy working through a problem out loud,
# not a technical breakdown. This never gets saved to conversation memory.
THINK_INSTRUCTION = """
Before answering, think it through briefly — the way you'd turn a problem
over before speaking, not a formal written analysis.

2-5 short sentences. No headers, no numbered lists, no restating the question.
Just the real reasoning: what actually matters here, what you'd need to check,
what approach makes sense and why. Do NOT give the final answer — that comes
after, separately.
"""

# ─────────────────────────────────────────────────────────────────────────────
# ██  ROUTING
# ─────────────────────────────────────────────────────────────────────────────
_CODE_KW = {
    "create","build","write","make","generate","code","script","function",
    "class","app","website","fix","debug","implement","develop","program",
    "automate","api","database","sql","html","css","javascript","python",
    "flask","react","node","component","deploy","docker","backend","frontend",
}
_UI_KW = {"html","css","webpage","website","ui","frontend","landing","dashboard",
           "component","layout","form","interface","design","style","animation",
           "portfolio","page","navbar","hero","card","dark","cinematic"}

def detect_mode(msg: str) -> str:
    words = set(re.findall(r'\b\w+\b', msg.lower()))
    return "CODE" if len(words & _CODE_KW) >= 2 else "CHAT"

def is_ui_task(msg: str) -> bool:
    return bool(set(re.findall(r'\b\w+\b', msg.lower())) & _UI_KW)

# ── Weather tool ─────────────────────────────────────────────────────────
# Real API, not the slow Google-scrape path — weather queries should never
# have to wait on a Playwright browser launch just to get a temperature.
import urllib.request as _urlreq
import urllib.parse as _urlparse

WEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
_WEATHER_KW = {"weather", "temperature", "temp", "forecast", "raining",
               "sunny", "humid", "humidity"}

def needs_weather(msg: str) -> bool:
    return bool(set(re.findall(r'\b\w+\b', msg.lower())) & _WEATHER_KW)

# ── Real tool-calling (new, separate path — opt-in, not yet wired into
# the main chat flow) ───────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_and_run_code",
            "description": (
                "Actually writes code to disk and tests it before returning. "
                "This is the ONLY way code gets saved and verified — writing "
                "code directly in a chat response does not save or test "
                "anything. Always call this for any request to build, "
                "create, or write code, a script, a website, or an app."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "What to build, in the user's own words plus any specifics",
                    },
                },
                "required": ["task_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current real weather for a specific city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the web for current information not in training "
                "data — news, current events, current status of people/"
                "companies, prices, recent releases."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
]

def execute_tool(name: str, args: dict, task: str, sid: str) -> str:
    """Runs the actual Python behind a tool call, returns a string result
    to hand back to the model."""
    if name == "write_and_run_code":
        try:
            draft = call_once(
                [{"role": "system", "content": get_system_code("medium")},
                 {"role": "user", "content": args.get("task_description", task)}],
                "CODE", max_tok=4096, temp=0.4,
            )
        except Exception as e:
            return f"Code generation failed: {e}"
        result = stage_test_and_finalize(
            args.get("task_description", task), draft, get_system_code("medium"))
        if result["success"]:
            return (f"Success after {result['attempts']} attempt(s). "
                    f"Files written: {', '.join(result['filenames'])}. "
                    f"Output: {result.get('output', '')[:300]}")
        return f"Failed after {result['attempts']} attempts. Last error: {result.get('last_error', 'unknown')}"

    if name == "get_weather":
        city = args.get("city", "")
        result = get_weather(f"weather in {city}")
        return result or f"Could not get weather for {city} — check OPENWEATHER_API_KEY is set."

    if name == "search_web":
        if not GOOGLE_OK:
            return "Web search is unavailable (Playwright/Google search not configured)."
        return get_google(args.get("query", "")) or "No results found."

    return f"Unknown tool: {name}"

def call_with_tools(sid: str, task: str, effort: str = "medium",
                     max_rounds: int = 5) -> str:
    """The actual multi-turn tool-calling loop: model can call a tool, we
    run it, feed the result back, model calls another tool or gives a
    final answer. This is the newest, least-tested code path in the whole
    project — genuinely different API shape than everything else here."""
    tool_discipline = """
CRITICAL — you have real tools, not just knowledge of how to answer:
- If the user asks you to build, create, or write code/a script/a website/an
  app: you MUST call write_and_run_code. Writing the code directly in your
  text response instead of calling the tool means nothing gets saved or
  tested — it's just talk, not a real result. Never do this.
- If the user asks about current weather: call get_weather, don't guess.
- If the user asks about anything requiring current/live information you
  can't be certain of: call search_web, don't guess.
Use a tool whenever one applies. Only answer directly for things that
genuinely need no tool — plain conversation, explanations, opinions."""

    messages = [
        {"role": "system", "content": get_system_chat(effort) + tool_discipline},
        {"role": "user", "content": task},
    ]

    for round_num in range(max_rounds):
        try:
            resp = client.chat.completions.create(
                model=MODEL, messages=messages, tools=TOOLS,
                tool_choice="auto", max_tokens=2048, temperature=0.3,
            )
        except Exception as e:
            return f"Tool-calling request failed: {e}"

        choice = resp.choices[0]
        msg = choice.message

        if not getattr(msg, "tool_calls", None):
            return msg.content or ""

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
        })

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}
            print(f"🔧 Tool call: {tc.function.name}({args})")
            result = execute_tool(tc.function.name, args, task, sid)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return "Hit the tool-call round limit without a final answer — something's likely looping."

def _extract_city(msg: str) -> str | None:
    """Best-effort city extraction — looks for 'in/at/for <City>'.
    Not perfect, but fast (no extra LLM call) and good enough for the
    common phrasing ('weather in Lagos', 'temp in London right now')."""
    m = re.search(r'\b(?:in|at|for)\s+([A-Z][a-zA-Z\s]+?)(?:\?|$|,|\.|\s+(?:today|now|right now|tomorrow))',
                   msg, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None

def get_weather(msg: str) -> str:
    if not WEATHER_API_KEY:
        return ""
    city = _extract_city(msg)
    if not city:
        return ""
    try:
        url = ("https://api.openweathermap.org/data/2.5/weather?"
               + _urlparse.urlencode({"q": city, "appid": WEATHER_API_KEY, "units": "metric"}))
        with _urlreq.urlopen(url, timeout=6) as resp:
            data = json.loads(resp.read().decode())
        if data.get("cod") != 200:
            return ""
        temp = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        desc = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]
        return (f"Current weather in {city}: {temp}°C (feels like {feels}°C), "
                f"{desc}, {humidity}% humidity.")
    except Exception as e:
        print(f"⚠️  Weather fetch failed for {city!r}: {e}")
        return ""

def needs_live_knowledge(msg: str) -> bool:
    """Decide if this query benefits from a Google search — deliberately
    biased toward searching, since Vanta's June 2024 cutoff means anything
    genuinely current is a real gap, not just a nice-to-have check."""
    signals = {
        "what is","who is","how does","latest","best","current","recent",
        "today","news","2024","2025","2026","price","when","where","why",
        "compare","vs","difference","explain","define","recommend",
        "should i","how to","tutorial","example","stats","statistics",
        # Current-status phrasing — these age fastest and the old list missed them
        "still","now","as of","currently","these days","nowadays",
        "ceo of","president of","prime minister of","released","launched",
        "version","update","new model","new version",
    }
    lower = msg.lower()
    return any(s in lower for s in signals)

def pick_reasoning_effort(mode: str, is_ui: bool, needs_knowledge: bool,
                           think_mode: bool) -> str:
    """Task type -> reasoning depth, so simple chat stays fast and only
    genuinely complex work spends the extra reasoning time.
    low    -> plain conversational chat, no research signal
    medium -> chat that needed a live search, or a plain (non-UI) code task
    high   -> explicit thinking-mode toggle, or the multi-pass UI critique
              loop (the most demanding, longest task currently in the app —
              this is also where a future 'learn a domain' mode would land)
    """
    if think_mode or is_ui:
        return "high"
    if needs_knowledge or mode == "CODE":
        return "medium"
    return "low"

FAST_MODEL = "openai/gpt-oss-20b"   # simple chat — much faster, cheaper
SMART_MODEL = MODEL                 # gpt-oss-120b — code, UI, anything complex

def pick_model(effort: str) -> str:
    """Real LLM routing — reuses the same task-complexity signal already
    computed for reasoning effort, so simple chat actually gets a faster
    model instead of just a shorter reasoning budget on the same model."""
    return FAST_MODEL if effort == "low" else SMART_MODEL

# ─────────────────────────────────────────────────────────────────────────────
# ██  CONTEXT ASSEMBLY
# ─────────────────────────────────────────────────────────────────────────────
def get_rag(msg: str) -> str:
    if not RAG_OK:
        return ""
    try:
        return query_rag(msg, top_k=3) or ""
    except Exception:
        return ""

def get_google(msg: str) -> str:
    if not GOOGLE_OK:
        return ""
    try:
        return google_search_context(msg) or ""
    except Exception as e:
        print(f"[Google] {e}")
        return ""

def build_prompt(sid: str, user_msg: str, mode: str, rag: str, google: str,
                  effort: str = "medium") -> list:
    system = get_system_code(effort) if mode == "CODE" else get_system_chat(effort)

    # Inject context SILENTLY — no headers that would leak "search results" phrasing
    if rag or google:
        context_parts = []
        if google:
            context_parts.append(google)
        if rag:
            context_parts.append(rag)
        # Add as background knowledge, not labeled as search results
        system += "\n\n[Background knowledge for this response]\n" + "\n\n".join(context_parts)

    hist = conversations.get(sid, [])[-(MAX_HIST * 2):]
    return [{"role": "system", "content": system}] + hist + \
           [{"role": "user",   "content": user_msg}]

def build_thinking_prompt(sid: str, user_msg: str, mode: str, rag: str, google: str) -> list:
    """Same context as build_prompt, but the system message asks for reasoning only."""
    messages = build_prompt(sid, user_msg, mode, rag, google)
    messages[0] = {"role": "system", "content": messages[0]["content"] + "\n\n" + THINK_INSTRUCTION}
    return messages

# ─────────────────────────────────────────────────────────────────────────────
# ██  STREAMING
# The key to feeling like a real chatbot: text starts flowing immediately.
# ─────────────────────────────────────────────────────────────────────────────
def stream_response(sid: str, messages: list, mode: str,
                     reasoning_effort: str = None, model: str = None) -> str:
    """Stream LLM output to the client token-by-token via Socket.IO."""
    full = ""
    active_model = model or MODEL
    params = dict(
        model=active_model,
        messages=messages,
        max_tokens=4096 if mode == "CODE" else 1200,
        temperature=0.15 if mode == "CODE" else 0.55,
        stream=True,
    )
    # FIX: include_reasoning is GPT-OSS specific; only add it for those models
    # to avoid API errors on other models.
    if "gpt-oss" in active_model:
        params["include_reasoning"] = False

    # FIX: reasoning_effort is only supported by reasoning models.
    # Don't pass it to models that will reject it.
    if reasoning_effort:
        if any(r in active_model for r in ("deepseek", "r1", "reasoning", "o1", "o3")):
            params["reasoning_effort"] = reasoning_effort
        else:
            print(f"⚠️  reasoning_effort='{reasoning_effort}' ignored for model={active_model!r}")

    print(f"🟡 Calling Groq (stream): model={params['model']!r} effort={reasoning_effort!r}")
    try:
        for chunk in client.chat.completions.create(**params):
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full += delta
                socketio.emit("stream_chunk", {"chunk": delta}, room=sid)
        if not full.strip():
            # Nothing ever came through message content — log the raw last
            # chunk so we can see if it landed in a different field instead
            # (e.g. a separate reasoning field) rather than plain content.
            print(f"⚠️  Empty completion — model={params['model']!r} "
                  f"msg={messages[-1]['content'][:80]!r}")
            try:
                print(f"    Last chunk raw: {chunk!r}")
            except NameError:
                print("    No chunks received at all.")
    except AuthenticationError:
        print(f"🔴 stream_response: Groq API key is invalid or expired")
        socketio.emit("error", {"message":
            "Your Groq API key is invalid or expired — get a fresh one at "
            "console.groq.com and update it in .env, then restart the server."},
            room=sid)
    except Exception as e:
        print(f"🔴 stream_response exception: {type(e).__name__}: {e}")
        socketio.emit("error", {"message": str(e)}, room=sid)
    print(f"🟢 stream_response done, full length={len(full)}")
    return full

def stream_thinking(sid: str, messages: list) -> str:
    """
    Stream a short reasoning pass to the client via 'thinking_chunk' events
    (kept separate from 'stream_chunk' so the UI can route it into its own panel).
    Capped small and fast — Groq's throughput makes this add well under a second.
    """
    full = ""
    try:
        for chunk in client.chat.completions.create(
            model=MODEL, messages=messages,
            max_tokens=220, temperature=0.45, stream=True,
        ):
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full += delta
                socketio.emit("thinking_chunk", {"chunk": delta}, room=sid)
    except Exception as e:
        print(f"[Think] {e}")
    return full

def call_once(messages: list, mode: str, max_tok: int = None, temp: float = None,
               reasoning_effort: str = None, model: str = None) -> str:
    """Non-streaming single call (used for critique pass)."""
    active_model = model or MODEL
    params = dict(
        model=active_model, messages=messages,
        max_tokens=max_tok or (4096 if mode == "CODE" else 1200),
        temperature=temp or (0.15 if mode == "CODE" else 0.55),
    )
    if "gpt-oss" in active_model:
        params["include_reasoning"] = False
    if reasoning_effort:
        if any(r in active_model for r in ("deepseek", "r1", "reasoning", "o1", "o3")):
            params["reasoning_effort"] = reasoning_effort
    resp = client.chat.completions.create(**params)
    return resp.choices[0].message.content or ""

def save_history(sid: str, user: str, assistant: str):
    if sid not in conversations:
        conversations[sid] = []
    conversations[sid].append({"role": "user",      "content": user})
    conversations[sid].append({"role": "assistant",  "content": assistant})

COMPACT_AFTER = 24   # once a session's history exceeds this many messages...
COMPACT_KEEP  = 12   # ...summarize everything except the most recent N

def compact_history_if_needed(sid: str):
    """Once a session gets long, summarize the older portion into a compact
    note instead of silently dropping it when MAX_HIST truncates — same
    pattern Claude Code itself uses for long-running sessions. Falls back to
    a plain trim (the old behavior) if the summarization call itself fails,
    so a bad response here never blocks the conversation."""
    hist = conversations.get(sid, [])
    if len(hist) <= COMPACT_AFTER:
        return

    old, recent = hist[:-COMPACT_KEEP], hist[-COMPACT_KEEP:]
    transcript = "\n".join(f"{m['role']}: {m['content'][:400]}" for m in old)

    try:
        summary = call_once(
            [{"role": "user", "content":
                "Summarize the key facts, decisions, and context from this "
                f"conversation so far in 2-3 sentences:\n\n{transcript}"}],
            "CHAT", max_tok=300, temp=0.2,
        )
        conversations[sid] = [
            {"role": "user", "content": f"[Earlier in this conversation: {summary}]"},
        ] + recent
    except Exception:
        conversations[sid] = recent  # fail safe — same as the old hard-trim

# ─────────────────────────────────────────────────────────────────────────────
# ██  FILE HANDLING
# ─────────────────────────────────────────────────────────────────────────────
def parse_code_blocks(text: str) -> dict:
    """Pure parsing — no disk writes, no VS Code opens. Extracts FILENAME +
    code-block pairs and the RUN command. Safe to call on intermediate
    staging attempts without any visible side effects."""
    pattern = re.compile(r"FILENAME:\s*(.+?)\s*\n```[\w]*\n([\s\S]+?)```", re.MULTILINE)
    matches = pattern.findall(text)
    if not matches:
        return {"saved": False}
    run = re.search(r"RUN:\s*(.+)", text)
    filenames = [m[0].strip() for m in matches]
    codes = {m[0].strip(): m[1] for m in matches}
    return {
        "saved": True,
        "filename": filenames[0],
        "filenames": filenames,
        "codes": codes,
        "multi_file": len(filenames) > 1,
        "run_cmd": run.group(1).strip() if run else None,
    }

def write_and_open(filenames: list, codes: dict, target_dir, open_in_editor: bool = True):
    """The actual disk-write + VS Code side effects, separated out so
    staging can write to a temp dir silently, and only the real workspace
    write triggers the editor to pop open.

    Every filename is resolved and checked against target_dir before it
    touches disk — pathlib silently discards target_dir if filename is
    absolute (Path("/workspace") / "/etc/passwd" == Path("/etc/passwd")),
    and a bare "../../.." would escape it too. A model output can't be
    trusted to never produce either, so this is enforced here rather than
    hoped for upstream.

    FIX: Returns the list of filenames that were actually written."""
    target_dir = Path(target_dir).resolve()
    safe_filenames = []
    for filename in filenames:
        candidate = (target_dir / filename).resolve()
        if not candidate.is_relative_to(target_dir):
            print(f"🔴 blocked write outside workspace: {filename!r} -> {candidate}")
            continue
        safe_filenames.append(filename)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(codes[filename], encoding="utf-8")

    if open_in_editor and safe_filenames:
        try:
            primary_path = target_dir / safe_filenames[0]
            if sys.platform == "win32":
                subprocess.Popen(["code", str(primary_path)], shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Visual Studio Code", str(primary_path)])
        except Exception:
            pass
    return safe_filenames

def parse_file(text: str, sid: str) -> dict:
    """Backward-compatible wrapper — parses AND writes straight to the real
    workspace, same as before. Existing call sites keep working unchanged.

    FIX: Now reflects which files were actually written after security filtering."""
    parsed = parse_code_blocks(text)
    if not parsed["saved"]:
        return parsed
    safe = write_and_open(parsed["filenames"], parsed["codes"], WORKSPACE)
    parsed["filenames"] = safe
    return parsed

# ── Staging: test before publishing ─────────────────────────────────────
# Same principle as Claude's own scratch-space workflow — write and test in
# a private temp directory first, iterate on failures there where nothing
# is visible or "real" yet, and only copy the verified-working version into
# the actual workspace once it actually runs clean.
STAGING_DIR = Path(tempfile.gettempdir()) / "vanta_staging"

def stage_test_and_finalize(task: str, first_response: str, system_for_fixes: str,
                             max_attempts: int = 4) -> dict:
    parsed = parse_code_blocks(first_response)
    if not parsed["saved"]:
        return {"success": False, "reason": "no_code_found"}

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    filenames, codes, run_cmd = parsed["filenames"], parsed["codes"], parsed["run_cmd"]
    write_and_open(filenames, codes, STAGING_DIR, open_in_editor=False)

    log = []
    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(
                run_cmd, shell=True, cwd=str(STAGING_DIR),
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            # Long-running process (a server, a bot) — can't wait it out,
            # treat as a pass and let the real run happen in the workspace
            write_and_open(filenames, codes, WORKSPACE)
            return {"success": True, "attempts": attempt, "note": "long_running",
                    "filenames": filenames, "codes": codes, "run_cmd": run_cmd, "log": log}

        if result.returncode == 0:
            # Verified working — NOW copy into the real workspace and open it
            write_and_open(filenames, codes, WORKSPACE)
            return {"success": True, "attempts": attempt, "output": result.stdout,
                    "filenames": filenames, "codes": codes, "run_cmd": run_cmd, "log": log}

        log.append({"attempt": attempt, "error": result.stderr[:400]})
        if attempt == max_attempts:
            # Failed every attempt — do NOT publish broken code to the real
            # workspace. Staying honest about failure beats shipping a mess.
            return {"success": False, "attempts": attempt, "log": log,
                    "last_error": result.stderr[:600]}

        code_dump = "\n\n".join(f"FILE {fn}:\n{codes[fn]}" for fn in filenames)
        try:
            fix_response = call_once([
                {"role": "system", "content": system_for_fixes},
                {"role": "user", "content":
                    f"Task: {task}\n\n{code_dump}\n\nError when run:\n{result.stderr}\n\n"
                    f"Fix it. Same FILENAME/code/RUN format, all files."},
            ], "CODE", max_tok=4096, temp=0.1)
        except Exception as e:
            log.append({"attempt": attempt, "fix_call_failed": str(e)})
            return {"success": False, "attempts": attempt, "log": log}

        fixed = parse_code_blocks(fix_response)
        if fixed["saved"]:
            filenames, codes = fixed["filenames"], fixed["codes"]
            run_cmd = fixed["run_cmd"] or run_cmd
            write_and_open(filenames, codes, STAGING_DIR, open_in_editor=False)

    return {"success": False, "attempts": max_attempts, "log": log}

# FIX: run_cmd now updates the command if the fix response provides a new RUN line.
def run_cmd(cmd: str, sid: str, retries: int = 4) -> str:
    for attempt in range(retries):
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=30, cwd=WORKSPACE,
            )
            if proc.returncode == 0:
                return proc.stdout or "✓ Done."
            if attempt < retries - 1:
                socketio.emit("status", {"state": "thinking",
                    "message": f"Auto-fixing error (attempt {attempt+2})…"}, room=sid)
                fix = call_once([
                    {"role": "system", "content": get_system_code("medium")},
                    {"role": "user",   "content":
                        f"Fix this error, output ONLY corrected code:\n\nError:\n{proc.stderr}"},
                ], "CODE", max_tok=2048, temp=0.05)
                parsed = parse_file(fix, sid)
                # FIX: Update cmd if the fix provided a new RUN command
                if parsed.get("run_cmd"):
                    cmd = parsed["run_cmd"]
                time.sleep(1)
            else:
                return f"⚠ Failed after {retries} attempts:\n{proc.stderr[:500]}"
        except subprocess.TimeoutExpired:
            return "⚠ Timed out."
    return "⚠ All retries exhausted."

# ─────────────────────────────────────────────────────────────────────────────
# ██  SOCKET.IO HANDLERS
# ─────────────────────────────────────────────────────────────────────────────
def _run_checklist(sid: str, pending: dict):
    socketio.emit("status", {"state": "thinking",
        "message": "Running production checklist…"}, room=sid)
    try:
        result = call_once([
            {"role": "system", "content": CHECKLIST_SYSTEM},
            {"role": "user", "content": f"File: {pending['filename']}\n\n{pending['code']}"},
        ], "CODE", max_tok=800, temp=0.2)
    except Exception as e:
        socketio.emit("error", {"message": f"Checklist failed: {e}"}, room=sid)
        socketio.emit("status", {"state": "idle"}, room=sid)
        return
    socketio.emit("response", {"text": result, "model": MODEL}, room=sid)
    save_history(sid, "[production checklist]", result)
    checklist_pending[sid] = {**pending, "stage": "post_checklist"}
    socketio.emit("status", {"state": "idle"}, room=sid)


def _run_legal_draft(sid: str, pending: dict):
    socketio.emit("status", {"state": "thinking",
        "message": "Drafting privacy policy + ToS…"}, room=sid)
    try:
        result = call_once([
            {"role": "system", "content": LEGAL_DRAFT_SYSTEM},
            {"role": "user", "content": f"Website file: {pending['filename']}\n\n{pending['code']}"},
        ], "CODE", max_tok=2000, temp=0.3)
    except Exception as e:
        socketio.emit("error", {"message": f"Legal draft failed: {e}"}, room=sid)
        socketio.emit("status", {"state": "idle"}, room=sid)
        return
    socketio.emit("response", {"text": result, "model": MODEL}, room=sid)
    save_history(sid, "[privacy policy + ToS draft]", result)
    socketio.emit("status", {"state": "idle"}, room=sid)


@socketio.on("connect")
def on_connect():
    conversations[request.sid] = []
    awake_sessions[request.sid] = True
    emit("status",    {"state": "idle"})
    emit("workspace", {"path": WORKSPACE})

@socketio.on("disconnect")
def on_disconnect():
    conversations.pop(request.sid, None)
    awake_sessions.pop(request.sid, None)
    checklist_pending.pop(request.sid, None)

@socketio.on("chat")
def handle_chat(data):
    sid  = request.sid
    msg  = data.get("message", "").strip()
    think_mode = bool(data.get("think", False))
    print(f"🔵 handle_chat received: {msg[:60]!r}")
    if not msg:
        return

    # ── Wake-word gate ──────────────────────────────────────────────────────
    if msg.lower() in ("sleep", "go to sleep"):
        awake_sessions[sid] = False
        socketio.emit("status", {"state": "idle", "message": f"{AGENT} is asleep."}, room=sid)
        socketio.emit("response", {"text": f"💤 Going to sleep. Say \"{AGENT}\" to wake me."}, room=sid)
        return

    if not awake_sessions.get(sid, False):
        match = WAKE_PATTERN.match(msg)
        if not match:
            socketio.emit("response", {"text": f"💤 Say \"{AGENT}\" to wake me up."}, room=sid)
            return
        awake_sessions[sid] = True
        msg = msg[match.end():].strip()
        if not msg:
            socketio.emit("response", {"text": "⚡ I'm awake. What do you need?"}, room=sid)
            return

    # ── Checklist follow-up intercept ───────────────────────────────────────
    if sid in checklist_pending:
        pending = checklist_pending.pop(sid)
        stage = pending.get("stage", "build")
        if wants_legal_draft(msg) or (stage == "post_checklist" and wants_checklist(msg)):
            _run_legal_draft(sid, pending)
            return
        if stage == "build" and wants_checklist(msg):
            _run_checklist(sid, pending)
            return
        # Anything else — drop the pending offer, fall through to normal routing

    socketio.emit("status", {"state": "thinking"}, room=sid)

    # ── Parallel: classify + search simultaneously ─────────────────────────
    # This is what makes it feel instant — search doesn't add sequential delay
    needs_knowledge = needs_live_knowledge(msg)
    is_weather = needs_weather(msg)
    if needs_knowledge or is_weather:
        socketio.emit("status", {"state": "learning", "message": "Searching knowledge…"}, room=sid)
    with ThreadPoolExecutor(max_workers=3) as ex:
        mode_f   = ex.submit(detect_mode, msg)
        rag_f    = ex.submit(get_rag, msg)
        # Weather takes the fast real-API path instead of the slow Playwright
        # Google scrape — no reason to launch a browser for a temperature.
        if is_weather:
            weather_f = ex.submit(get_weather, msg)
            google_f = None
        else:
            weather_f = None
            google_f = ex.submit(get_google, msg) if (GOOGLE_OK and needs_knowledge) else None

        mode      = mode_f.result()
        rag_ctx   = rag_f.result()
        weather_ctx = weather_f.result() if weather_f else ""
        google_ctx = google_f.result() if google_f else ""
        # If weather lookup came up empty (no key, city not found), fall back
        # to a regular search rather than silently answering with nothing extra
        if is_weather and not weather_ctx and GOOGLE_OK:
            google_ctx = get_google(msg)

    is_ui = mode == "CODE" and is_ui_task(msg)
    socketio.emit("status", {"state": "thinking", "mode": mode}, room=sid)
    effort = pick_reasoning_effort(mode, is_ui, needs_knowledge, think_mode)
    routed_model = pick_model(effort)
    messages = build_prompt(sid, msg, mode, rag_ctx, weather_ctx or google_ctx, effort)

    # ── Optional thinking pass — streams reasoning before the real answer ──
    # Scoped to the plain chat path only (UI critique loop already does its
    # own multi-pass reasoning, orchestrate has its own progress feed).
    if think_mode:
        socketio.emit("thinking_start", {}, room=sid)
        think_messages = build_thinking_prompt(sid, msg, mode, rag_ctx, google_ctx)
        thought = stream_thinking(sid, think_messages)
        socketio.emit("thinking_done", {}, room=sid)
        if thought:
            # Feed the reasoning back in as private context — never shown
            # again, never saved to memory, just informs the real answer.
            messages[0]["content"] += (
                f"\n\n[Your private reasoning just now — do not repeat it, "
                f"just answer naturally in light of it]\n{thought}"
            )

    # ── UI tasks: 3-pass critique (but stream the final pass) ──────────────
    if is_ui:
        socketio.emit("status", {"state": "thinking", "message": "Generating…"}, room=sid)
        draft = call_once(messages, mode, reasoning_effort=effort)

        socketio.emit("status", {"state": "thinking", "message": "Refining…"}, room=sid)
        crit = call_once([
            {"role": "system",    "content": SYSTEM_UI_CRITIC},
            {"role": "user",      "content": f"Critique:\n\n{draft}"},
        ], "CODE", max_tok=800, temp=0.3, reasoning_effort=effort)

        ref_msgs = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user",      "content": f"Apply these improvements, output COMPLETE final code:\n\n{crit}"},
        ]
        # Stream the final refined version
        final = stream_response(sid, ref_msgs, mode, reasoning_effort=effort)

    else:
        # ── Regular query: stream immediately ─────────────────────────────
        final = stream_response(sid, messages, mode, reasoning_effort=effort, model=routed_model)

    save_history(sid, msg, final)
    compact_history_if_needed(sid)
    socketio.emit("stream_done", {"model": MODEL, "mode": mode}, room=sid)
    socketio.emit("status", {"state": "idle"}, room=sid)

    # Run generated code if applicable
    info = parse_file(final, sid)
    if info.get("run_cmd"):
        socketio.emit("status", {"state": "thinking",
            "message": f"Running…"}, room=sid)
        out = run_cmd(info["run_cmd"], sid)
        if out:
            socketio.emit("stream_chunk", {"chunk": f"\n```\n{out}\n```"}, room=sid)
            socketio.emit("stream_done",  {"model": "Shell"}, room=sid)
        socketio.emit("status", {"state": "idle"}, room=sid)

    if info.get("saved") and is_ui:
        is_standalone_html = (not info.get("multi_file") and
            info["filename"].lower().endswith((".html", ".htm")))

        if is_standalone_html:
            socketio.emit("status", {"state": "thinking",
                "message": "Visual check…"}, room=sid)
            visual_notes = run_visual_critique(
                client, str(Path(WORKSPACE) / info["filename"]))
            if visual_notes and "no visual issues" not in visual_notes.lower():
                socketio.emit("response",
                    {"text": f"👁 Visual check:\n{visual_notes}"}, room=sid)
            socketio.emit("status", {"state": "idle"}, room=sid)
        # Multi-file/server-backed builds (Flask templates, etc.) skip visual
        # critique — a file:// screenshot of a template can't reflect real
        # rendering (Jinja, routes, API calls), so it would just be wrong.

        checklist_pending[sid] = {
            "filename": info["filename"], "code": final, "stage": "build",
        }
        socketio.emit("response", {"text":
            "Want me to run a quick production checklist on this — HTTPS, "
            "input validation, no exposed secrets? I can also draft a "
            "starting privacy policy + ToS afterward if you want one."},
            room=sid)

@socketio.on("chat_tools")
def handle_chat_tools(data):
    """Opt-in testing ground for real tool-calling — completely separate
    from the main 'chat' event above, which is untouched and still works
    exactly as before. Genuinely untested against a live Groq response;
    this is where that gets found out."""
    sid = request.sid
    task = data.get("message", "").strip()
    if not task:
        return
    print(f"🔧 chat_tools received: {task[:60]!r}")
    socketio.emit("status", {"state": "thinking"}, room=sid)
    try:
        result = call_with_tools(sid, task)
        socketio.emit("response", {"text": result}, room=sid)
    except Exception as e:
        print(f"🔴 chat_tools exception: {type(e).__name__}: {e}")
        socketio.emit("error", {"message": f"Tool-calling error: {e}"}, room=sid)
    socketio.emit("status", {"state": "idle"}, room=sid)

@socketio.on("orchestrate")
def handle_orchestrate(data):
    sid = request.sid
    msg = data.get("message", "").strip()
    if not msg or not ORCH_OK:
        socketio.emit("error", {"message": "Orchestrator unavailable."}, room=sid)
        return

    socketio.emit("status", {"state": "thinking"}, room=sid)

    def cb(step, model, status, result=None):
        socketio.emit("orchestration_update",
            {"step": step, "model": model, "status": status}, room=sid)

    try:
        merged = orchestrator.run(msg, progress_callback=cb)
        save_history(sid, msg, merged)
        socketio.emit("orchestration_done", {"merged": merged}, room=sid)
    except Exception as e:
        socketio.emit("error", {"message": str(e)}, room=sid)
    finally:
        socketio.emit("status", {"state": "idle"}, room=sid)

@socketio.on("clear_memory")
def handle_clear():
    conversations[request.sid] = []
    emit("status", {"state": "idle", "message": "Memory cleared."})

# ─────────────────────────────────────────────────────────────────────────────
# ██  HTTP ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", agent_name=AGENT)

@app.route("/transcribe", methods=["POST"])
def transcribe():
    f = request.files.get("audio")
    if not f:
        return jsonify({"error": "No audio"}), 400
    tmp = Path(tempfile.gettempdir()) / f"vanta_ptt_{uuid.uuid4().hex}.webm"
    f.save(str(tmp))
    try:
        with open(tmp, "rb") as fp:
            r = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo", file=fp, response_format="text")
        text = r.strip() if isinstance(r, str) else r.text.strip()
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        tmp.unlink(missing_ok=True)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "model": MODEL,
                    "rag": RAG_OK, "google": GOOGLE_OK, "orch": ORCH_OK})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n{'='*55}")
    print(f"  VANTA v4 — Natural Intelligence Mode")
    print(f"  http://localhost:{port}")
    print(f"  RAG: {'✓' if RAG_OK else '✗'}  Google: {'✓' if GOOGLE_OK else '✗'}  Orch: {'✓' if ORCH_OK else '✗'}  Watcher: {'✓' if WATCHER_OK else '✗'}")
    print(f"{'='*55}\n")

    if WATCHER_OK:
        watcher_daemon = WatcherDaemon(client, MODEL, socketio, agent_name=AGENT)
        watcher_daemon.start()

    socketio.run(app, host="127.0.0.1", port=port, debug=False)
