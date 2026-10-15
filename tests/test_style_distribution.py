"""Guards against the presentation-design deliberation collapsing onto one style.

The selector chooses from 46 candidates, but six of the eight runs recorded in
``exp/`` before this check existed picked ``bold_template:blue-professional``.
That is a property of the whole pipeline rather than of any one function, so it
cannot be asserted from a unit test — it only shows up across real runs.

These checks read the statistics each foundation run already writes. They
consider only runs recorded after the de-anchoring fix, identified by the
``selected_prompt_rank`` field, so historical runs do not fail the suite.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = REPO_ROOT / "exp"

# With 46 candidates, any single style taking more than this share of runs means
# something other than course fit is driving the choice.
MAX_MODAL_SHARE = 0.40

# Below this many runs the modal share is noise: three runs can legitimately
# agree twice.
MIN_RUNS_TO_JUDGE = 4


def _measurable_runs() -> list[dict[str, object]]:
    """Return statistics for runs recorded after the de-anchoring fix."""
    runs: list[dict[str, object]] = []
    for path in sorted(EXPERIMENT_ROOT.glob("*/statistics_slide_style.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or "selected_prompt_rank" not in data:
            continue
        selected = data.get("selected_style")
        if not isinstance(selected, dict) or not selected.get("key"):
            continue
        runs.append({**data, "course": path.parent.name})
    return runs


def test_no_single_style_dominates_the_selection() -> None:
    runs = _measurable_runs()
    if len(runs) < MIN_RUNS_TO_JUDGE:
        pytest.skip(
            f"Need {MIN_RUNS_TO_JUDGE} runs recorded with selected_prompt_rank; "
            f"found {len(runs)}."
        )

    picks = Counter(
        f"{run['selected_style']['source']}:{run['selected_style']['key']}"
        for run in runs
    )
    style, count = picks.most_common(1)[0]
    share = count / len(runs)

    assert share <= MAX_MODAL_SHARE, (
        f"{style} was selected in {count} of {len(runs)} runs "
        f"({share:.0%}). The style deliberation is collapsing onto one "
        f"candidate again. Full distribution: {dict(picks)}"
    )


def test_selection_is_not_tracking_position_in_the_prompt() -> None:
    """A style is chosen for its fit, not for being near the top of the list.

    ``presentation_order`` shuffles the candidate list per course, so the
    winner's rank should scatter across the 46 positions. Ranks clustered in the
    first few positions mean the shuffle stopped being applied and the model is
    anchoring on order again.
    """
    runs = _measurable_runs()
    if len(runs) < MIN_RUNS_TO_JUDGE:
        pytest.skip(
            f"Need {MIN_RUNS_TO_JUDGE} runs recorded with selected_prompt_rank; "
            f"found {len(runs)}."
        )

    ranks = [run["selected_prompt_rank"] for run in runs]
    ranks = [rank for rank in ranks if isinstance(rank, int)]
    if len(ranks) < MIN_RUNS_TO_JUDGE:
        pytest.skip("Not enough runs recorded a numeric prompt rank.")

    top_eighth = [rank for rank in ranks if rank <= 6]

    assert len(top_eighth) < len(ranks), (
        "Every run selected a style from the first six inventory positions "
        f"(ranks {ranks}). Check that presentation_order is still being applied "
        "to the prompt payload and the selection constraint."
    )
