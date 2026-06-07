"""Tests for v7 Step 1 LaTeX cleanup (fixes v6 PDF-conversion failures)."""

from __future__ import annotations

from src.slides import _clean_latex_artifacts


class TestFakeIncludegraphicsPath:
    def test_strips_path_to_placeholder(self):
        text = (
            "Slide content.\n"
            "\\includegraphics[width=0.55\\textwidth]{/path/to/file.png}\n"
            "More content.\n"
        )
        out = _clean_latex_artifacts(text)
        assert "/path/to/file.png" not in out
        assert "\\includegraphics" not in out
        assert "Slide content." in out
        assert "More content." in out

    def test_keeps_real_paths(self):
        # Real grounding_cache paths must survive
        text = (
            "Real figure:\n"
            "\\includegraphics[width=0.55\\textwidth]{/Users/x/.grounding_cache/figures/p0017.png}\n"
        )
        out = _clean_latex_artifacts(text)
        assert ".grounding_cache/figures/p0017.png" in out
        assert "\\includegraphics" in out

    def test_strips_your_path_placeholder(self):
        text = "\\includegraphics{(your image path here)}"
        out = _clean_latex_artifacts(text)
        assert "(your" not in out

    def test_handles_no_options(self):
        text = "\\includegraphics{/path/to/foo.png}"
        out = _clean_latex_artifacts(text)
        assert "\\includegraphics" not in out


class TestBibtexCiteUnwrap:
    def test_unwraps_cite_to_brackets(self):
        # v7 chain: \cite{token} -> [token] -> \texttt{[escaped-token]}
        text = "Claim text \\cite{han_data_mining_3e:ch1.s1:p01} and more."
        out = _clean_latex_artifacts(text)
        assert "\\cite{" not in out
        # Citation token survives in texttt-wrapped, underscore-escaped form
        assert r"\texttt{[han\_data\_mining\_3e:ch1.s1:p01]}" in out

    def test_unwraps_multiple(self):
        text = (
            "Claim A \\cite{han_data_mining_3e:ch2.s2:p05}. "
            "Claim B \\cite{han_data_mining_3e:ch6.s2:p08}."
        )
        out = _clean_latex_artifacts(text)
        assert "\\cite{" not in out
        assert r"\texttt{[han\_data\_mining\_3e:ch2.s2:p05]}" in out
        assert r"\texttt{[han\_data\_mining\_3e:ch6.s2:p08]}" in out

    def test_leaves_non_textbook_cite_alone(self):
        # A cite to a real BibTeX entry (rare here but safe)
        text = "Per \\cite{Smith2021} the approach works."
        out = _clean_latex_artifacts(text)
        # Smith2021 doesn't match our textbook pattern → leave alone
        assert "\\cite{Smith2021}" in out


class TestAmpersandEscaping:
    def test_escapes_bare_ampersand_in_text(self):
        text = "\\begin{frame}\nSegments customers by behavior & demographics.\n\\end{frame}"
        out = _clean_latex_artifacts(text)
        assert "behavior \\& demographics" in out

    def test_preserves_tabular_ampersand(self):
        text = (
            "\\begin{tabular}{|c|c|c|}\n"
            "A & B & C \\\\\n"
            "1 & 2 & 3 \\\\\n"
            "\\end{tabular}"
        )
        out = _clean_latex_artifacts(text)
        # Tabular ampersands must stay raw
        assert "A & B & C" in out
        assert "A \\& B" not in out

    def test_preserves_already_escaped_ampersand(self):
        text = "Q\\&A session"
        out = _clean_latex_artifacts(text)
        # Already-escaped ampersand should not double-escape
        assert "Q\\&A" in out
        assert "Q\\\\&A" not in out

    def test_preserves_align_ampersand(self):
        text = "\\begin{align}\nx & = y + z \\\\\na & = b\n\\end{align}"
        out = _clean_latex_artifacts(text)
        assert "x & = y" in out  # math-mode ampersand preserved

    def test_skips_comment_lines(self):
        # Comments contain text the user wrote about ampersands; don't touch
        text = "% Note: see Q&A section below\nActual & content"
        out = _clean_latex_artifacts(text)
        assert "% Note: see Q&A section below" in out
        assert "Actual \\& content" in out


class TestUnicodeReplacement:
    def test_em_dash_becomes_triple_hyphen(self):
        text = "A claim — followed by more text."
        out = _clean_latex_artifacts(text)
        assert "—" not in out
        assert "A claim --- followed by more text." in out

    def test_en_dash_becomes_double_hyphen(self):
        text = "Range 5–10 inclusive."
        out = _clean_latex_artifacts(text)
        assert "–" not in out
        assert "Range 5--10 inclusive." in out

    def test_curly_double_quotes(self):
        text = "He said “hello world” to me."
        out = _clean_latex_artifacts(text)
        assert "“" not in out
        assert "”" not in out
        assert "``hello world''" in out

    def test_curly_single_quotes(self):
        text = "It‘s a wrap’."
        out = _clean_latex_artifacts(text)
        assert "‘" not in out
        assert "’" not in out
        assert "It`s a wrap'." in out

    def test_ellipsis_becomes_ldots(self):
        text = "And so on…"
        out = _clean_latex_artifacts(text)
        assert "…" not in out
        assert "\\ldots{}" in out

    def test_ascii_only_text_untouched(self):
        text = "Plain ASCII content, no unicode here."
        out = _clean_latex_artifacts(text)
        assert out == text


class TestCitationTokenEscaping:
    def test_token_in_text_wrapped_in_texttt(self):
        text = "Per [han_data_mining_3e:ch1.s1:p01] the topic..."
        out = _clean_latex_artifacts(text)
        assert r"\texttt{[han\_data\_mining\_3e:ch1.s1:p01]}" in out

    def test_underscores_escaped_in_token(self):
        text = "[han_data_mining_3e:ch6.s2:p08]"
        out = _clean_latex_artifacts(text)
        # Three underscores in 'han_data_mining_3e' all escaped
        assert r"han\_data\_mining\_3e" in out

    def test_already_wrapped_token_not_double_wrapped(self):
        text = r"\texttt{[han_data_mining_3e:ch1.s1:p01]}"
        out = _clean_latex_artifacts(text)
        # Should NOT have \texttt{\texttt{...}}
        assert r"\texttt{\texttt{" not in out

    def test_page_range_token_wrapped(self):
        # Multi-page chunks have p15-p17 format
        text = "Per [han_data_mining_3e:ch3.s4:p15-p17] the formula..."
        out = _clean_latex_artifacts(text)
        assert r"\texttt{[han\_data\_mining\_3e:ch3.s4:p15-p17]}" in out

    def test_non_textbook_brackets_untouched(self):
        # Square brackets that aren't citation tokens (LaTeX options, etc.)
        text = "\\begin{frame}[fragile]\n[Just some bracketed text]\n"
        out = _clean_latex_artifacts(text)
        assert "[fragile]" in out  # LaTeX optional arg preserved
        # Plain bracketed text not matching citation pattern preserved
        assert "[Just some bracketed text]" in out


class TestGraphicspathInjection:
    def test_graphicspath_inserted_after_graphicx(self):
        text = (
            "\\documentclass{beamer}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{amsmath}\n"
            "\\begin{document}\n"
            "\\end{document}\n"
        )
        out = _clean_latex_artifacts(text)
        assert "\\graphicspath" in out
        # Should appear AFTER \usepackage{graphicx}
        graphicx_pos = out.find("\\usepackage{graphicx}")
        graphicspath_pos = out.find("\\graphicspath")
        assert graphicspath_pos > graphicx_pos

    def test_graphicspath_not_double_injected(self):
        text = (
            "\\usepackage{graphicx}\n"
            "\\graphicspath{{my/path/}}\n"
            "Content."
        )
        out = _clean_latex_artifacts(text)
        # Should NOT add a second graphicspath
        assert out.count("\\graphicspath") == 1
        # The user's path should be preserved
        assert "{my/path/}" in out

    def test_graphicspath_not_added_without_graphicx(self):
        text = "\\documentclass{article}\n\\begin{document}\nContent.\n\\end{document}"
        out = _clean_latex_artifacts(text)
        # No graphicx means no graphicspath needed
        assert "\\graphicspath" not in out


class TestVLMMarkerLeakage:
    """When the VLM extractor produces [DESCRIPTION:] / [INSIGHT:] /
    [IMAGE_PATH:] / [LATEX:] / [TABLE:] / [ALGORITHM_STEPS:] markers,
    the writer is supposed to consume them. When it copies them verbatim
    into the LaTeX, they leak onto the rendered slide as ugly raw text.
    The cleanup pass strips them."""

    def test_description_marker_stripped(self):
        text = (
            'Slide content: "Fig.1: Example [DESCRIPTION: The figure '
            'shows a diagram.] [INSIGHT: It illustrates structure.]"'
        )
        out = _clean_latex_artifacts(text)
        assert "[DESCRIPTION:" not in out
        assert "[INSIGHT:" not in out
        # Surrounding text preserved
        assert "Slide content" in out
        assert "Fig.1: Example" in out

    def test_image_path_marker_stripped(self):
        text = (
            "See the figure: [IMAGE_PATH: /tmp/cache/fig.png] which shows X."
        )
        out = _clean_latex_artifacts(text)
        assert "[IMAGE_PATH:" not in out
        assert "See the figure:" in out
        assert "which shows X." in out

    def test_latex_marker_stripped(self):
        # Math markers from VLM should also be stripped when they leak as text
        text = "Per equation [LATEX: f = ma] the relation holds."
        out = _clean_latex_artifacts(text)
        assert "[LATEX:" not in out
        assert "Per equation" in out
        assert "the relation holds." in out

    def test_table_marker_stripped(self):
        text = "See [TABLE: |A|B|\n|1|2|] for the values."
        out = _clean_latex_artifacts(text)
        assert "[TABLE:" not in out

    def test_algorithm_steps_marker_stripped(self):
        text = "Algorithm: [ALGORITHM_STEPS: 1. init; 2. iterate; 3. stop.] is standard."
        out = _clean_latex_artifacts(text)
        assert "[ALGORITHM_STEPS:" not in out

    def test_real_citation_tokens_preserved(self):
        # Citation tokens follow [textbook_id:chN.sM:pXX] shape and must
        # survive (they're wrapped in \texttt{} by the citation pass with
        # escaped underscores).
        text = "Per [han_data_mining_3e:ch1.s1:p01] the topic is studied."
        out = _clean_latex_artifacts(text)
        assert r"\texttt{[han\_data\_mining\_3e:ch1.s1:p01]}" in out

    def test_case_insensitive_strip(self):
        # Some VLM outputs use mixed case
        text = "[description: a figure showing X] and [Insight: it teaches Y]"
        out = _clean_latex_artifacts(text)
        assert "description:" not in out.lower() or "[" not in out
        # Both markers gone
        assert "[Insight:" not in out
        assert "[description:" not in out

    def test_nested_brackets_in_marker_handled(self):
        # VLM descriptions sometimes contain inner brackets [['supervisor']]
        text = (
            "[DESCRIPTION: The figure shows a 'Multi-Agent Team' with a "
            "'Supervisor' and three 'Specialist' agents.] Following text."
        )
        out = _clean_latex_artifacts(text)
        assert "[DESCRIPTION:" not in out
        assert "Following text." in out


class TestEdgeCases:
    def test_empty_text_no_op(self):
        assert _clean_latex_artifacts("") == ""
        assert _clean_latex_artifacts(None) is None

    def test_clean_text_unchanged(self):
        text = "\\begin{frame}\\frametitle{Title}\nClean content.\n\\end{frame}"
        out = _clean_latex_artifacts(text)
        assert out == text

    def test_combined_fixes(self):
        # Multiple issues at once — all should be fixed
        text = (
            "\\begin{frame}\n"
            "Per \\cite{han_data_mining_3e:ch1.s1:p01} the topic A & B is studied.\n"
            "\\includegraphics{/path/to/file.png}\n"
            "\\end{frame}"
        )
        out = _clean_latex_artifacts(text)
        # v7 chain: cite-unwrap → texttt-wrap with escaped underscores
        assert r"\texttt{[han\_data\_mining\_3e:ch1.s1:p01]}" in out
        assert "\\cite{" not in out
        assert "A \\& B" in out
        assert "\\includegraphics" not in out
