"""
Regression tests for SyllabusProcessor's prompt content.

The bug these tests guard against: a previous version of the prompt
showed `"title": "Chapter 1: Introduction to Machine Learning"` as the
example, with no instruction telling the LLM to preserve the syllabus's
own numbering. On grounded runs whose syllabus contains many
"Readings: Chapter X.Y" textbook references, the LLM started copying
those textbook chapter numbers into the course chapter labels, producing
duplicates like `Chapter 1: ...`, `Chapter 1: ...` (two weeks under the
same textbook chapter). See the chapter-label regression caught
on `feature/textbook-grounding-v2`'s first validation run.

The fix updates the prompt to:
  1. Use "Week 1:" in the example (matches typical syllabus headings).
  2. Explicitly instruct the LLM to use the syllabus's own week labels.
  3. Explicitly instruct the LLM NOT to renumber based on textbook
     readings.

These tests assert those three properties of the prompt.
"""

from unittest.mock import MagicMock

from src.ADDIE import SyllabusProcessor


def _mocked_processor() -> SyllabusProcessor:
    """Build a SyllabusProcessor with a stubbed LLM that returns valid JSON.

    The tests don't care about the JSON content; they care about the
    prompt the processor SENDS to the LLM.
    """
    proc = SyllabusProcessor.__new__(SyllabusProcessor)
    proc.name = "Syllabus Processor"
    proc.role = "Syllabus organizer and formatter"
    proc.system_prompt = ""
    proc.message_history = []
    proc.llm = MagicMock()
    proc.llm.generate_response = MagicMock(
        return_value=('[{"title":"Week 1: t","description":"d"}]', 0.0, {}),
    )
    proc.generate_response = MagicMock(
        return_value=('[{"title":"Week 1: t","description":"d"}]', 0.0, {}),
    )
    proc.reset_history = MagicMock()
    return proc


class TestSyllabusProcessorPrompt:
    """The prompt must steer the LLM to preserve the syllabus's own week
    labels and ignore textbook chapter references in readings."""

    def test_example_uses_week_not_chapter(self):
        """The example in the prompt must show "Week 1: ..." not "Chapter 1: ...".

        Rationale: an LLM under uncertainty mimics example shapes
        literally. Showing it "Chapter 1: ..." biases the output toward
        textbook chapter numbering when the syllabus contains "Readings:
        Chapter X.Y" references.
        """
        proc = _mocked_processor()
        proc.process_syllabus("### Week 1: Intro\n- Readings: Chapter 1")

        call_args = proc.generate_response.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]

        # The example must show a Week-style title
        assert '"title": "Week 1:' in prompt, (
            "Example in prompt should use Week 1: ... not Chapter 1: ..."
        )
        # Belt-and-braces: don't have the old Chapter-1 example
        assert '"title": "Chapter 1: Introduction to Machine Learning"' not in prompt

    def test_prompt_instructs_preserve_syllabus_numbering(self):
        """The prompt must explicitly tell the LLM to use the syllabus's
        own numbering, not invent its own."""
        proc = _mocked_processor()
        proc.process_syllabus("### Week 1: Intro")

        call_args = proc.generate_response.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        prompt_lower = prompt.lower()

        # Look for some variant of "preserve the syllabus's numbering"
        # or "use the exact title from the syllabus"
        assert any(
            phrase in prompt_lower
            for phrase in (
                "preserve the syllabus",
                "use the exact title",
                "exact title from",
                "syllabus's own numbering",
            )
        ), "Prompt should instruct the LLM to preserve the syllabus's own numbering"

    def test_prompt_warns_against_renumbering_by_textbook(self):
        """The prompt must warn the LLM NOT to renumber based on textbook
        chapter references in readings.

        This is the specific failure mode caught on v2: the LLM saw
        "Readings: Chapter 1.1 - 1.2" and used "Chapter 1" as the course
        chapter number, producing duplicate labels across weeks.
        """
        proc = _mocked_processor()
        proc.process_syllabus("### Week 1: Intro\n- Readings: Chapter 1.1 - 1.2")

        call_args = proc.generate_response.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        prompt_lower = prompt.lower()

        assert any(
            phrase in prompt_lower
            for phrase in (
                "do not renumber",
                "must not become",
                "textbook chapter numbers",
            )
        ), (
            "Prompt should explicitly warn against using textbook chapter "
            "numbers from readings as the course chapter numbers"
        )
