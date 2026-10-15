"""Tests for the grounded-runtime wiring inside `ADDIE.__init__` and
`ADDIERunner`. Specifically:

1. **Cross-encoder reranker is attached** to the `HybridRetriever` when
   `--use-textbook` is set, and is `None` on the vanilla path.

2. **Admin scaffolding pass** (`_maybe_augment_syllabus_with_admin`) runs
   only when a knowledge base is attached, appends to the syllabus output
   file, and is idempotent across resumed runs.

Both invariants are vanilla-preservation properties: when no textbook is
loaded, the new code paths are no-ops and the system behaves byte-
identically to the pre-PR release.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE = Path("tests/fixtures/mini_textbook.pdf")


# --------------------------------------------------------------------- #
# #1 — Cross-encoder reranker attachment
# --------------------------------------------------------------------- #
@pytest.mark.skipif(
    not FIXTURE.exists(), reason="mini_textbook.pdf fixture missing"
)
class TestCrossEncoderRerankerAttachment:
    """The CrossEncoderReranker should be attached to the retriever when a
    textbook is loaded, and absent when running vanilla.
    """

    def test_reranker_attached_when_textbook_loaded(self, tmp_path):
        # Avoid the OpenAI client requirement during construction. The
        # ADDIE class also instantiates an LLM; patch that to a MagicMock
        # so we don't need a real API key.
        with patch("src.agents.LLM") as MockLLM:
            MockLLM.return_value = MagicMock()
            from src.ADDIE import ADDIE
            addie = ADDIE("Test Course", textbook_path=str(FIXTURE))
        # Retriever exists and has a reranker attached
        assert addie.retriever is not None
        assert addie.retriever.reranker is not None
        # And it's the cross-encoder specifically (not LLMReranker /
        # HashReranker etc.) — verify by class name to avoid importing
        # sentence-transformers in this test.
        assert type(addie.retriever.reranker).__name__ == "CrossEncoderReranker"

    def test_no_retriever_no_reranker_in_vanilla(self):
        # Vanilla path: textbook_path is None → no retriever, no reranker.
        # Confirms the entire grounding stack (including the reranker we
        # just added) is a no-op when grounding is off.
        with patch("src.agents.LLM") as MockLLM:
            MockLLM.return_value = MagicMock()
            from src.ADDIE import ADDIE
            addie = ADDIE("Test Course", textbook_path=None)
        assert addie.retriever is None
        assert addie.knowledge_base is None


# --------------------------------------------------------------------- #
# #3 — Admin scaffolding pass
# --------------------------------------------------------------------- #
class TestMaybeAugmentSyllabusWithAdmin:
    """The admin scaffolding pass appends a 'Course Policies' section to
    the syllabus output FILE when grounding is on, via a generic
    catalog-agnostic LLM call. Vanilla path is a no-op; idempotent across
    resumed runs.
    """

    def _runner(self, *, knowledge_base, output_dir, llm_response):
        """Build an ADDIERunner with minimum wiring to call
        `_maybe_augment_syllabus_with_admin` without spinning up a full ADDIE.
        """
        from src.ADDIE import ADDIERunner
        addie = MagicMock()
        addie.knowledge_base = knowledge_base
        # `LLM.generate_response` returns (text, elapsed, tokens). Mock to
        # the test-supplied response.
        addie.llm.generate_response.return_value = (llm_response, 0.0, 0)
        runner = ADDIERunner.__new__(ADDIERunner)
        runner.addie = addie
        runner.output_dir = str(output_dir)
        return runner

    def test_vanilla_is_a_no_op(self, tmp_path):
        # No knowledge_base attached → method returns early without writing
        # anything, even if a syllabus file exists.
        syllabus = tmp_path / "result_syllabus_design.md"
        syllabus.write_text("# Original Syllabus\n\nWeek 1 content.")
        runner = self._runner(
            knowledge_base=None, output_dir=tmp_path,
            llm_response="this should never be written",
        )
        runner._maybe_augment_syllabus_with_admin()
        # Original syllabus untouched, no sentinel created, no LLM call made.
        assert syllabus.read_text() == "# Original Syllabus\n\nWeek 1 content."
        assert not (tmp_path / "result_syllabus_design.md.pre_admin_scaffolding.bak").exists()
        runner.addie.llm.generate_response.assert_not_called()

    def test_grounded_path_augments_and_preserves_original(self, tmp_path):
        # With a KB attached + a syllabus file on disk, the method calls
        # the LLM, writes the augmented output to the original path, and
        # preserves the original under the sentinel name.
        syllabus = tmp_path / "result_syllabus_design.md"
        original = "# Original Syllabus\n\nWeek 1: Introduction"
        syllabus.write_text(original)
        augmented = (
            "# Original Syllabus\n\nWeek 1: Introduction\n\n"
            "## Course Policies\n\n### Instructor Contact Information\n"
            "[Instructor Name], [Email]\n\n### Grading Policy\n"
        )
        runner = self._runner(
            knowledge_base=MagicMock(), output_dir=tmp_path,
            llm_response=augmented,
        )
        runner._maybe_augment_syllabus_with_admin()
        # The syllabus file now contains the augmented content.
        assert syllabus.read_text() == augmented
        # The sentinel (original backup) exists with the pre-augmentation text.
        sentinel = tmp_path / "result_syllabus_design.md.pre_admin_scaffolding.bak"
        assert sentinel.exists()
        assert sentinel.read_text() == original
        # The LLM was called exactly once.
        runner.addie.llm.generate_response.assert_called_once()
        # generate_response must receive a chat message LIST (the prompt content
        # lives in the first message) — not a bare string.
        messages = runner.addie.llm.generate_response.call_args[0][0]
        assert isinstance(messages, list) and messages[0]["role"] == "user"
        content = messages[0]["content"]
        assert "Week 1: Introduction" in content
        assert "Course Policies" in content

    def test_calls_llm_with_message_list_not_string(self, tmp_path):
        # Regression: the prompt must be passed as a chat message LIST, never a
        # bare string. A string is rejected by the SDK, the error is swallowed
        # below, and the scaffolding is silently skipped (the .bak is never
        # written, so --resume retries the failing call forever). MagicMock
        # accepts any argument type, so assert the format explicitly.
        syllabus = tmp_path / "result_syllabus_design.md"
        syllabus.write_text("# Original Syllabus\n\nWeek 1: Intro")
        runner = self._runner(
            knowledge_base=MagicMock(), output_dir=tmp_path,
            llm_response="# augmented\n\n## Course Policies\n",
        )
        runner._maybe_augment_syllabus_with_admin()
        arg = runner.addie.llm.generate_response.call_args[0][0]
        assert isinstance(arg, list), f"expected a message list, got {type(arg).__name__}"
        assert arg and arg[0].get("role") == "user" and "content" in arg[0]

    def test_resume_skips_when_sentinel_exists(self, tmp_path):
        # Idempotency: a sentinel file from a prior run is sufficient signal
        # not to re-augment. Important so resumed runs don't double-append
        # admin sections.
        syllabus = tmp_path / "result_syllabus_design.md"
        syllabus.write_text("# Already augmented")
        # Pre-create sentinel to simulate a prior augmentation
        sentinel = tmp_path / "result_syllabus_design.md.pre_admin_scaffolding.bak"
        sentinel.write_text("# Original (pre-augmentation)")
        runner = self._runner(
            knowledge_base=MagicMock(), output_dir=tmp_path,
            llm_response="this should never be written",
        )
        runner._maybe_augment_syllabus_with_admin()
        # No LLM call, no rewrite.
        runner.addie.llm.generate_response.assert_not_called()
        assert syllabus.read_text() == "# Already augmented"

    def test_missing_syllabus_file_is_no_op(self, tmp_path):
        # If foundation phase didn't finish (no result_syllabus_design.md
        # on disk), we silently skip — never call the LLM, never write
        # anything.
        runner = self._runner(
            knowledge_base=MagicMock(), output_dir=tmp_path,
            llm_response="never written",
        )
        runner._maybe_augment_syllabus_with_admin()
        runner.addie.llm.generate_response.assert_not_called()
        assert not (tmp_path / "result_syllabus_design.md.pre_admin_scaffolding.bak").exists()

    def test_llm_error_response_leaves_original_unchanged(self, tmp_path):
        # If the LLM returns an error-marked response (the existing error
        # path returns ("Error: ...", 0.0, 0)), we DON'T overwrite the
        # syllabus with the error text — keep the original intact.
        syllabus = tmp_path / "result_syllabus_design.md"
        original = "# Original Syllabus\n\nWeek 1 content."
        syllabus.write_text(original)
        runner = self._runner(
            knowledge_base=MagicMock(), output_dir=tmp_path,
            llm_response="Error: rate-limited by OpenAI",
        )
        runner._maybe_augment_syllabus_with_admin()
        # Original syllabus stays intact; no sentinel written.
        assert syllabus.read_text() == original
        assert not (tmp_path / "result_syllabus_design.md.pre_admin_scaffolding.bak").exists()

    def test_empty_llm_response_leaves_original_unchanged(self, tmp_path):
        # Defensive: empty/whitespace LLM output shouldn't replace a real
        # syllabus with nothing.
        syllabus = tmp_path / "result_syllabus_design.md"
        original = "# Original Syllabus"
        syllabus.write_text(original)
        runner = self._runner(
            knowledge_base=MagicMock(), output_dir=tmp_path,
            llm_response="   \n   \n",
        )
        runner._maybe_augment_syllabus_with_admin()
        assert syllabus.read_text() == original
