from pathlib import Path

from src.beamer_preflight import normalize_beamer_file, normalize_beamer_source


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
