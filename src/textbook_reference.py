"""
Utilities for turning lightweight textbook references into catalog data.

This module intentionally avoids LLM calls. It extracts a bounded amount of
text from a user-provided textbook PDF/text file and converts it into the
existing catalog schema so the ADDIE workflow can consume it without changing
the core generation pipeline.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

try:
    import pdfplumber
except ImportError:  # pragma: no cover - dependency availability varies
    pdfplumber = None

try:
    import PyPDF2
except ImportError:  # pragma: no cover - dependency availability varies
    PyPDF2 = None

try:
    import pypdf
except ImportError:  # pragma: no cover - dependency availability varies
    pypdf = None


STOPWORDS = {
    "about", "after", "again", "also", "because", "before", "being", "between",
    "chapter", "course", "could", "during", "example", "first", "from", "have",
    "into", "learn", "learning", "more", "most", "other", "page", "section",
    "should", "students", "that", "their", "these", "this", "through", "using",
    "with", "would", "your", "或者", "以及", "学习", "学生", "课程", "章节",
}


class TextbookReferenceBuilder:
    """Build catalog-compatible reference data from a small textbook excerpt."""

    def __init__(self, max_pages: int = 20, max_chars: int = 40000):
        self.max_pages = max_pages
        self.max_chars = max_chars

    def build_catalog(self, source_path: Path, course_name: str = "") -> Dict[str, Any]:
        text_by_page = self.extract_text(source_path)
        full_text = "\n".join(page["text"] for page in text_by_page).strip()
        bounded_text = full_text[: self.max_chars]

        chapters = self.extract_chapters_from_toc(text_by_page)
        if not chapters:
            chapters = self.extract_chapters(bounded_text)
        key_topics = self.extract_key_topics(bounded_text)
        summary = self.summarize_excerpt(bounded_text, key_topics)
        weekly_outline = self.build_weekly_outline(chapters, key_topics)
        source_name = source_path.name

        return {
            "student_profile": {
                "student_background": "Students are assumed to be new to the course topic and will benefit from textbook-aligned explanations.",
                "aggregate_academic_performance": "Readiness is inferred from the uploaded textbook scope rather than historical grade data.",
                "anticipated_learner_needs_and_barriers": (
                    "Materials should introduce concepts progressively, reuse textbook terminology, "
                    "and provide examples connected to the reference chapters."
                ),
            },
            "instructor_preferences": {
                "instructor_emphasis_intent": "Use the uploaded textbook as the primary reference material for topic selection and examples.",
                "instructor_style_preferences": "Keep generated materials aligned with textbook chapter order and terminology.",
                "instructor_focus_for_assessment": "Assess whether students can explain and apply the key textbook concepts.",
            },
            "course_structure": {
                "course_learning_outcomes": self.build_learning_outcomes(key_topics),
                "total_number_of_weeks": str(max(1, min(len(chapters) or 6, 12))),
                "weekly_schedule_outline": weekly_outline,
                "textbook_reference_summary": summary,
                "required_readings": self.build_required_readings(source_name, chapters),
            },
            "assessment_design": {
                "assessment_format_preferences": "Short concept checks, applied exercises, and a final synthesis task grounded in the textbook reference.",
                "assessment_delivery_constraints": "Assessments should cite or refer back to the uploaded textbook chapters where relevant.",
            },
            "teaching_constraints": {
                "platform_policy_constraints": "Generated content should avoid quoting long textbook passages verbatim.",
                "ta_support_availability": "No additional teaching assistant support is assumed for this prototype.",
                "instructional_delivery_context": "Textbook-guided course generation prototype.",
                "max_slide_count": "10",
            },
            "institutional_requirements": {
                "program_learning_outcomes": "Materials should align textbook concepts with practical learning outcomes.",
                "academic_policies_and_institutional_standards": "Respect copyright by summarizing and paraphrasing reference material.",
                "department_syllabus_requirements": "Include textbook-derived topics, learning objectives, and assessment alignment.",
            },
            "prior_feedback": {
                "historical_course_evaluation_results": "No prior feedback supplied; this catalog was generated from textbook reference content.",
            },
            "textbook_reference": {
                "source": source_name,
                "course_name": course_name,
                "pages_processed": len(text_by_page),
                "characters_used": len(bounded_text),
                "key_topics": key_topics,
                "detected_chapters": chapters,
                "excerpt_summary": summary,
                "sample_excerpt": bounded_text[:1500],
            },
        }

    def extract_text(self, source_path: Path) -> List[Dict[str, Any]]:
        suffix = source_path.suffix.lower()
        if suffix == ".pdf":
            return self.extract_pdf_text(source_path)
        if suffix in {".txt", ".md"}:
            text = source_path.read_text(encoding="utf-8", errors="ignore")
            return [{"page": 1, "text": text[: self.max_chars]}]
        raise ValueError("Only PDF, TXT, and Markdown textbook references are supported.")

    def extract_pdf_text(self, pdf_path: Path) -> List[Dict[str, Any]]:
        pages: List[Dict[str, Any]] = []

        if pdfplumber is not None:
            try:
                with pdfplumber.open(str(pdf_path)) as pdf:
                    for index, page in enumerate(pdf.pages[: self.max_pages], start=1):
                        text = page.extract_text() or ""
                        if text.strip():
                            pages.append({"page": index, "text": text})
                if pages:
                    return pages
            except Exception as exc:
                print(f"[textbook_reference] pdfplumber extraction failed, falling back to PyPDF2: {exc}")
                pages = []

        if PyPDF2 is not None:
            with pdf_path.open("rb") as file:
                reader = PyPDF2.PdfReader(file)
                for index, page in enumerate(reader.pages[: self.max_pages], start=1):
                    text = page.extract_text() or ""
                    if text.strip():
                        pages.append({"page": index, "text": text})

        if not pages and pypdf is not None:
            with pdf_path.open("rb") as file:
                reader = pypdf.PdfReader(file)
                for index, page in enumerate(reader.pages[: self.max_pages], start=1):
                    text = page.extract_text() or ""
                    if text.strip():
                        pages.append({"page": index, "text": text})

        if not pages:
            raise ValueError("Could not extract readable text from the textbook file.")

        return pages

    def extract_chapters_from_toc(self, text_by_page: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Scan each page for TOC-like patterns before falling back to full-text extraction."""
        toc_chapter_pattern = re.compile(
            r"(?:Chapter\s*\d+|第\s*[一二三四五六七八九十\d]+\s*章|\d+\.\d+(?:\.\d+)?)\s*.{3,80}",
            flags=re.IGNORECASE,
        )
        seen = set()
        chapters: List[Dict[str, str]] = []

        for page in text_by_page[:6]:  # TOC is usually in the first few pages
            lines = [re.sub(r"\s+", " ", line).strip() for line in page["text"].splitlines()]
            toc_candidates = [
                line for line in lines
                if toc_chapter_pattern.fullmatch(line)
                and not line.endswith((".", ",", ";", ":"))
                and len(line.split()) <= 14
            ]
            if len(toc_candidates) >= 3:  # Looks like a TOC page
                for line in toc_candidates:
                    # Strip trailing page number (e.g., "Chapter 1: Introduction  42" → "Chapter 1: Introduction")
                    cleaned = re.sub(r"\s+\d{1,4}\s*$", "", line).strip()
                    if cleaned and len(cleaned) >= 5:
                        normalized = cleaned.lower()
                        if normalized not in seen:
                            seen.add(normalized)
                            chapters.append({"title": cleaned})
            if chapters:
                break  # Found a good TOC page, stop scanning

        return chapters[:12]

    def extract_chapters(self, text: str) -> List[Dict[str, str]]:
        seen = set()
        chapters: List[Dict[str, str]] = []
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]

        for index, line in enumerate(lines):
            title = None

            if line.upper() == "CHAPTER" and index > 0 and index + 1 < len(lines):
                previous_line = lines[index - 1]
                next_line = lines[index + 1]
                if re.fullmatch(r"\d{1,3}", previous_line) and self._looks_like_heading(next_line):
                    title = f"Chapter {previous_line}: {next_line}"

            if title is None:
                section_match = re.fullmatch(r"(\d+\.\d+(?:\.\d+)?)\s+(.{3,80})", line)
                section_title = section_match.group(2) if section_match else ""
                if (
                    section_match
                    and not re.search(r"\s\d{2,4}$", section_title)
                    and self._looks_like_heading(section_title)
                ):
                    title = line

            if title is None:
                chapter_match = re.fullmatch(r"(Chapter\s*\d+)\s*[:.\-\s]\s*(.{3,80})", line, flags=re.IGNORECASE)
                chapter_title = chapter_match.group(2) if chapter_match else ""
                if (
                    chapter_match
                    and self._looks_like_heading(chapter_title)
                    and self._looks_like_chapter_title(chapter_title)
                ):
                    title = f"{chapter_match.group(1)}: {chapter_title}"

            if title is None:
                chinese_match = re.fullmatch(r"(第\s*[一二三四五六七八九十\d]+\s*章)\s*(.{0,80})", line)
                if chinese_match:
                    suffix = chinese_match.group(2).strip()
                    title = f"{chinese_match.group(1)} {suffix}".strip()

            if title:
                normalized = title.lower()
                if normalized not in seen:
                    seen.add(normalized)
                    chapters.append({"title": title})
                if len(chapters) >= 12:
                    break

        return chapters

    def _looks_like_heading(self, text: str) -> bool:
        text = text.strip()
        if not 3 <= len(text) <= 100:
            return False
        if text.endswith((".", ",", ";", ":")):
            return False
        words = text.split()
        if len(words) > 12:
            return False
        alpha_chars = re.findall(r"[A-Za-z\u4e00-\u9fff]", text)
        if len(alpha_chars) < 3:
            return False
        return True

    def _looks_like_chapter_title(self, text: str) -> bool:
        first_word = text.split()[0] if text.split() else ""
        if first_word and first_word[0].islower():
            return False
        if re.search(r"\b(discussed|are|is|was|were|will|can|cannot|should|examples?)\b", text, flags=re.IGNORECASE):
            return False
        if re.search(r"\s\d{2,4}$", text):
            return False
        return True

    def extract_key_topics(self, text: str, limit: int = 12) -> List[str]:
        words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}|[\u4e00-\u9fff]{2,}", text.lower())
        candidates = [
            word.strip("-")
            for word in words
            if len(word) > 3 and word not in STOPWORDS and not word.isdigit()
        ]
        counts = Counter(candidates)
        return [word for word, _ in counts.most_common(limit)]

    def summarize_excerpt(self, text: str, key_topics: List[str]) -> str:
        sentences = re.split(r"(?<=[.!?。！？])\s+", text.replace("\n", " "))
        clean_sentences = [re.sub(r"\s+", " ", sentence).strip() for sentence in sentences]
        clean_sentences = [sentence for sentence in clean_sentences if 40 <= len(sentence) <= 260]

        selected = clean_sentences[:3]
        topic_text = ", ".join(key_topics[:6]) if key_topics else "core textbook concepts"
        if selected:
            return f"Main detected topics include {topic_text}. Representative excerpt themes: " + " ".join(selected)
        return f"Main detected topics include {topic_text}."

    def build_learning_outcomes(self, key_topics: List[str]) -> str:
        topics = key_topics[:6] or ["core concepts", "key methods", "applications"]
        return (
            "By the end of the course, students should be able to explain, compare, "
            f"and apply textbook concepts including {', '.join(topics)}."
        )

    def build_weekly_outline(self, chapters: List[Dict[str, str]], key_topics: List[str]) -> str:
        if chapters:
            outline_items = [
                f"Module {index}: {chapter['title']}"
                for index, chapter in enumerate(chapters[:12], start=1)
            ]
        else:
            topics = key_topics[:8] or ["Textbook overview", "Core concepts", "Applications"]
            outline_items = [
                f"Module {index}: {topic.title()}"
                for index, topic in enumerate(topics, start=1)
            ]
        return "; ".join(outline_items)

    def build_required_readings(self, source_name: str, chapters: List[Dict[str, str]]) -> str:
        if chapters:
            readings = [
                f"{source_name}, {chapter['title']}"
                for chapter in chapters[:8]
            ]
            return "; ".join(readings)
        return f"Selected excerpts from {source_name}"
