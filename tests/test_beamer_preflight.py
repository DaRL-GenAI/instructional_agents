import shutil
import subprocess
from pathlib import Path

import pytest

from src.beamer_preflight import normalize_beamer_file, normalize_beamer_source


def _document(body: str, preamble: str = "") -> str:
    return (
        "\\documentclass{beamer}\n"
        "\\usepackage{xcolor}\n"
        f"{preamble}"
        "\\begin{document}\n"
        f"{body}\n"
        "\\end{document}\n"
    )


def test_flattens_only_list_wrappers_beyond_three_levels() -> None:
    source = r"""
\begin{itemize}
  \item Level 1
  \begin{enumerate}
    \item Level 2
    \begin{itemize}
      \item Level 3
      \begin{itemize}[<+->]
        \item Level 4 content
      \end{itemize}
    \end{itemize}
  \end{enumerate}
\end{itemize}
"""

    result = normalize_beamer_source(source)

    assert result.changed
    assert result.removed_list_wrapper_pairs == 1
    assert result.original_max_list_depth == 4
    assert result.normalized_max_list_depth == 3
    assert "Level 4 content" in result.source
    assert result.source.count(r"\begin{itemize}") == 2
    assert "[<+->]" not in result.source
    assert not normalize_beamer_source(result.source).changed


def test_preserves_list_examples_in_comments_and_listings() -> None:
    source = r"""
% \begin{itemize}
\begin{lstlisting}
\begin{itemize}
\begin{itemize}
\begin{itemize}
\begin{itemize}
\end{itemize}
\end{itemize}
\end{itemize}
\end{itemize}
\end{lstlisting}
"""

    result = normalize_beamer_source(source)

    assert not result.changed
    assert result.source == source


def test_malformed_list_structure_is_not_rewritten() -> None:
    source = r"\begin{itemize}\begin{enumerate}\end{itemize}\end{enumerate}"

    result = normalize_beamer_source(source)

    assert not result.changed
    assert result.source == source


def test_normalize_beamer_file_writes_repaired_source_atomically(
    tmp_path: Path,
) -> None:
    path = tmp_path / "slides.tex"
    source = (
        r"\begin{itemize}" * 4
        + r"\item Keep me"
        + r"\end{itemize}" * 4
    )
    path.write_text(source, encoding="utf-8")

    result = normalize_beamer_file(path)

    assert result.changed
    assert path.read_text(encoding="utf-8") == result.source
    assert not path.with_suffix(".tex.preflight.tmp").exists()


def test_injects_providecolor_for_undefined_named_color() -> None:
    source = _document(r"\textcolor{electricblue}{\textbf{Ethics}}")

    result = normalize_beamer_source(source)

    assert result.changed
    assert result.injected_color_definitions == ("electricblue",)
    assert r"\providecolor{electricblue}{HTML}{0047AB}" in result.source
    definition_index = result.source.index(r"\providecolor{electricblue}")
    assert definition_index < result.source.index(r"\begin{document}")


def test_explicit_color_models_are_not_treated_as_names() -> None:
    source = _document(
        r"\textcolor[HTML]{FF0000}{x} \color[rgb]{1,0,0} y"
    )

    result = normalize_beamer_source(source)

    assert not result.changed
    assert result.source == source


def test_defined_colors_are_not_reinjected() -> None:
    source = _document(
        r"\textcolor{myblue}{x} \colorlet{halfblue}{myblue!50}"
        + "\n"
        + r"\colorbox{halfblue}{y} \textcolor{mystery}{z}",
        preamble="\\definecolor{myblue}{HTML}{2244AA}\n",
    )

    result = normalize_beamer_source(source)

    assert result.injected_color_definitions == ("mystery",)


def test_colorlet_source_expression_is_repaired() -> None:
    source = _document(r"\colorlet{shade}{undefinedname!30!white}")

    result = normalize_beamer_source(source)

    assert result.injected_color_definitions == ("undefinedname",)


def test_color_expressions_are_decomposed() -> None:
    source = _document(r"\colorbox{myaccent!20!white}{x}")

    result = normalize_beamer_source(source)

    assert result.injected_color_definitions == ("myaccent",)


def test_setbeamercolor_fg_bg_values_are_repaired() -> None:
    source = _document(
        r"x",
        preamble=r"\setbeamercolor{frametitle}{fg=white, bg=brandnavy}" + "\n",
    )

    result = normalize_beamer_source(source)

    assert result.injected_color_definitions == ("brandnavy",)


def test_tikz_color_keys_are_repaired_and_none_is_skipped() -> None:
    source = _document(
        r"\tikz{\node[fill=deepteal!60, draw=none, text=offivory] {x};}"
    )

    result = normalize_beamer_source(source)

    assert set(result.injected_color_definitions) == {"deepteal", "offivory"}


def test_known_names_and_garbage_fall_back_deterministically() -> None:
    source = _document(r"\textcolor{SteelBlue}{x} \textcolor{zorbcolor}{y}")

    result = normalize_beamer_source(source)

    assert r"\providecolor{SteelBlue}{HTML}{4682B4}" in result.source
    assert r"\providecolor{zorbcolor}{HTML}{4A5568}" in result.source


def test_colors_in_comments_and_listings_are_ignored() -> None:
    source = _document(
        "% \\textcolor{commentonly}{x}\n"
        "\\begin{lstlisting}\n"
        "\\textcolor{listingonly}{x}\n"
        "\\end{lstlisting}"
    )

    result = normalize_beamer_source(source)

    assert not result.changed
    assert result.source == source


def test_color_injection_is_idempotent() -> None:
    source = _document(r"\textcolor{electricblue}{x}")

    first = normalize_beamer_source(source)
    second = normalize_beamer_source(first.source)

    assert first.changed
    assert not second.changed
    assert second.source == first.source


def test_sources_without_document_environment_are_left_unchanged() -> None:
    source = r"\textcolor{electricblue}{x}"

    result = normalize_beamer_source(source)

    assert not result.changed
    assert result.source == source


_PDFLATEX = shutil.which("pdflatex")


@pytest.mark.latex
@pytest.mark.skipif(_PDFLATEX is None, reason="pdflatex is not installed")
def test_repaired_undefined_color_compiles_with_pdflatex(tmp_path: Path) -> None:
    source = _document(
        "\\begin{frame}\n"
        "\\frametitle{Ethics}\n"
        "\\textcolor{electricblue}{\\textbf{Introduction to Ethical Considerations}}\n"
        "\\end{frame}"
    )
    tex_path = tmp_path / "slides.tex"
    tex_path.write_text(normalize_beamer_source(source).source, encoding="utf-8")

    completed = subprocess.run(
        [_PDFLATEX, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )

    pdf_path = tmp_path / "slides.pdf"
    assert completed.returncode == 0, completed.stdout[-2000:]
    assert pdf_path.is_file() and pdf_path.stat().st_size > 0


@pytest.mark.latex
@pytest.mark.skipif(_PDFLATEX is None, reason="pdflatex is not installed")
def test_compiler_retry_recovers_undefined_color_without_touching_source(
    tmp_path: Path,
) -> None:
    from src.compile import LaTeXCompiler

    source = _document(
        "\\begin{frame}\n"
        "\\textcolor{electricblue}{x}\n"
        "\\end{frame}"
    )
    tex_path = tmp_path / "slides.tex"
    tex_path.write_text(source, encoding="utf-8")

    pdf_path = LaTeXCompiler(str(tmp_path)).compile_one(tex_path)

    assert pdf_path.is_file() and pdf_path.stat().st_size > 0
    assert tex_path.read_text(encoding="utf-8") == source
