"""Render-fidelity fixes found by a page-by-page review of generated decks.

Three deterministic, no-LLM fixes (all gated to the grounded path / safe on
general text):

1. **Dense math no longer collapses.** A bare ``\\bar{x} = \\frac{\\sum_{i=1}^{N}
   x_i}{N}`` used to render as just ``=`` — the ``\\frac`` regex couldn't span
   the nested ``\\sum_{…}^{…}`` braces, so the generic command-stripper erased
   the whole fraction and the ``\\bar`` accent. The converter now resolves
   accents and symbols, sheds sub/superscript braces before ``\\frac``, and
   tolerates one level of nesting in the fraction.

2. **Empty figure-promise frames are dropped.** A frame whose only body is a
   dangling "the following figure illustrates …" / "the figure below …" / "we
   include a relevant figure:" pointer (plus an orphaned ``\\caption`` or a
   hallucinated ``\\includegraphics`` that never resolves) is stripped to empty
   and removed, instead of shipping as a near-blank slide.

(The figure-height floor that keeps small figures legible lives in the JS
renderer build_pptx.js and is verified by re-rendering, not here.)
"""

from __future__ import annotations

from src.latex_to_pptx import strip_latex_formatting
from src.slides import _drop_empty_frames, _strip_dangling_figure_promises


class TestDenseMathDoesNotCollapse:
    def test_bar_frac_sum_mean_formula(self):
        # The exact bare formula that rendered as "=" in a generated deck.
        out = strip_latex_formatting(r"\bar{x} = \frac{\sum_{i=1}^{N} x_i}{N}")
        assert out.startswith("x")            # \bar{x} survived as x̄
        assert "̄" in out                # combining macron present
        assert "Σ" in out                     # \sum resolved, not erased
        assert "/(N)" in out                  # fraction converted, not dropped
        assert out != "="

    def test_plain_fraction_still_works(self):
        # No nested braces — must keep rendering as before.
        out = strip_latex_formatting(r"\frac{30 + 36 + 110}{12} = 53.83")
        assert out == "(30 + 36 + 110)/(12) = 53.83"

    def test_nested_sqrt_in_fraction(self):
        assert strip_latex_formatting(r"\frac{\sqrt{x}}{2}") == "(√(x))/(2)"

    def test_accents_resolve(self):
        assert strip_latex_formatting(r"\hat{y}").startswith("y")
        assert "̂" in strip_latex_formatting(r"\hat{y}")   # circumflex

    def test_set_notation_braces_in_denominator(self):
        # Silhouette-style: \max\{a, b\} nested in a fraction denominator.
        out = strip_latex_formatting(r"s = \frac{b-a}{\max\{a, b\}}")
        assert out == "s = (b-a)/(max{a, b})"


def _frame(title, body):
    return f"\\begin{{frame}}\n\\frametitle{{{title}}}\n{body}\n\\end{{frame}}\n"


def _clean(deck):
    return _drop_empty_frames(_strip_dangling_figure_promises(deck))


class TestEmptyFigurePromiseFramesDropped:
    def test_following_figure_with_trailing_clause_and_orphan_caption(self):
        # Two sentences on one line + an orphaned caption (figure was deduped
        # elsewhere). Both the internal period and the caption used to keep the
        # frame alive.
        deck = _frame(
            "Cluster Analysis Visualization",
            "The following figure illustrates a 2-D plot of customer data in a "
            "city. It shows three distinct clusters:\n"
            "\\caption{A 2-D plot of customer data revealing three clusters.}",
        )
        assert _clean(deck).strip() == ""

    def test_in_the_following_figure_we_illustrate(self):
        deck = _frame(
            "Illustration of Data Mining Trends",
            "In the following figure, we illustrate a relevant aspect of data "
            "mining trends.\n\\begin{center}\n\\end{center}",
        )
        assert _clean(deck).strip() == ""

    def test_figure_below_illustrates(self):
        deck = _frame(
            "Figure: Outlier Analysis",
            "The figure below illustrates the concept of outlier analysis and "
            "highlights the methods.",
        )
        assert _clean(deck).strip() == ""

    def test_hallucinated_includegraphics_only_frame_dropped(self):
        # A non-resolving \includegraphics is the frame's only "content"; it
        # must be stripped so the empty-frame drop can fire.
        deck = _frame(
            "Diagram: Data Pipeline",
            "\\includegraphics[width=0.6\\textwidth]{path_to_example_figure}",
        )
        assert _clean(deck).strip() == ""

    def test_dangling_numbered_reference_on_figureless_frame(self):
        deck = _frame(
            "Classification Models",
            "We can visualize these forms in Figure 1.9, which illustrates the "
            "model.",
        )
        assert _clean(deck).strip() == ""


class TestLegitimateFramesSurvive:
    def test_frame_with_resolving_figure_untouched(self, tmp_path):
        img = tmp_path / "real.png"
        img.write_bytes(b"\x89PNG real")
        deck = _frame(
            "Overview",
            f"\\includegraphics[width=0.7\\textwidth]{{{img}}}\n"
            "\\caption{Overview of data mining}\n"
            "Data mining extracts patterns.",
        )
        out = _clean(deck)
        assert "Overview of data mining" in out      # caption kept
        assert str(img) in out                        # image kept
        assert "Data mining extracts patterns." in out

    def test_real_sentence_plus_trailing_promise_keeps_content(self):
        # Real content + a dangling promise on the SAME line: strip only the
        # promise sentence, keep the real one (don't blank a content slide).
        deck = _frame(
            "Classification Model Representations",
            "Classification models can be represented in various forms, "
            "enhancing interpretability for stakeholders. The following figure "
            "illustrates different representations of a classification model.",
        )
        out = _clean(deck)
        assert "Classification models can be represented" in out
        assert "The following figure illustrates" not in out

    def test_indefinite_figure_mention_is_content(self):
        # "a figure that shows …" is descriptive content, not a dangling
        # pointer — the frame must survive.
        deck = _frame(
            "Boxplots",
            "A boxplot is a figure that shows the five-number summary.",
        )
        out = _clean(deck)
        assert "five-number summary" in out

    def test_vanilla_text_frame_untouched(self):
        deck = _frame("Intro", "Data mining finds patterns in large datasets.")
        assert _clean(deck).strip() == deck.strip()
