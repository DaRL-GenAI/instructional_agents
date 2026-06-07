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
            r"\item Strong content with citations [han_data_mining_3e:ch1.s1:p01]"
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
