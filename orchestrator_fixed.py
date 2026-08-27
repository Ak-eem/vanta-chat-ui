"""orchestrator.py
The brain of multi-model orchestration.
Breaks a task into sub-tasks, routes each to the best model,
executes via OpenRouter by default (or opt-in browser automation),
and merges all results.
"""

import json
import os
from typing import Callable, Optional

from .task_analyzer import analyze_task, should_orchestrate
from .model_router import get_model_list, get_model_info
from .openrouter_router import OpenRouterClient


BROWSER_AUTOMATION = os.getenv("BROWSER_AUTOMATION", "manual").strip().lower() in {
    "auto",
    "on",
}

if BROWSER_AUTOMATION:
    try:
        from .browser_agent import BrowserAgentSync
        BROWSER_OK = True
    except Exception:
        BrowserAgentSync = None
        BROWSER_OK = False
else:
    BrowserAgentSync = None
    BROWSER_OK = False


MERGE_PROMPT = """
You are merging outputs from multiple specialized AI models into one cohesive, production-ready result.

Original user request: {task}

Sub-task results:
{results}

Instructions:
- Combine all outputs into a single, coherent, complete response
- Remove duplications
- Ensure consistency (naming, style, interfaces)
- If multiple code files were produced, organize them clearly with FILENAME: headers
- The merged result should be complete and immediately usable
"""


class VantaOrchestrator:
    def __init__(self, groq_client, model: str):
        self.groq = groq_client
        self.model = model
        self._agent: Optional["BrowserAgentSync"] = None

        # OpenRouter is an optional API path for orchestration calls only.
        # BrowserAgentSync below remains responsible for browser automation.
        self.openrouter = OpenRouterClient.from_env()
        if self.openrouter is not None:
            self.analysis_client = self.openrouter
            self.analysis_model = self.openrouter.flash_model
            self.merge_client = self.openrouter
            # OpenRouter owns transparent Nemotron -> DeepSeek R1 failover;
            # keep the existing analysis/merge wiring unchanged.
            self.merge_model = self.openrouter.brain_model
        else:
            self.analysis_client = groq_client
            self.analysis_model = model
            self.merge_client = groq_client
            self.merge_model = model

    def _get_agent(self) -> "BrowserAgentSync":
        if not BROWSER_OK or BrowserAgentSync is None:
            raise ImportError(
                "playwright not installed. Run: pip install playwright "
                "&& playwright install chromium"
            )
        if self._agent is None:
            self._agent = BrowserAgentSync()
            self._agent.start()
            print("[Orchestrator] Browser agent started.")
        return self._agent

    def run(
        self,
        task: str,
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """Run the complete orchestration pipeline."""

        def emit(step, model, status, result=None):
            if progress_callback:
                progress_callback(step, model, status, result)

        # Step 1: Analyze
        emit("Analyzing task...", "Vanta", "thinking")
        analysis = analyze_task(task, self.analysis_client, self.analysis_model)
        subtasks = analysis.get("subtasks", [])
        emit(f"Found {len(subtasks)} sub-tasks", "Vanta", "done")

        # If it's simple or orchestration isn't needed, handle directly.
        if not should_orchestrate(analysis):
            emit("Simple task — handling locally", "Vanta", "done")
            return self._local_fallback(task)

        # Step 2: Execute sub-tasks through OpenRouter by default. Browser
        # automation is opt-in and is imported/started only when enabled.
        agent = None
        if BROWSER_AUTOMATION:
            try:
                agent = self._get_agent()
            except ImportError as exc:
                emit(str(exc), "System", "error")
                # FIX: Don't return early — fall through to OpenRouter or local fallback
                # so that a missing Playwright install doesn't kill orchestration entirely.

        results = []
        for subtask in sorted(subtasks, key=lambda x: x.get("priority", 99)):
            task_type = subtask["type"]
            description = subtask["description"]
            model_list = get_model_list(task_type)
            best_model = get_model_info(model_list[0])["name"]

            emit(
                f"Sub-task: {task_type} — {description[:50]}...",
                best_model,
                "thinking",
            )

            prompt = (
                f"You are working on a specific part of a larger project.

"
                f"Overall project: {task}

"
                f"Your specific task ({task_type}): {description}

"
                f"Produce a complete, production-ready solution for your part only. "
                f"Be thorough and include all necessary code."
            )

            def on_progress(step, model_name, status, result=None):
                emit(step, model_name, status, result)

            if agent is not None:
                response, model_used = agent.send_with_failover(
                    model_priority=model_list,
                    prompt=prompt,
                    on_progress=on_progress,
                )
            elif self.openrouter is not None:
                response, model_used = self.openrouter.execute(
                    prompt,
                    task_type,
                    on_progress=lambda model_name, status, result=None: emit(
                        f"Sub-task: {task_type}", model_name, status, result
                    ),
                )
            else:
                emit(
                    "OpenRouter is not configured; handling task locally",
                    "Vanta",
                    "error",
                )
                return self._local_fallback(task)

            results.append(
                {
                    "type": task_type,
                    "desc": description,
                    "model": model_used,
                    "response": response,
                }
            )
            emit(
                f"✓ {task_type} done (via {model_used})",
                model_used,
                "done",
            )

        # Step 3: Merge
        emit("Merging all results...", "Vanta", "thinking")
        merged = self._merge(task, results)
        emit("Merge complete.", "Vanta", "done")
        return merged

    def _merge(self, task: str, results: list[dict]) -> str:
        """Use the configured brain model; its client handles transparent failover."""
        results_text = "

".join(
            f"[{r['type'].upper()} — via {r['model']}]
{r['response']}"
            for r in results
        )
        prompt = MERGE_PROMPT.format(task=task, results=results_text)

        try:
            resp = self.merge_client.chat.completions.create(
                model=self.merge_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.2,
            )
            return resp.choices[0].message.content
        except Exception:
            # Safe fallback: preserve every result if the merge provider fails.
            parts = [
                f"### {r['type'].upper()} (via {r['model']})
{r['response']}"
                for r in results
            ]
            return "

---

".join(parts)

    def _local_fallback(self, task: str) -> str:
        """Handle simple tasks directly through the legacy provider."""
        resp = self.groq.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are Vanta, a premium AI coding assistant.",
                },
                {"role": "user", "content": task},
            ],
            max_tokens=4096,
            temperature=0.2,
        )
        return resp.choices[0].message.content
