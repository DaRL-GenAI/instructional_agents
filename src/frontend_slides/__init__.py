"""Offline Beamer-to-HTML slide generation for Instructional Agents."""

from .finalize import FrontendSlidesError, finalize_chapter
from .models import ChapterFrontendResult, CourseSlideStyle
from .style_workflow import ensure_course_slide_style, load_course_slide_style

__all__ = [
    "ChapterFrontendResult",
    "CourseSlideStyle",
    "FrontendSlidesError",
    "ensure_course_slide_style",
    "finalize_chapter",
    "load_course_slide_style",
]
