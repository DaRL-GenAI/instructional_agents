from src.html_slides import ContentElement, render_element


def _equation(text: str, env: str | None = None) -> str:
    return render_element(ContentElement(kind="equation", text=text, env=env))


def test_plain_equation_stays_bare_display_math() -> None:
    html = _equation("E = mc^2", env="equation")
    assert "\\[E = mc^2\\]" in html
    assert "aligned" not in html


def test_align_body_is_wrapped_in_aligned() -> None:
    html = _equation("a &= b \\\\ c &= d", env="align")
    assert "\\[\\begin{aligned}" in html
    assert "\\end{aligned}\\]" in html


def test_align_star_and_gather_get_display_safe_wrappers() -> None:
    assert "\\begin{aligned}" in _equation("a &= b", env="align*")
    assert "\\begin{gathered}" in _equation("p = q \\\\ r = s", env="gather")


def test_nested_align_inside_equation_is_normalized() -> None:
    html = _equation("\\begin{align*} x &= 1 \\\\ y &= 2 \\end{align*}", env="equation")
    assert "\\begin{align*}" not in html
    assert "\\begin{align}" not in html
    assert html.count("\\begin{aligned}") == 1


def test_env_less_body_with_alignment_marker_is_wrapped_defensively() -> None:
    assert "\\begin{aligned}" in _equation("a &= b")


def test_matrix_bodies_are_not_double_wrapped() -> None:
    html = _equation("A = \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}", env="equation")
    assert "aligned" not in html
    assert "pmatrix" in html
