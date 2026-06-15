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


class TestMarkdownBoldUpstreamFix:
    """v7.2 — strip markdown **bold** from .tex output BEFORE the file
    is saved so downstream PPTX/HTML converters never see the raw
    asterisks. Converts to \\textbf{} so LaTeX still renders it bold."""

    def test_double_asterisks_become_textbf(self):
        text = "**Data Types** can be classified"
        out = _clean_latex_artifacts(text)
        assert "**" not in out
        assert r"\textbf{Data Types}" in out

    def test_multiple_bold_phrases_in_one_line(self):
        text = "**Synchronous**: fast. **Asynchronous**: slow."
        out = _clean_latex_artifacts(text)
        assert "**" not in out
        assert r"\textbf{Synchronous}" in out
        assert r"\textbf{Asynchronous}" in out

    def test_lone_asterisk_preserved(self):
        text = "Mark with * for footnotes."
        out = _clean_latex_artifacts(text)
        # Single asterisk should not match the bold pattern
        assert "Mark with * for footnotes." in out


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


class TestMarkdownItalicUnderscore:
    def test_single_underscore_pair_to_emph(self):
        out = _clean_latex_artifacts("The _k_-means algorithm")
        assert "_k_" not in out
        assert r"\emph{k}" in out

    def test_multiword_italic(self):
        out = _clean_latex_artifacts("an object is a _core object_ here")
        assert r"\emph{core object}" in out

    def test_real_subscript_untouched(self):
        text = "the value $x_i$ and $C_{ij}$"
        assert _clean_latex_artifacts(text) == text

    def test_path_underscores_untouched(self):
        text = ".grounding_cache/figures/data_mining_p01.png"
        assert _clean_latex_artifacts(text) == text

    def test_escaped_underscore_untouched(self):
        text = r"already escaped \_ stays"
        assert _clean_latex_artifacts(text) == text


class TestGuillemetAndEmptyMath:
    def test_guillemets_stripped(self):
        out = _clean_latex_artifacts('<<"a quote">> follows')
        assert "<<" not in out and ">>" not in out
        assert '"a quote"' in out

    def test_nonempty_display_math_preserved(self):
        # Non-empty $$…$$ is left intact in the .tex — the PPTX converter
        # flattens its content to readable unicode. Stripping the fences
        # here would feed bare \frac{…} to the command-stripper.
        text = "the formula $$s(o) = \\frac{a}{b}$$ holds"
        out = _clean_latex_artifacts(text)
        assert "\\frac{a}{b}" in out

    def test_empty_display_math_stripped(self):
        out = _clean_latex_artifacts("text \\[  \\] more")
        assert "\\[" not in out and "\\]" not in out

    def test_orphan_display_delim_stripped(self):
        out = _clean_latex_artifacts("line\n    \\[\n\n    \\]\nmore")
        assert "\\[" not in out and "\\]" not in out


class TestDanglingFigurePromise:
    def test_promise_without_figure_dropped(self):
        from src.slides import _strip_dangling_figure_promises
        frame = (
            "\\begin{frame}\n\\frametitle{T}\n"
            "\\begin{itemize}\n"
            "\\item The steps can be illustrated graphically:\n"
            "\\end{itemize}\n\\end{frame}"
        )
        out = _strip_dangling_figure_promises(frame)
        assert "illustrated graphically" not in out

    def test_caption_with_resolving_figure_kept(self, tmp_path):
        from src.slides import _strip_dangling_figure_promises
        img = tmp_path / "real.png"
        img.write_bytes(b"\x89PNG\r\n")
        frame = (
            "\\begin{frame}\n\\frametitle{T}\n"
            "\\item Core objects are shown below:\n"
            f"\\includegraphics[width=0.5\\textwidth]{{{img}}}\n"
            "\\end{frame}"
        )
        # A figure that resolves on disk → promise text is preserved.
        assert _strip_dangling_figure_promises(frame) == frame

    def test_promise_stripped_when_figure_missing(self):
        from src.slides import _strip_dangling_figure_promises
        frame = (
            "\\begin{frame}\n\\frametitle{T}\n"
            "This figure highlights the cluster formations.\n"
            "\\includegraphics[width=0.5\\textwidth]{/no/such.png}\n"
            "\\end{frame}"
        )
        # Figure path doesn't resolve → dangling reference is stripped.
        assert "This figure highlights" not in _strip_dangling_figure_promises(frame)

    def test_genuine_as_follows_list_kept(self):
        from src.slides import _strip_dangling_figure_promises
        frame = (
            "\\begin{frame}\nThe procedure is as follows:\n"
            "\\begin{enumerate}\n\\item Select k points\n"
            "\\end{enumerate}\n\\end{frame}"
        )
        # "as follows:" is followed by a real list, no figure-promise verb
        assert _strip_dangling_figure_promises(frame) == frame


class TestContentTokensAndSectionOrder:
    def test_content_tokens_drop_filler(self):
        from src.slides import _content_tokens
        toks = _content_tokens("The clustering method shows density reachable points")
        assert "density" in toks and "reachable" in toks
        # generic filler dropped
        assert "clustering" not in toks and "method" not in toks and "the" not in toks

    def test_section_order_numeric(self):
        from src.slides import _section_order_key
        secs = ["13.1 Notes", "10.2 Partitioning", "10.1 Cluster Analysis", "11.1 Advanced"]
        ordered = sorted(enumerate(secs), key=lambda kv: _section_order_key(kv[1], kv[0]))
        assert [s for _, s in ordered][0] == "10.1 Cluster Analysis"
        assert [s for _, s in ordered][-1] == "13.1 Notes"

    def test_unnumbered_section_sorts_last(self):
        from src.slides import _section_order_key
        assert _section_order_key("References", 0) > _section_order_key("10.6 Eval", 99)


class TestFigureCaptionInjection:
    def test_caption_map_from_chunks(self):
        from src.slides import _build_figure_caption_map
        class _C:
            def __init__(self, text, page): self.text = text; self.page_start = page
        chunks = [_C("Figure 10.2 The k-means partitioning algorithm. More text.", 491)]
        m = _build_figure_caption_map(chunks)
        assert 491 in m
        assert m[491][0][0] == "10.2"
        assert "k-means partitioning algorithm" in m[491][0][1]

    def test_caption_for_path_by_page(self):
        from src.slides import _caption_for_figure_path
        cmap = {491: [("10.2", "The k-means partitioning algorithm")]}
        cap = _caption_for_figure_path("x/data_mining_p0491_09.png", cmap)
        assert cap == "Figure 10.2: The k-means partitioning algorithm"

    def test_caption_for_path_nearby_page(self):
        from src.slides import _caption_for_figure_path
        cmap = {510: [("10.14", "Density-reachability")]}
        # path page 511 should match page 510 (±1 window)
        assert "10.14" in _caption_for_figure_path("a/han_p0511_01.png", cmap)

    def test_inject_only_when_missing(self, tmp_path):
        from src.slides import _inject_missing_figure_captions
        cmap = {491: [("10.2", "The k-means partitioning algorithm")]}
        img = tmp_path / "data_mining_p0491_01.png"
        img.write_bytes(b"\x89PNG\r\n")
        # bare figure that resolves on disk → caption injected
        bare = f"\\includegraphics[width=0.5\\textwidth]{{{img}}}\n"
        out = _inject_missing_figure_captions(bare, cmap)
        assert "\\caption{Figure 10.2: The k-means partitioning algorithm}" in out
        # already-captioned figure → untouched
        capd = (f"\\includegraphics{{{img}}}\n\\caption{{Writer's own caption}}\n")
        out2 = _inject_missing_figure_captions(capd, cmap)
        assert out2.count("\\caption{") == 1
        assert "Writer's own caption" in out2

    def test_no_caption_for_missing_image(self):
        from src.slides import _inject_missing_figure_captions
        cmap = {491: [("10.2", "The k-means partitioning algorithm")]}
        # path doesn't resolve → no caption (avoids orphan caption)
        bare = "\\includegraphics{/no/such/data_mining_p0491_01.png}\n"
        assert "\\caption" not in _inject_missing_figure_captions(bare, cmap)

    def test_no_caption_for_equation_crop(self, tmp_path):
        from src.slides import _inject_missing_figure_captions
        cmap = {491: [("10.2", "The k-means partitioning algorithm")]}
        img = tmp_path / "data_mining_p0491_01.png"
        img.write_bytes(b"\x89PNG\r\n")
        bare = f"\\includegraphics{{{img}}}\n"
        # filename NOT in the real-figure allowlist → treated as equation
        out = _inject_missing_figure_captions(bare, cmap, figure_filenames=set())
        assert "\\caption" not in out

    def test_inject_noop_without_map(self):
        from src.slides import _inject_missing_figure_captions
        text = "\\includegraphics{x/p0491_01.png}\n"
        assert _inject_missing_figure_captions(text, {}) == text


class TestOutlineDedupe:
    def test_drops_duplicate_titles(self):
        from src.slides import _dedupe_outline_titles
        outline = [
            {"title": "Applications of Cluster Analysis", "description": "a"},
            {"title": "K-Means Algorithm", "description": "b"},
            {"title": "applications of cluster analysis!", "description": "c"},
        ]
        out = _dedupe_outline_titles(outline)
        assert len(out) == 2
        assert [o["title"] for o in out] == [
            "Applications of Cluster Analysis", "K-Means Algorithm"]

    def test_keeps_distinct_titles(self):
        from src.slides import _dedupe_outline_titles
        outline = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
        assert len(_dedupe_outline_titles(outline)) == 3

    def test_real_figure_filenames_excludes_equations(self):
        from src.slides import _build_real_figure_filenames

        class _C:
            def __init__(self, text, kinds):
                self.text = text
                self.kinds = set(kinds)
        chunks = [
            _C("[IMAGE_PATH: a/fig_p01_01.png]", {"figure_cap"}),
            _C("[IMAGE_PATH: a/eq_p02_01.png]", {"equation"}),
        ]
        names = _build_real_figure_filenames(chunks)
        assert "fig_p01_01.png" in names
        assert "eq_p02_01.png" not in names
