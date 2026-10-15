"""Tests for SlideUtils in src/slides.py"""

import pytest
from unittest.mock import patch


with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
    with patch("openai.OpenAI"):
        from src.slides import SlideUtils, SlidesDeliberation


class TestSlideUtils:
    """Tests for the SlideUtils utility class."""

    def test_get_latex_template_default(self):
        template = SlideUtils.get_latex_template()
        assert "\\documentclass{beamer}" in template
        assert "\\begin{document}" in template
        assert "\\end{document}" in template
        assert "\\usetheme{Madrid}" in template

    def test_parse_latex_template_standard(self):
        template = (
            "\\documentclass{beamer}\n"
            "\\begin{document}\n"
            "content\n"
            "\\end{document}"
        )
        prefix, suffix = SlideUtils.parse_latex_template(template)
        assert prefix.endswith("\\begin{document}")
        assert suffix.startswith("\\end{document}")

    def test_parse_latex_template_missing_end(self):
        template = "\\documentclass{beamer}\n\\begin{document}\ncontent"
        prefix, suffix = SlideUtils.parse_latex_template(template)
        assert prefix.endswith("\\begin{document}")
        assert "\\end{document}" in suffix

    def test_parse_latex_template_no_structure(self):
        template = "some raw content"
        prefix, suffix = SlideUtils.parse_latex_template(template)
        assert "\\begin{document}" in prefix
        assert "\\end{document}" in suffix

    def test_extract_latex_frames_single(self):
        source = r"""
\begin{frame}[fragile]
    \frametitle{Test}
    Content here
\end{frame}
"""
        frames = SlideUtils.extract_latex_frames(source)
        assert len(frames) == 1
        assert "\\frametitle{Test}" in frames[0]

    def test_extract_latex_frames_multiple(self):
        source = r"""
\begin{frame}
    \frametitle{Frame 1}
    Content 1
\end{frame}

\begin{frame}
    \frametitle{Frame 2}
    Content 2
\end{frame}

\begin{frame}
    \frametitle{Frame 3}
    Content 3
\end{frame}
"""
        frames = SlideUtils.extract_latex_frames(source)
        assert len(frames) == 3

    def test_extract_latex_frames_empty(self):
        source = "No frames here, just text."
        frames = SlideUtils.extract_latex_frames(source)
        assert frames == []

    def test_compile_latex_document(self):
        prefix = "\\documentclass{beamer}\n\\begin{document}"
        frames = [
            "\\begin{frame}\n\\frametitle{A}\nContent A\n\\end{frame}",
            "\\begin{frame}\n\\frametitle{B}\nContent B\n\\end{frame}",
        ]
        suffix = "\\end{document}"

        result = SlideUtils.compile_latex_document(prefix, frames, suffix)
        assert "\\documentclass{beamer}" in result
        assert "\\begin{document}" in result
        assert "\\end{document}" in result
        assert "Content A" in result
        assert "Content B" in result

    def test_compile_latex_document_preserves_order(self):
        prefix = "\\documentclass{beamer}\n\\begin{document}"
        frames = ["\\begin{frame}\nFirst\n\\end{frame}", "\\begin{frame}\nSecond\n\\end{frame}"]
        suffix = "\\end{document}"

        result = SlideUtils.compile_latex_document(prefix, frames, suffix)
        assert result.index("First") < result.index("Second")

    def test_generate_latex_frame_prompt(self):
        prompt = SlideUtils.generate_latex_frame_prompt(
            title="Intro to ML",
            content="Machine learning is a field of AI.",
        )
        assert "Intro to ML" in prompt
        assert "Machine learning" in prompt
        assert "exactly one Beamer frame" in prompt
        assert "multiple frames" not in prompt
        assert "Part X" not in prompt
        assert "Never nest itemize/enumerate environments more than 3 levels" in prompt
        assert "Never nest display-math environments" in prompt
        assert "at most one lstlisting environment" in prompt
        assert "separate code block under every numbered step" in prompt

    def test_generate_latex_frame_prompt_with_feedback(self):
        prompt = SlideUtils.generate_latex_frame_prompt(
            title="Test",
            content="Content",
            user_feedback={"slides": "Add more examples", "overall": "Good"},
        )
        assert "Add more examples" in prompt
        assert "Good" in prompt

    def test_generate_latex_frame_prompt_with_description(self):
        prompt = SlideUtils.generate_latex_frame_prompt(
            title="Test",
            content="Content",
            description="Overview of the topic",
        )
        assert "Overview of the topic" in prompt

    def test_legacy_checkpoint_is_rejected(self, tmp_path):
        deliberation = SlidesDeliberation(
            id="slides",
            name="Slides",
            agents={},
            llm=None,
            output_dir=str(tmp_path),
        )
        (tmp_path / deliberation.CHECKPOINT_FILENAME).write_text(
            '{"version":1,"latex_dict":{"0":{"frames":[]}}}',
            encoding="utf-8",
        )

        assert deliberation._load_checkpoint() is None
