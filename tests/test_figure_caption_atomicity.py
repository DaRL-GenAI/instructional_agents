"""Tests for figure↔caption atomicity.

A caption is sourced ONLY from the same IR chunk as its image (paired by
filename), never from a page lookup — a page lookup would have to guess among
the captions on that page, which is exactly how image B ends up under caption A.
An image with no paired caption renders bare. Strict atomicity = zero downstream
guessing.
"""

from __future__ import annotations

from src.slides import (
    _build_figure_caption_by_path,
    _caption_for_figure_path,
)


class _C:
    def __init__(self, text):
        self.text = text


class TestBuildByPath:
    def test_pairs_each_figure_with_its_own_caption(self):
        chunks = [
            _C("Figure 2.1: A scatter plot of clusters "
               "[IMAGE_PATH: /x/han_p0054_01.png]"),
            _C("Figure 2.2: A dendrogram of merges "
               "[IMAGE_PATH: /x/han_p0054_02.png]"),
        ]
        by_path = _build_figure_caption_by_path(chunks)
        assert by_path["han_p0054_01.png"] == "A scatter plot of clusters"
        assert by_path["han_p0054_02.png"] == "A dendrogram of merges"

    def test_uncaptioned_figure_skipped(self):
        # "Figure (p54, item 1):" has no real caption — no entry.
        chunks = [_C("Figure (p54, item 1): [IMAGE_PATH: /x/han_p0054_01.png]")]
        assert _build_figure_caption_by_path(chunks) == {}


class TestCaptionIsStrictlyAtomic:
    def test_returns_the_images_own_caption(self):
        by_path = {"han_p0054_01.png": "A scatter plot of clusters",
                   "han_p0054_02.png": "A dendrogram of merges"}
        # image _02 gets ITS caption, never image _01's — no page guessing.
        assert _caption_for_figure_path(
            "/x/han_p0054_02.png", by_path=by_path
        ) == "A dendrogram of merges"

    def test_unpaired_image_is_bare(self):
        # No atomic caption for this image → "" (the renderer adds a generic
        # "Figure." label). No page/neighbour fallback can mis-caption it.
        by_path = {"han_p0054_01.png": "A scatter plot"}
        assert _caption_for_figure_path("/x/han_p0054_02.png", by_path=by_path) == ""

    def test_no_by_path_is_bare(self):
        assert _caption_for_figure_path("/x/han_p0054_01.png") == ""
        assert _caption_for_figure_path("/x/han_p0054_01.png", by_path={}) == ""
