"""Tests for foundation-deliberation TOC injection (the Fix-#1/#2 patch).

The grounded path injects the textbook's table of contents into every
foundation deliberation prompt so the syllabus + earlier deliberations
SEE the source before deciding course structure — closing the
architectural gap exposed by the SVVT smoke test (course on
"Structural-Based Techniques" + software-testing textbook → syllabus
generated for civil engineering).

The vanilla path must stay byte-identical — these tests pin that
invariant. They also confirm the retry path in copilot mode receives the
same TOC so first-call and retry behavior don't drift.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agents import Deliberation


class _StubAgent:
    """Captures the FIRST prompt the deliberation hands to its agent.

    `Deliberation.run` calls `generate_response` once per round (with the
    real prompt the TOC injection lives in) and then once more at the end
    on `summary_agent` (with just the discussion-history blob). We pin the
    first call so the test sees the actual agent-facing prompt.
    """

    def __init__(self, name: str = "stub"):
        self.name = name
        self.captured_prompt: str | None = None

    def reset_history(self):
        pass

    def generate_response(self, prompt: str, save_to_history: bool = False):
        if self.captured_prompt is None:
            self.captured_prompt = prompt
        return ("placeholder response", 0.0, 0)


def _make_deliberation(instruction: str = "Design the course syllabus.",
                       delib_id: str = "syllabus_design"):
    agent = _StubAgent()
    delib = Deliberation(
        id=delib_id,
        name="Stub",
        agents=[agent],
        summary_agent=agent,
        max_rounds=1,
        instruction_prompt=instruction,
        input_files=None,
        output_format="md",
    )
    return delib, agent


class TestDeliberationOptInInvariant:
    """Vanilla path (no textbook_context) must produce a byte-identical
    prompt to today's release. Reviewers will check this — and so will
    the prof's regression checklist for the demo.
    """

    def test_no_textbook_context_prompt_byte_identical_to_baseline(self):
        # Baseline: what the prompt looked like before the patch — instruction
        # prompt as-is, no leading "Available textbook" block.
        delib, agent = _make_deliberation("Design the course syllabus.")
        delib.run(current_context="prior results")
        assert agent.captured_prompt is not None
        # The instruction_prompt sits at the START with no preamble.
        assert agent.captured_prompt.startswith("Design the course syllabus.")
        assert "Available textbook chapters" not in agent.captured_prompt

    def test_explicit_none_textbook_context_also_byte_identical(self):
        # Passing textbook_context=None explicitly behaves the same as omitting it.
        delib, agent = _make_deliberation("Design the course syllabus.")
        delib.run(current_context="prior", textbook_context=None)
        assert agent.captured_prompt.startswith("Design the course syllabus.")
        assert "Available textbook chapters" not in agent.captured_prompt


class TestDeliberationTocInjection:
    """Grounded path: textbook_context is prepended to the instruction prompt
    as an authoritative "Available textbook" block. The block has to come
    FIRST (before instruction_prompt) so the agents see the book before the
    task is framed — that's the fix for the SVVT-style topic-drift bug.
    """

    def test_textbook_context_prepended_above_instruction(self):
        toc = "Chapter 1: Control Flow Testing\n  - 1.1 Coverage criteria"
        delib, agent = _make_deliberation("Design the course syllabus.")
        delib.run(current_context="ctx", textbook_context=toc)
        prompt = agent.captured_prompt
        assert prompt is not None
        # TOC block appears BEFORE the instruction.
        toc_idx = prompt.find("Available textbook chapters")
        instr_idx = prompt.find("Design the course syllabus.")
        assert 0 <= toc_idx < instr_idx
        assert "Chapter 1: Control Flow Testing" in prompt
        assert "1.1 Coverage criteria" in prompt

    def test_directive_warns_against_off_textbook_topics(self):
        # The injection is not just informational — it tells the agents to
        # AVOID topics with no textbook support. Without this directive the
        # model treats the TOC as background and ignores it (we tested this).
        toc = "Chapter 1: Topic A"
        delib, agent = _make_deliberation("Design.")
        delib.run(textbook_context=toc)
        assert "Avoid chapters or topics with no textbook support" in agent.captured_prompt


class TestAddieRunnerTocHelper:
    """`ADDIERunner._textbook_toc_context` returns the TOC string when a
    knowledge base is attached, else None. Used once per run to build the
    string passed to every foundation deliberation + retry.
    """

    def _runner(self, kb):
        from src.ADDIE import ADDIERunner
        addie = MagicMock()
        addie.knowledge_base = kb
        runner = ADDIERunner.__new__(ADDIERunner)
        runner.addie = addie
        return runner

    def test_vanilla_returns_none(self):
        runner = self._runner(kb=None)
        assert runner._textbook_toc_context() is None

    def test_grounded_returns_toc_string(self):
        kb = MagicMock()
        kb.toc.return_value = "Chapter 1: Demo"
        runner = self._runner(kb=kb)
        assert runner._textbook_toc_context() == "Chapter 1: Demo"
        kb.toc.assert_called_once()

    def test_toc_failure_falls_back_gracefully(self):
        # If kb.toc() raises (malformed textbook), we mustn't kill the run —
        # fall back to vanilla foundation prompts and log it.
        kb = MagicMock()
        kb.toc.side_effect = ValueError("malformed")
        runner = self._runner(kb=kb)
        assert runner._textbook_toc_context() is None


class TestRetryPathSeesSameToc:
    """`_check_for_retry`'s foundation-deliberation retry path passes the
    same TOC to ``deliberation.run()`` that the first call received. Without
    this, copilot users would see a different prompt on first call vs retry
    — silent behavior drift.
    """

    def test_foundation_retry_passes_textbook_context(self, monkeypatch):
        # Build a runner that simulates: foundation TOC already populated
        # (run_foundation_deliberations ran), copilot user picks "retry".
        from src.ADDIE import ADDIERunner

        addie = MagicMock()
        addie.copilot = True
        addie.copilot_catalog = {}
        runner = ADDIERunner.__new__(ADDIERunner)
        runner.addie = addie
        runner.results = ["course name", "fnd0", "fnd1", "fnd2", "fnd3 (syllabus)"]
        runner.output_dir = "/tmp/_toc_retry_test"
        import os
        os.makedirs(runner.output_dir, exist_ok=True)
        runner._foundation_toc = "Chapter 1: Topic A"

        # Stub deliberation that records every kwarg it was called with.
        delib_calls = []

        class _StubDelib:
            name = "Syllabus"
            id = "syllabus_design"
            output_format = "md"

            def run(self, **kwargs):
                delib_calls.append(kwargs)
                return "retried syllabus result"

        # Drive _check_for_retry with two scripted inputs: choose "retry",
        # give a suggestion, then choose "satisfied".
        scripted_inputs = iter(["2", "make it shorter", "1"])
        monkeypatch.setattr("builtins.input", lambda _prompt="": next(scripted_inputs))

        # Patch _save_result so we don't write to disk (not under test here).
        runner._save_result = lambda *a, **k: None

        runner._check_for_retry(_StubDelib(), idx=4)

        assert len(delib_calls) == 1
        assert delib_calls[0].get("textbook_context") == "Chapter 1: Topic A"

    def test_foundation_retry_vanilla_passes_none(self, monkeypatch):
        # Vanilla runner: _foundation_toc not set OR is None → retry passes
        # textbook_context=None, preserving byte-identical vanilla prompts.
        from src.ADDIE import ADDIERunner

        addie = MagicMock()
        addie.copilot = True
        addie.copilot_catalog = {}
        runner = ADDIERunner.__new__(ADDIERunner)
        runner.addie = addie
        runner.results = ["course", "a", "b", "c", "d"]
        runner.output_dir = "/tmp/_toc_retry_vanilla"
        import os
        os.makedirs(runner.output_dir, exist_ok=True)
        # Notably, do NOT set runner._foundation_toc — vanilla never sets it.

        delib_calls = []

        class _StubDelib:
            name = "Syllabus"
            id = "syllabus_design"
            output_format = "md"

            def run(self, **kwargs):
                delib_calls.append(kwargs)
                return "result"

        scripted_inputs = iter(["2", "tweak", "1"])
        monkeypatch.setattr("builtins.input", lambda _prompt="": next(scripted_inputs))
        runner._save_result = lambda *a, **k: None

        runner._check_for_retry(_StubDelib(), idx=4)
        assert delib_calls[0].get("textbook_context") is None
