"""Generate tests/fixtures/mini_textbook.pdf — a tiny labeled PDF textbook.

Run manually to (re)create the fixture:
    pip install fpdf2
    python tests/fixtures/make_mini_pdf.py

The generated .pdf is committed to the repo as a test fixture; fpdf2 itself is
NOT a project dependency (nothing in src/ or the test suite imports it).

Known structure (the ground truth the PDF-ingester tests assert against):
  Chapter 1: Foundations        2 sections (1.1 Numbers, 1.2 Operators)
  Chapter 2: Control Flow        1 section  (2.1 Conditionals)
"""

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).parent / "mini_textbook.pdf"


def main() -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    def heading(text: str, size: int) -> None:
        pdf.set_font("Helvetica", "B", size)
        pdf.multi_cell(0, size * 0.6, text)
        pdf.ln(6)

    def body(text: str) -> None:
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, text)
        pdf.ln(11)

    pdf.add_page()
    heading("Chapter 1: Foundations", 24)
    heading("1.1 Numbers", 15)
    body("Numbers can be integers or floating point values in this language.")
    body("A second prose paragraph discusses arithmetic and number operations.")
    heading("1.2 Operators", 15)
    body("Operators perform actions on values and produce new results here.")

    pdf.add_page()
    heading("Chapter 2: Control Flow", 24)
    heading("2.1 Conditionals", 15)
    body("Conditional statements let a program branch on a boolean test value.")
    body("Loops repeat a block of statements multiple times in clear sequence.")

    pdf.output(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
