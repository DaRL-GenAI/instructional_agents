"""Tests for v7.2 polish fixes in src/latex_to_pptx.py.

Covers:
  - Backtick quote conversion (`` ``...'' `` → "..." and `` `...' `` → '...')
  - Markdown bold/italic stripping (** **, __ __, *...*)
  - Bare $...$ math-fence stripping
  - Empty-item filtering in itemize/enumerate
"""

from __future__ import annotations

import pytest

from src.latex_to_pptx import (
    LaTeXParser,
    strip_bare_math_fences,
    strip_latex_formatting,
    strip_markdown_artifacts,
    unescape_latex,
)


class TestBacktickQuoteConversion:
    def test_double_backtick_double_apostrophe(self):
        out = unescape_latex("``Multi-Agent Collaboration pattern''")
        assert out == '"Multi-Agent Collaboration pattern"'

    def test_single_backtick_apostrophe(self):
        out = unescape_latex("`safe' or `risky'")
        assert "`safe'" not in out
        assert "'safe'" in out
        assert "'risky'" in out

    def test_paragraph_with_multiple_quotes(self):
        out = unescape_latex(
            "He said ``hello'' and then `whispered' something."
        )
        assert '"hello"' in out
        assert "'whispered'" in out
        # No backticks survive in this output
        assert "``" not in out
        assert "''" not in out

    def test_ascii_quotes_unchanged(self):
        # Regular ASCII quotes shouldn't be touched
        out = unescape_latex('He said "hello" and she said "world".')
        assert '"hello"' in out
        assert '"world"' in out


class TestMarkdownBoldStripping:
    def test_double_asterisk_stripped(self):
        out = strip_markdown_artifacts("**Data Types** can be classified")
        assert out == "Data Types can be classified"

    def test_underscore_bold(self):
        out = strip_markdown_artifacts("Per __these results__ we see")
        assert "__" not in out
        assert "these results" in out

    def test_single_asterisk_italic(self):
        out = strip_markdown_artifacts("This is *important* content.")
        assert out == "This is important content."

    def test_does_not_strip_lone_asterisk(self):
        # A literal asterisk (e.g. wildcard, footnote marker) should
        # not match the bold/italic pattern — needs paired delimiters.
        out = strip_markdown_artifacts("Mark with * for footnotes.")
        assert out == "Mark with * for footnotes."

    def test_does_not_eat_multiple_bold_phrases(self):
        # When two distinct bold phrases appear on one line, both
        # should be stripped without consuming the text between them.
        out = strip_markdown_artifacts(
            "**Synchronous Request/Response**: For quick operations. "
            "**Server-Sent Events (SSE)**: For ongoing flows."
        )
        assert "**" not in out
        assert "Synchronous Request/Response" in out
        assert "Server-Sent Events (SSE)" in out

    def test_strips_in_strip_latex_formatting(self):
        # The integrated pipeline should also strip markdown
        out = strip_latex_formatting("**Categorical Data**: examples")
        assert out == "Categorical Data: examples"


class TestBareMathFenceStripping:
    def test_simple_dollar_pair(self):
        out = strip_bare_math_fences("If age $ 30$ look further")
        assert "$" not in out
        assert "30" in out

    def test_two_separate_math_fences(self):
        out = strip_bare_math_fences(
            "If age $ 30$ then check income $ 50K$."
        )
        assert "$" not in out
        assert "30" in out
        assert "50K" in out

    def test_does_not_eat_long_text(self):
        # The fence regex is bounded so it doesn't run away over
        # paragraph boundaries when an unmatched $ appears
        out = strip_bare_math_fences(
            "Cost is $5 per unit and pricing is fair across products."
        )
        # A truly unmatched $ should be left alone if there's nothing
        # closing it. (The pattern requires the second $ within 60 chars.)
        # Here there is no second $ within the limit, so input is unchanged.
        assert "$5 per unit" in out

    def test_integrated_via_strip_latex_formatting(self):
        out = strip_latex_formatting("If age $\\geq 30$ then we have data.")
        assert "$" not in out


class TestEmptyItemFiltering:
    def test_empty_item_dropped(self):
        # \item with no content after it should produce no entry
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\begin{itemize}"
            r"\item First"
            r"\item"
            r"\item Third"
            r"\end{itemize}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser()
        frames = parser.parse(tex)
        # Find the itemize element
        itemize = next(
            (e for e in frames[0].elements if e.type == "itemize"), None
        )
        assert itemize is not None
        # 3 \item tokens in source; the empty one should be dropped
        texts = [it.get("text", "") for it in itemize.items]
        assert "First" in texts
        assert "Third" in texts
        # The empty item should not have produced a bullet entry
        assert "" not in texts or len(texts) == 2

    def test_whitespace_only_item_dropped(self):
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\begin{itemize}"
            r"\item First"
            r"\item    "
            r"\item Third"
            r"\end{itemize}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser()
        frames = parser.parse(tex)
        itemize = next(e for e in frames[0].elements if e.type == "itemize")
        texts = [it.get("text", "") for it in itemize.items]
        assert "First" in texts
        assert "Third" in texts
        # No empty bullet
        assert all(t.strip() for t in texts)

    def test_punct_only_item_dropped(self):
        # An item that's just ":" or similar punctuation should also be
        # dropped — these are usually orphan label markers
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\begin{itemize}"
            r"\item First"
            r"\item :"
            r"\item Third"
            r"\end{itemize}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser()
        frames = parser.parse(tex)
        itemize = next(e for e in frames[0].elements if e.type == "itemize")
        texts = [it.get("text", "") for it in itemize.items]
        # Punct-only item dropped
        assert ":" not in texts

    def test_normal_items_preserved(self):
        # Defensive: make sure the empty-item filter doesn't drop real
        # content. Especially items that start with stylistic markers.
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\begin{itemize}"
            r"\item Strong content with citations [my_textbook:ch1.s1:p01]"
            r"\item Another fact about K-means clustering"
            r"\item Third bullet"
            r"\end{itemize}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser()
        frames = parser.parse(tex)
        itemize = next(e for e in frames[0].elements if e.type == "itemize")
        assert len(itemize.items) == 3


class TestNestedItemizeBalancedMatch:
    """Outer itemize parsing must track depth so a nested ``\\end{itemize}``
    doesn't truncate the outer environment. Previously the non-greedy
    ``(.*?)\\end{itemize}`` matched the FIRST inner close — the rest of the
    structure leaked as raw text into the parent item, producing phantom
    bullet rows in the PPTX render."""

    def test_nested_itemize_produces_subitems(self):
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\begin{itemize}"
            r"\item \textbf{Concept Overview:}"
            r"\begin{itemize}"
            r"\item First sub-item."
            r"\item Second sub-item."
            r"\item Third sub-item."
            r"\end{itemize}"
            r"\end{itemize}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser()
        frames = parser.parse(tex)
        itemize = next(e for e in frames[0].elements if e.type == "itemize")
        assert len(itemize.items) == 1
        parent = itemize.items[0]
        assert parent["text"] == "Concept Overview:"
        subs = parent.get("subitems", [])
        assert [s["text"] for s in subs] == [
            "First sub-item.",
            "Second sub-item.",
            "Third sub-item.",
        ]

    def test_nested_enumerate_within_itemize(self):
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\begin{itemize}"
            r"\item Outer"
            r"\begin{enumerate}"
            r"\item Inner one"
            r"\item Inner two"
            r"\end{enumerate}"
            r"\end{itemize}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser()
        frames = parser.parse(tex)
        itemize = next(e for e in frames[0].elements if e.type == "itemize")
        assert len(itemize.items) == 1
        parent = itemize.items[0]
        assert parent["text"] == "Outer"
        subs = parent.get("subitems", [])
        assert [s["text"] for s in subs] == ["Inner one", "Inner two"]

    def test_two_sibling_itemize_blocks_both_parsed(self):
        # If the outer regex were depth-blind it could swallow content
        # across sibling blocks. This guards that case too.
        tex = (
            r"\begin{document}\begin{frame}{T}"
            r"\begin{itemize}\item A1\item A2\end{itemize}"
            r"\begin{itemize}\item B1\item B2\end{itemize}"
            r"\end{frame}\end{document}"
        )
        parser = LaTeXParser()
        frames = parser.parse(tex)
        itemizes = [e for e in frames[0].elements if e.type == "itemize"]
        assert len(itemizes) == 2
        assert [i["text"] for i in itemizes[0].items] == ["A1", "A2"]
        assert [i["text"] for i in itemizes[1].items] == ["B1", "B2"]


class TestMathBlockToReadableText:
    """align/equation blocks flatten to readable unicode, not raw LaTeX."""

    def test_align_merge_sequence_readable(self):
        from src.latex_to_pptx import clean_math_for_display
        align = (
            r"\text{Initial:} \& \quad \{a\}, \{b\} \\"
            "\n"
            r"\text{Step 1:} \& \quad \{a\}, \{b\} \rightarrow \{ab\}"
        )
        out = clean_math_for_display(align)
        assert "\\text" not in out
        assert "\\quad" not in out
        assert "\\rightarrow" not in out
        assert "→" in out
        assert "Initial:" in out and "{ab}" in out

    def test_empty_after_clean_returns_blank(self):
        from src.latex_to_pptx import clean_math_for_display
        assert clean_math_for_display(r"\\ \quad \&") == ""


class TestUnderscoreItalicAndGuillemets:
    def test_single_underscore_italic_stripped(self):
        from src.latex_to_pptx import strip_latex_formatting
        out = strip_latex_formatting("The _k_-means and _MinPts_ values")
        assert "_k_" not in out and "_MinPts_" not in out
        assert "k-means" in out and "MinPts" in out

    def test_guillemets_stripped(self):
        from src.latex_to_pptx import strip_latex_formatting
        out = strip_latex_formatting('<<"DBSCAN finds core objects.">>')
        assert "<<" not in out and ">>" not in out


class TestDashAndDollarNormalization:
    def test_triple_dash_to_emdash(self):
        from src.latex_to_pptx import unescape_latex
        assert "—" in unescape_latex("a quote --- a gloss")

    def test_empty_double_dollar_dropped(self):
        from src.latex_to_pptx import unescape_latex
        assert "$$" not in unescape_latex("such as $$ (the radius)")


class TestInlineMathRendering:
    """Inline/display math renders to readable unicode, not raw LaTeX or
    an erased fragment."""

    def test_bare_frac_survives_command_strip(self):
        from src.latex_to_pptx import strip_latex_formatting
        # A formula with no $ delimiters must not be erased to "s(o) =".
        out = strip_latex_formatting("s(o) = \\frac{b(o) - a(o)}{\\max(a(o), b(o))}")
        assert "(b(o) - a(o))/(max(a(o), b(o)))" in out

    def test_inline_paren_math_unwrapped(self):
        from src.latex_to_pptx import strip_latex_formatting
        out = strip_latex_formatting("Select \\( K \\) random points")
        assert "\\(" not in out and "\\)" not in out
        assert "Select K random points" in out

    def test_dollar_math_symbols_to_unicode(self):
        from src.latex_to_pptx import strip_latex_formatting
        out = strip_latex_formatting("where $k \\leq n$ and $O(n \\log n)$")
        assert "≤" in out and "log" in out
        assert "\\leq" not in out and "$" not in out

    def test_greek_inline(self):
        from src.latex_to_pptx import strip_latex_formatting
        out = strip_latex_formatting("the parameter $\\epsilon$ and $MinPts$")
        assert "ε" in out and "MinPts" in out

    def test_set_notation_braces_survive(self):
        from src.latex_to_pptx import clean_math_for_display
        out = clean_math_for_display(r"\{a\}, \{b\} \rightarrow \{ab\}")
        assert "{a}" in out and "{ab}" in out and "→" in out


class TestCaptionAndCapBug:
    def test_caption_not_mangled_by_cap_symbol(self):
        from src.latex_to_pptx import _convert_math_macros
        # \cap must not fire inside \caption
        assert "∩tion" not in _convert_math_macros(r"\caption{Reachability plot}")
        assert _convert_math_macros(r"\caption{x}") == r"\caption{x}"

    def test_cap_still_converts_standalone(self):
        from src.latex_to_pptx import _convert_math_macros
        assert "∩" in _convert_math_macros(r"A \cap B")

    def test_caption_kept_when_image_resolves(self, tmp_path):
        from src.latex_to_pptx import LaTeXParser
        img = tmp_path / "fig.png"
        img.write_bytes(b"\x89PNG\r\n")  # any existing file resolves
        body = (
            f"\\includegraphics[width=0.5\\textwidth]{{{img}}}\n"
            "\\caption{What the figure shows.}\n"
        )
        elements = LaTeXParser()._parse_content(body)
        caps = [e for e in elements if e.type == "caption"]
        assert len(caps) == 1
        assert "What the figure shows." in caps[0].content

    def test_orphan_caption_dropped_when_image_missing(self):
        from src.latex_to_pptx import LaTeXParser
        body = (
            "\\includegraphics[width=0.5\\textwidth]{/no/such.png}\n"
            "\\caption{Orphan with no picture.}\n"
        )
        elements = LaTeXParser()._parse_content(body)
        assert [e for e in elements if e.type == "caption"] == []
        assert [e for e in elements if e.type == "image"] == []


class TestStripTextbookFigureNumber:
    def test_drops_leading_figure_number(self):
        from src.latex_to_pptx import _strip_textbook_figure_number
        assert _strip_textbook_figure_number(
            "Figure 13.3: Other data mining methodologies"
        ) == "Other data mining methodologies"
        assert _strip_textbook_figure_number(
            "Figure 10.8. Hierarchical clustering") == "Hierarchical clustering"
        assert _strip_textbook_figure_number(
            "Fig 2.16 — visualization") == "visualization"

    def test_leaves_normal_caption(self):
        from src.latex_to_pptx import _strip_textbook_figure_number
        cap = "Cluster assignment across iterations"
        assert _strip_textbook_figure_number(cap) == cap


class TestPercentRendering:
    """The comment-strip used to drop from % to end-of-line even for an
    escaped \\%, truncating "50\\% of data" to "50". The negative lookbehind
    keeps \\% so unescape_latex turns it into a literal %."""

    def test_escaped_percent_renders_as_literal(self):
        out = strip_latex_formatting("Captures the middle 50\\% of data here.")
        assert "50% of data here" in out

    def test_bare_percent_still_strips_as_comment(self):
        # A genuinely unescaped % is still a LaTeX comment (upstream behavior).
        out = strip_latex_formatting("visible text % hidden tail")
        assert "visible text" in out
        assert "hidden tail" not in out


class TestTabularToText:
    """A tabular renders as readable rows, not a bare placeholder."""

    def test_flattens_rows_and_cells(self):
        from src.latex_to_pptx import _tabular_to_text
        body = (
            "{|l|l|}\n\\hline\nName & Type \\\\\n\\hline\n"
            "cust\\_id & integer \\\\\nname & string \\\\\n\\hline\n"
        )
        out = _tabular_to_text(body)
        assert "Name  |  Type" in out
        assert "cust_id  |  integer" in out
        assert "name  |  string" in out

    def test_unwraps_text_command_cells(self):
        # \text{...} / \textbf{...} cells must keep their content — the
        # generic command-strip would otherwise drop them and blank the row.
        from src.latex_to_pptx import _tabular_to_text
        body = (
            "{|c|c|}\n\\hline\n\\textbf{Table} & \\textbf{Attributes} \\\\\n\\hline\n"
            "\\text{Customer} & \\text{cust ID, name, age} \\\\\n\\hline\n"
        )
        out = _tabular_to_text(body)
        assert "Table  |  Attributes" in out
        assert "Customer  |  cust ID, name, age" in out

    def test_empty_returns_blank(self):
        from src.latex_to_pptx import _tabular_to_text
        assert _tabular_to_text("{ll}\n\\hline\n") == ""

    def test_parser_emits_table_text_not_placeholder(self):
        tex = (
            "\\begin{document}\n\\begin{frame}\\frametitle{T}\n"
            "\\begin{tabular}{ll}\nApple & Fruit \\\\\nCarrot & Veg \\\\\n"
            "\\end{tabular}\n\\end{frame}\n\\end{document}"
        )
        frames = LaTeXParser().parse(tex)
        joined = "\n".join(
            e.content for e in frames[0].elements if e.type == "text"
        )
        assert "see LaTeX source" not in joined
        assert "Apple  |  Fruit" in joined


class TestUndelimitedMathTextUnwrap:
    """A rule written as bare (no-$) LaTeX with \\text{} must keep its content.
    Without the unwrap in _convert_math_macros, the generic command-strip ate
    "\\text{computer}" whole — the literal "buys(X, ) ⇒ buys(X, )" defect."""

    def test_strip_latex_formatting_keeps_text_content(self):
        rule = (r'\text{buys}(X, \text{"computer"}) \Rightarrow '
                r'\text{buys}(X, \text{"software"})')
        out = strip_latex_formatting(rule)
        assert "buys" in out and "computer" in out and "software" in out
        assert "⇒" in out

    def test_convert_math_macros_unwraps_text(self):
        from src.latex_to_pptx import _convert_math_macros
        assert _convert_math_macros(r"\text{support}") == "support"
        assert _convert_math_macros(r"\mathbf{x}") == "x"
