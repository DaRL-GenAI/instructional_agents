"""Tests for v7.1 \\includegraphics support in LaTeXToPPTXConverter.

Confirms the Python parser:
  - extracts \\includegraphics{...} into an ``image`` SlideElement
  - resolves paths relative to the .tex file's directory
  - silently skips broken paths instead of crashing
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.latex_to_pptx import LaTeXParser, SlideElement


class TestIncludeGraphicsParsing:
    def test_includegraphics_creates_image_element(self, tmp_path):
        # Create a real image file the parser can resolve to
        img = tmp_path / "fig.png"
        img.write_bytes(b"\x89PNG fake")

        tex = (
            r"\begin{document}"
            r"\begin{frame}{Title}"
            rf"\includegraphics[width=0.5\textwidth]{{{img}}}"
            r"\end{frame}"
            r"\end{document}"
        )

        parser = LaTeXParser(source_dir=tmp_path)
        frames = parser.parse(tex)
        assert len(frames) == 1
        # Find the image element
        imgs = [e for e in frames[0].elements if e.type == "image"]
        assert len(imgs) == 1
        # Path should be the absolute one we wrote
        assert Path(imgs[0].content) == img.resolve()

    def test_includegraphics_without_options(self, tmp_path):
        img = tmp_path / "fig.png"
        img.write_bytes(b"PNG")
        tex = (
            r"\begin{document}\begin{frame}{T}"
            rf"\includegraphics{{{img}}}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser(source_dir=tmp_path)
        frames = parser.parse(tex)
        imgs = [e for e in frames[0].elements if e.type == "image"]
        assert len(imgs) == 1

    def test_relative_path_resolved_against_source_dir(self, tmp_path):
        figs = tmp_path / "figs"
        figs.mkdir()
        img = figs / "fig.png"
        img.write_bytes(b"PNG")
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\includegraphics{figs/fig.png}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser(source_dir=tmp_path)
        frames = parser.parse(tex)
        imgs = [e for e in frames[0].elements if e.type == "image"]
        assert len(imgs) == 1
        assert Path(imgs[0].content) == img.resolve()

    def test_path_walking_up_to_grounding_cache(self, tmp_path):
        # Simulate the production layout:
        #   /project_root/
        #     .grounding_cache/figures/fig.png   <- the image
        #     exp/han_b1_v7_default/chapter_1/slides.tex
        root = tmp_path
        gc = root / ".grounding_cache" / "figures"
        gc.mkdir(parents=True)
        img = gc / "fig.png"
        img.write_bytes(b"PNG")
        chapter = root / "exp" / "han_b1_v7_default" / "chapter_1"
        chapter.mkdir(parents=True)
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\includegraphics{.grounding_cache/figures/fig.png}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser(source_dir=chapter)
        frames = parser.parse(tex)
        imgs = [e for e in frames[0].elements if e.type == "image"]
        assert len(imgs) == 1
        assert Path(imgs[0].content) == img.resolve()

    def test_missing_image_silently_skipped(self, tmp_path):
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\includegraphics{nonexistent/missing.png}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser(source_dir=tmp_path)
        frames = parser.parse(tex)
        imgs = [e for e in frames[0].elements if e.type == "image"]
        # Missing image → no image element emitted (no crash)
        assert imgs == []

    def test_multiple_includegraphics_in_one_frame(self, tmp_path):
        img1 = tmp_path / "a.png"
        img1.write_bytes(b"PNG1")
        img2 = tmp_path / "b.png"
        img2.write_bytes(b"PNG2")
        tex = (
            r"\begin{document}\begin{frame}{T}"
            rf"\includegraphics{{{img1}}}"
            r" some text "
            rf"\includegraphics{{{img2}}}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser(source_dir=tmp_path)
        frames = parser.parse(tex)
        imgs = [e for e in frames[0].elements if e.type == "image"]
        assert len(imgs) == 2

    def test_no_source_dir_falls_back_to_cwd(self):
        # When source_dir is None, only cwd-relative + absolute lookups work
        parser = LaTeXParser()
        # Absolute path that doesn't exist → returns None
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\includegraphics{/totally/missing.png}"
            r"\end{frame}\end{document}"
        )
        frames = parser.parse(tex)
        imgs = [e for e in frames[0].elements if e.type == "image"]
        assert imgs == []
