"""
Visual critique — the screenshot half of UI quality checking.

The existing 3-pass loop (generate -> critique -> refine) only ever reads
CODE, never actually looks at the rendered page. This module closes that
gap with a lightweight 2-shot approach: one screenshot at page load, one
~500ms later, sent to a vision-capable model together. This catches real
rendering bugs (overlapping text, broken layout, invisible elements) that
code-only review can't see — without the cost of full frame-by-frame
animation capture, which would burn through Groq's free tier fast.

Vision model note: qwen/qwen3.6-27b is Groq's current vision-capable
option, but it's explicitly a preview model per Groq's own docs — it can
change or be pulled with little warning. This is why it's scoped to ONLY
this one feature rather than used as the project's main model.
"""

import base64
import os
import time
from pathlib import Path

from orchestrator.openrouter_router import OpenRouterClient


VISION_MODEL = "qwen/qwen3.6-27b"

VISUAL_CRITIQUE_SYSTEM = """You are a meticulous visual QA engineer reviewing
a webpage. You'll see two screenshots of the same page: one at load, one
about 500ms later. Compare them and identify real visual problems only:

- Overlapping or cut-off text/elements
- Broken layout (misaligned, wrong position, overflow)
- Poor contrast (text hard to read against its background)
- Elements that should be visible but aren't
- Animation that looks broken or jarring between the two frames
- Anything that reads as a rendering bug, not a design choice

If it genuinely looks correct, say so briefly — don't invent problems.
Output a short numbered list of real issues, or "No visual issues found"
if it's clean. Be specific about what's wrong and where."""


def _screenshot_pair(file_path: str):
    """Two screenshots of a local HTML file: load state, ~500ms later.
    Returns (bytes, bytes) or None if Playwright isn't available/fails."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    file_url = f"file:///{Path(file_path).resolve().as_posix()}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(file_url, wait_until="domcontentloaded", timeout=15000)
            shot1 = page.screenshot(full_page=True)
            time.sleep(0.5)
            shot2 = page.screenshot(full_page=True)
            browser.close()
            return shot1, shot2
    except Exception as e:
        print(f"[Visual critique] Screenshot failed: {e}")
        return None


def _critique_screenshots(groq_client, shot1: bytes, shot2: bytes) -> str:
    b64_1 = base64.b64encode(shot1).decode()
    b64_2 = base64.b64encode(shot2).decode()
    try:
        resp = groq_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": VISUAL_CRITIQUE_SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": "Screenshot 1 — page load:"},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64_1}"}},
                    {"type": "text", "text": "Screenshot 2 — ~500ms later:"},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64_2}"}},
                ]},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[Visual critique unavailable: {e}]"


def _critique_screenshots_openrouter(
    openrouter_client: OpenRouterClient, shot1: bytes, shot2: bytes
) -> str:
    """FIXED: Use complete() directly instead of execute() which does not
    support vision content or the extra kwargs that were being passed."""
    b64_1 = base64.b64encode(shot1).decode()
    b64_2 = base64.b64encode(shot2).decode()
    content = [
        {"type": "text", "text": "Screenshot 1 — page load:"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_1}"}},
        {"type": "text", "text": "Screenshot 2 — ~500ms later:"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_2}"}},
    ]
    model = os.getenv("VISION_CRITIQUE_MODEL", "").strip() or VISION_MODEL
    try:
        resp = openrouter_client.complete(
            model=model,
            messages=[
                {"role": "system", "content": VISUAL_CRITIQUE_SYSTEM},
                {"role": "user", "content": content},
            ],
            max_tokens=600,
            temperature=0.2,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[Visual critique via OpenRouter failed: {e}]"


def run_visual_critique(groq_client, file_path: str):
    """Full pipeline: screenshot -> vision critique.
    Returns the critique text, or None if screenshots couldn't be taken
    (Playwright missing/not installed — fails silently, doesn't block the build)."""
    shots = _screenshot_pair(file_path)
    if not shots:
        return None

    try:
        openrouter_client = OpenRouterClient.from_env()
        if openrouter_client is not None:
            return _critique_screenshots_openrouter(
                openrouter_client, shots[0], shots[1]
            )
    except Exception as e:
        print(f"[Visual critique] OpenRouter failed, falling back to Groq: {e}")

    return _critique_screenshots(groq_client, shots[0], shots[1])
