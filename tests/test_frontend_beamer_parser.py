from pathlib import Path

from src.frontend_slides import parse_beamer


def test_parse_nested_lists_equations_tables_and_code(tmp_path: Path) -> None:
    tex = r"""
\documentclass{beamer}
\title{Synthetic Deck}
\begin{document}
\frame{\titlepage}
\begin{frame}[fragile]{Frame Arg}
  \frametitle{Nested Content}
  Plain intro.
  \begin{itemize}
    \item Parent one
      \begin{enumerate}
        \item Child alpha
        \item Child beta
      \end{enumerate}
    \item Parent two
  \end{itemize}
  \begin{equation}
    y = Xw
  \end{equation}
  \begin{table}
    \begin{tabular}{|c|c|}
      A & B \\
      1 & 2 \\
    \end{tabular}
  \end{table}
  \begin{lstlisting}[language=Python]
print("hello")
  \end{lstlisting}
\end{frame}
\end{document}
"""
    path = tmp_path / "synthetic.tex"
    path.write_text(tex, encoding="utf-8")

    deck = parse_beamer(path)
    slide = deck.slides[1]

    assert deck.title == "Synthetic Deck"
    assert deck.slide_count == 2
    assert slide.title == "Nested Content"
    assert [element.kind for element in slide.elements] == ["text", "list", "equation", "table", "code"]
    list_element = slide.elements[1]
    assert list_element.items[0].text == "Parent one"
    assert list_element.items[0].children[0].kind == "list"
    assert list_element.items[0].children[0].items[1].text == "Child beta"
    assert slide.elements[2].text.strip() == "y = Xw"
    assert slide.elements[2].env == "equation"
    assert slide.elements[3].rows == [["A", "B"], ["1", "2"]]
    assert slide.elements[4].language == "Python"
    assert 'print("hello")' in slide.elements[4].text


def test_code_blocks_are_dedented_and_verbatim_is_code(tmp_path: Path) -> None:
    tex = r"""
\documentclass{beamer}
\title{Code Deck}
\begin{document}
\begin{frame}[fragile]
  \frametitle{Snippets}
  \begin{lstlisting}[language=Python]
        from sklearn.svm import SVC
        model = SVC(kernel='rbf')
  \end{lstlisting}
  \begin{verbatim}
        Root
        |-- Left
        |-- Right
  \end{verbatim}
\end{frame}
\end{document}
"""
    path = tmp_path / "code.tex"
    path.write_text(tex, encoding="utf-8")

    deck = parse_beamer(path)
    code, verbatim = deck.slides[0].elements

    assert code.kind == "code"
    assert code.language == "Python"
    assert code.text.startswith("from sklearn.svm import SVC")
    assert "\nmodel = SVC" in code.text  # common indentation removed

    assert verbatim.kind == "code"
    assert verbatim.language is None
    assert verbatim.text.startswith("Root")
    assert "verbatim" not in deck.unsupported_environments


def _single_frame_deck(tmp_path: Path, body: str) -> "BeamerSlide":
    tex = (
        "\\documentclass{beamer}\n\\title{Wrapped Deck}\n\\begin{document}\n"
        "\\begin{frame}{Wrapped}\n" + body + "\n\\end{frame}\n\\end{document}\n"
    )
    path = tmp_path / "wrapped.tex"
    path.write_text(tex, encoding="utf-8")
    return parse_beamer(path).slides[0]


def test_tabular_inside_wrapper_environments_parses_as_table(tmp_path: Path) -> None:
    wrappers = {
        "center": "\\begin{center}\n@BODY@\n\\end{center}",
        "columns": (
            "\\begin{columns}\n\\begin{column}{0.6\\textwidth}\n@BODY@\n"
            "\\end{column}\n\\end{columns}"
        ),
        "adjustbox": "\\begin{adjustbox}{max width=\\textwidth}\n@BODY@\n\\end{adjustbox}",
        "resizebox": "\\resizebox{\\textwidth}{!}{@BODY@}",
    }
    tabular = "\\begin{tabular}{|c|c|}\nA & B \\\\\n1 & 2 \\\\\n\\end{tabular}"
    for name, template in wrappers.items():
        slide = _single_frame_deck(tmp_path, template.replace("@BODY@", tabular))
        tables = [element for element in slide.elements if element.kind == "table"]
        assert tables, f"tabular inside {name} was not parsed as a table"
        assert tables[0].rows == [["A", "B"], ["1", "2"]], name
        assert not [element for element in slide.elements if element.kind == "raw"], name


def test_table_rows_keep_empty_cells(tmp_path: Path) -> None:
    body = (
        "\\begin{center}\n\\begin{tabular}{|c|c|c|}\n\\hline\n"
        " & Predicted Yes & Predicted No \\\\\n\\hline\n"
        "Actual Yes & TP & FN \\\\\n\\hline\n\\end{tabular}\n\\end{center}"
    )
    slide = _single_frame_deck(tmp_path, body)
    assert slide.elements[0].rows == [
        ["", "Predicted Yes", "Predicted No"],
        ["Actual Yes", "TP", "FN"],
    ]


def test_alignment_environments_record_env_and_strip_labels(tmp_path: Path) -> None:
    body = (
        "\\begin{align}\\label{eq:sys}\nx &= 1 \\\\\ny &= 2\n\\end{align}\n"
        "\\begin{align*}\na &= b\n\\end{align*}\n"
        "\\begin{gather}\np = q\n\\end{gather}\n"
        "\\begin{alignat}{2}\nu &= v\n\\end{alignat}"
    )
    slide = _single_frame_deck(tmp_path, body)
    equations = [element for element in slide.elements if element.kind == "equation"]
    assert [element.env for element in equations] == ["align", "align*", "gather", "alignat"]
    assert "\\label" not in equations[0].text
    assert equations[3].text.strip().startswith("u"), "alignat {n} argument should be consumed"


def test_inline_math_survives_text_cleaning(tmp_path: Path) -> None:
    tex = r"""
\documentclass{beamer}
\title{Math Deck}
\begin{document}
\begin{frame}
  \frametitle{Inline Math}
  The probability \( P(y = 1 | X) \) of the positive class uses $\beta_0 + \beta_1 X_1$ as the linear part.
  \begin{itemize}
    \item Odds are defined as \(\frac{P}{1-P}\).
  \end{itemize}
\end{frame}
\end{document}
"""
    path = tmp_path / "math.tex"
    path.write_text(tex, encoding="utf-8")

    slide = parse_beamer(path).slides[0]

    text = slide.elements[0].text
    assert r"\(P(y = 1 | X)\)" in text
    assert r"\(\beta_0 + \beta_1 X_1\)" in text  # $...$ is normalized to \( ... \)
    assert r"\(\frac{P}{1-P}\)" in slide.elements[1].items[0].text
