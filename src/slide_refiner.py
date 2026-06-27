"""SlideRefiner - localized, frame-level refinement of an existing Beamer LaTeX deck.

Extracted from the IA-aarsh refiner pipeline (src/refinement.py). Unlike the
"regenerate" path in optimize.py, this performs surgical edits: it locates only
the frames most relevant to the feedback, rewrites just their bodies, anchors the
replacement on the original frame text so untouched frames stay byte-identical,
and guards the result with deterministic body- and document-level validation plus
retries.

The LLM is only trusted to (1) pick which frames to edit and (2) rewrite a single
frame body; everything else is regex parsing + string replacement + checks.

Input contract: refine_slides(content, feedback_text, max_retries) where
`content` is a full LaTeX document string and `feedback_text` is free text
(evaluator metrics OR human feedback -- it is just a string).
"""

import re

from src.latex_to_pptx import LaTeXParser


class SlideRefiner:
    def __init__(self, llm):
        self.llm = llm

    def refine_slides(self, content, feedback_text, max_retries=1):

        frames = self.parse_frames(content)
        frame_summary = self.build_frame_summary(frames)
        locator_response = self.locate_frames(feedback_text, frame_summary)
        target_indexes = self.parse_target_frame_indexes(locator_response)
        target_frames = self.get_target_frames(frames, target_indexes)

        edited_frames = []
        validation_history = []
        refined_content = content

        for attempt in range(max_retries + 1):
            working_frames = self.parse_frames(refined_content)

            for target_frame in target_frames:
                frame_index = target_frame["index"]
                current_target_frame = working_frames[frame_index]
                frame_context = self.build_target_frame_context(
                    working_frames,
                    current_target_frame
                )

                if attempt == 0:
                    revised_body = self.refine_frame_body(
                        frame_context,
                        feedback_text
                    )

                else:
                    previous_validation = validation_history[-1]

                    validation_errors = "\n".join(
                        previous_validation.get("errors", [])
                    )

                    revised_body = self.retry_refine_frame_body(
                        frame_context,
                        feedback_text,
                        validation_errors
                    )

                body_validation = self.validate_frame_body(revised_body)
                body_retries_used = 0

                while (
                    body_validation["status"] == "FAIL"
                    and body_retries_used < max_retries
                ):
                    revised_body = self.retry_refine_frame_body(
                        frame_context,
                        feedback_text,
                        "\n".join(body_validation["errors"])
                    )
                    body_validation = self.validate_frame_body(revised_body)
                    body_retries_used += 1

                if body_validation["status"] == "FAIL":
                    continue

                rebuilt_frame = self.rebuild_frame(
                    current_target_frame,
                    revised_body
                )

                working_frames = self.replace_frames(
                    working_frames,
                    frame_index,
                    rebuilt_frame
                )

                if not any(
                    frame["index"] == frame_index
                    for frame in edited_frames
                ):
                    edited_frames.append({
                        "index": frame_index,
                        "title": current_target_frame["title"]
                    })

            refined_content = self.reassemble_slides(
                refined_content,
                working_frames
            )

            validation_result = self.validate_slide_patch(
                original_latex=content,
                refined_latex=refined_content,
                edited_frames=edited_frames
            )

            validation_history.append(validation_result)

            if validation_result["status"] == "PASS":
                return {
                    "refined_content": refined_content,
                    "locator_response": locator_response,
                    "target_indexes": target_indexes,
                    "edited_frames": edited_frames,
                    "slide_validation_status": "PASS",
                    "slide_validation_errors": [],
                    "validation_history": validation_history,
                    "retries_used": attempt
                }

        final_validation = validation_history[-1]

        return {
            "refined_content": refined_content,
            "locator_response": locator_response,
            "target_indexes": target_indexes,
            "edited_frames": edited_frames,
            "slide_validation_status": "FAIL",
            "slide_validation_errors": final_validation.get("errors", []),
            "validation_history": validation_history,
            "retries_used": max_retries
        }
    def validate_slide_patch(self, original_latex, refined_latex, edited_frames):

        errors = []

        required_markers = [
            "\\documentclass",
            "\\begin{document}",
            "\\end{document}"
        ]

        for marker in required_markers:
            if marker not in refined_latex:
                errors.append(f"Missing required LaTeX marker: {marker}")

        original_begin_frames = len(re.findall(r"\\begin\{frame", original_latex))
        refined_begin_frames = len(re.findall(r"\\begin\{frame", refined_latex))

        original_end_frames = len(re.findall(r"\\end\{frame\}", original_latex))
        refined_end_frames = len(re.findall(r"\\end\{frame\}", refined_latex))

        if original_begin_frames != refined_begin_frames:
            errors.append(
                f"Frame begin count changed unexpectedly: "
                f"original={original_begin_frames}, refined={refined_begin_frames}"
            )

        if original_end_frames != refined_end_frames:
            errors.append(
                f"Frame end count changed unexpectedly: "
                f"original={original_end_frames}, refined={refined_end_frames}"
            )

        try:
            parsed_frames = LaTeXParser().parse(refined_latex)
            if not parsed_frames:
                errors.append(
                    "Refined slides could not be parsed by PPTX parser"
                )
        except Exception as e:
            errors.append(f"PPTX parser failed: {str(e)}")

        if "```" in refined_latex:
            errors.append("Markdown code fences detected in refined slides")

        if "TARGET_FRAMES:" in refined_latex:
            errors.append("Locator prompt text leaked into refined slides")

        original_frames = self.parse_frames(original_latex)
        refined_frames = self.parse_frames(refined_latex)

        edited_indexes = {
            frame["index"]
            for frame in edited_frames
        }

        for frame in original_frames:
            idx = frame.get("index")
            title = frame.get("title")

            if idx in edited_indexes:
                continue

            if title not in refined_latex:
                errors.append(
                    f"Unedited frame title missing after refinement: {title}"
                )

        for frame in refined_frames:
            idx = frame.get("index")
            body = frame.get("body")

            if idx not in edited_indexes:
                continue

            if not body or not body.strip():
                errors.append(
                    f"Edited frame body is empty for frame index {idx}"
                )
                continue

            body_validation = self.validate_frame_body(body)
            for error in body_validation["errors"]:
                errors.append(
                    f"Edited frame {idx} body failed validation: {error}"
                )

        environments = [
            "itemize",
            "enumerate",
            "block",
            "columns",
            "figure",
            "equation"
        ]

        for env in environments:
            begin_count = len(
                re.findall(rf"\\begin\{{{env}\}}", refined_latex)
            )

            end_count = len(
                re.findall(rf"\\end\{{{env}\}}", refined_latex)
            )

            if begin_count != end_count:
                errors.append(
                    f"Unbalanced LaTeX environment '{env}': "
                    f"begin={begin_count}, end={end_count}"
                )

        if errors:
            return {
                "status": "FAIL",
                "errors": errors
            }

        return {
            "status": "PASS",
            "errors": []
        }

    def validate_frame_body(self, body):
        errors = []

        if not body or not body.strip():
            errors.append("Frame body is empty")
            return {
                "status": "FAIL",
                "errors": errors
            }

        forbidden_patterns = [
            ("\\begin{frame", "Frame body includes frame wrapper"),
            ("\\end{frame}", "Frame body includes frame wrapper"),
            ("\\frametitle", "Frame body includes frame title"),
            ("```", "Markdown code fence detected"),
            ("**", "Markdown bold syntax detected"),
            ("###", "Markdown heading syntax detected"),
            ("[Author", "Placeholder citation detected"),
            ("[Cite", "Placeholder citation detected"),
            ("needed_reference", "Placeholder citation key detected"),
            ("\\cite{", "Citation command detected"),
            ("\\footnote{", "Footnote attribution detected")
        ]

        for pattern, message in forbidden_patterns:
            if pattern in body:
                errors.append(message)

        if self.get_max_list_nesting_depth(body) > 2:
            errors.append("List nesting is too deep for a Beamer slide")

        for env in ["itemize", "enumerate"]:
            pattern = re.compile(
                rf"\\begin\{{{env}\}}(.*?)\\end\{{{env}\}}",
                re.DOTALL
            )
            for match in pattern.finditer(body):
                if "\\item" not in match.group(1):
                    errors.append(
                        f"LaTeX environment '{env}' has no \\item entries"
                    )

        for env in ["itemize", "enumerate", "block", "columns", "figure", "equation"]:
            begin_count = len(re.findall(rf"\\begin\{{{env}\}}", body))
            end_count = len(re.findall(rf"\\end\{{{env}\}}", body))

            if begin_count != end_count:
                errors.append(
                    f"Unbalanced LaTeX environment '{env}': "
                    f"begin={begin_count}, end={end_count}"
                )

        if not self.has_balanced_braces(body):
            errors.append("Unbalanced curly braces detected")

        if self.has_unescaped_ampersand(body):
            errors.append("Unescaped ampersand detected")

        if errors:
            return {
                "status": "FAIL",
                "errors": errors
            }

        return {
            "status": "PASS",
            "errors": []
        }

    def get_max_list_nesting_depth(self, text):
        max_depth = 0
        current_depth = 0
        token_pattern = re.compile(r"\\(begin|end)\{(itemize|enumerate)\}")

        for match in token_pattern.finditer(text):
            action = match.group(1)

            if action == "begin":
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            else:
                current_depth = max(0, current_depth - 1)

        return max_depth

    def has_balanced_braces(self, text):
        cleaned = re.sub(r"\\[{}]", "", text)
        return cleaned.count("{") == cleaned.count("}")

    def has_unescaped_ampersand(self, text):
        for line in text.splitlines():
            if "\\begin{tabular" in line or "\\end{tabular" in line:
                continue

            for match in re.finditer("&", line):
                if match.start() == 0 or line[match.start() - 1] != "\\":
                    return True

        return False


    def retry_refine_frame_body(
        self,
        frame_context,
        feedback_text,
        validation_errors
    ):

        prompt = f"""
You are revising a previously edited Beamer slide frame body.
Your previous refinement attempt failed deterministic validation.
You must fix ONLY the validation issues while preserving useful edits.
---
EVALUATOR FEEDBACK:
{feedback_text}
---
VALIDATION ERRORS:
{validation_errors}
---
FRAME CONTEXT:
{frame_context}
---
RULES:
- Edit ONLY the TARGET FRAME body.
- Preserve valid existing edits whenever possible.
- Fix ONLY the reported validation failures.
- Preserve valid Beamer LaTeX syntax.
- Do NOT add unverifiable external-evidence claims or footnotes.
- Do NOT invent outside materials, authors, dates, organizations, or locator keys.
- Do NOT return frame wrappers.
- Do NOT include markdown fences.
- Return ONLY valid Beamer body content.
---
OUTPUT:

Return ONLY the corrected TARGET FRAME body content.
"""

        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate_response(messages)[0]
        return response

    def parse_frames(self, latex_content):
        frame_pattern = r"\\begin{frame}.*?\\end{frame}"

        frames = re.findall(
            frame_pattern,
            latex_content,
            re.DOTALL
        )

        parsed_frames = []

        for idx, frame in enumerate(frames):
            title_match = re.search(
                r"\\frametitle\{(.*?)\}",
                frame
            )
            title = title_match.group(1) if title_match else "Untitled"
            structure_match = re.search(
                r"(\\begin\{frame\}(?:\[.*?\])?)\s*(\\frametitle\{.*?\})(.*?)(\\end\{frame\})",
                frame,
                re.DOTALL
            )

            if structure_match:
                frame_start = structure_match.group(1).strip()
                title_line = structure_match.group(2).strip()
                body = structure_match.group(3).strip()
                frame_end = structure_match.group(4).strip()

            else:
                frame_start = None
                title_line = None
                body = None
                frame_end = None

            parsed_frames.append({
                "index": idx,
                "title": title,
                "content": frame,
                "original_content": frame,
                "frame_start": frame_start,
                "title_line": title_line,
                "body": body,
                "frame_end": frame_end
            })

        return parsed_frames

    def build_frame_summary(self, frames):
        frame_summary_text = ""

        for frame in frames:
            index = frame.get("index")
            title = frame.get("title")

            frame_summary = f"Frame {index}: {title}\n"
            frame_summary_text += frame_summary

        return frame_summary_text


    def locate_frames(self, feedback_text, frame_summary):
        prompt = f"""
You are a slide-deck reviewer.
Your job is to identify which slide frames are MOST LIKELY responsible
for the evaluator feedback.
You are NOT rewriting slides.
You are NOT evaluating the entire deck.
You are ONLY locating likely problem regions.
---
FEEDBACK:
{feedback_text}
---
FRAME SUMMARY:
{frame_summary}
---
RULES:
- Use the frame titles to infer which frames are most related to the feedback.
- Select ONLY the frames most likely connected to the reported weaknesses.
- Prefer precision over recall.
- Do NOT select frames unless there is a reasonable connection to the feedback.
- Keep the list compact.
- Return a maximum of 5 frames.
- If multiple adjacent frames appear related, include only the most relevant ones.
- Use short reasoning phrases, not long explanations.
---
OUTPUT FORMAT (STRICT):
TARGET_FRAMES:
- Frame <index>: <short reason>
- Frame <index>: <short reason>
If no strong match exists:
TARGET_FRAMES:
- None confidently identified
---
Return ONLY the output.
"""
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate_response(messages)[0]
        return response


    def parse_target_frame_indexes(self, locator_response):
        if not locator_response:
            return []
        index_pattern = r"Frame\s+(\d+)"
        indexes = re.findall(index_pattern, locator_response)
        return sorted(set(int(idx) for idx in indexes))

    def get_target_frames(self, frames, target_indexes):

        target_frames = []
        for frame in frames:
            index = frame.get("index")

            if index in target_indexes:
                target_frames.append(frame)

        return target_frames

    def build_target_frame_context(self, frames, target_frame):

        idx = target_frame.get("index")

        context_text = ""
        # Previous frame
        if idx > 0:
            prev_frame = frames[idx - 1]
            context_text += f"""
    PREVIOUS FRAME:
    Frame {prev_frame.get("index")}: {prev_frame.get("title")}
    """

        # Target frame
        context_text += f"""
    TARGET FRAME:
    Frame {target_frame.get("index")}: {target_frame.get("title")}
    {target_frame.get("content")}
    """

        # Next frame
        if idx < len(frames) - 1:
            next_frame = frames[idx + 1]
            context_text += f"""
    NEXT FRAME:
    Frame {next_frame.get("index")}: {next_frame.get("title")}
    """
        return context_text.strip()



    def refine_frame_body(self, frame_context, feedback_text):

        prompt = f"""
    You are a careful Beamer LaTeX slide editor.

    Your job is to repair ONLY the BODY of one target frame using evaluator feedback.

    You are NOT rewriting the slide deck.
    You are NOT rewriting neighboring frames.
    You are ONLY editing the body content of the TARGET FRAME.

    ---

    EVALUATOR FEEDBACK:
    {feedback_text}

    ---

    FRAME CONTEXT:
    {frame_context}

    ---

    RULES:

    - Edit ONLY the TARGET FRAME body.
    - Do NOT edit neighboring frames.
    - Preserve useful existing body content whenever possible.
    - Make the smallest useful changes needed to address the feedback.
    - Keep the slide concise and presentation-friendly.
    - Preserve valid Beamer LaTeX syntax.
    - Preserve existing formatting structure when possible.
    - Do NOT add unverifiable external-evidence claims or footnotes.
    - Do NOT invent outside materials, authors, dates, organizations, or locator keys.
    - Ignore feedback that requires unavailable outside evidence.
    - Focus on clarity, alignment, examples, depth, structure, and learner accessibility.
    - If reducing density, simplify or condense content instead of expanding it.
    - Do not add unnecessary sections or filler content.

    ---

    IMPORTANT OUTPUT RULES:

    - Do NOT return \\begin{{frame}}
    - Do NOT return \\frametitle{{...}}
    - Do NOT return \\end{{frame}}
    - Do NOT include markdown fences.
    - Return ONLY valid Beamer frame BODY content.
    - Return ONLY the revised body for the TARGET FRAME.

    ---

    OUTPUT:

    Return ONLY the revised TARGET FRAME body content.
    """

        messages = [{"role": "user", "content": prompt}]

        response = self.llm.generate_response(messages)[0]

        return response


    def rebuild_frame(self, frame, new_body):
        frame_start = frame.get("frame_start")
        title_line = frame.get("title_line")
        frame_end = frame.get("frame_end")

        if not frame_start or not title_line or not frame_end:
            return frame.get("content")

        new_body = new_body.strip()

        new_frame = f"""{frame_start}
{title_line}
{new_body}
{frame_end}"""

        return new_frame

    def replace_frames(self, frames, frame_index, new_frame_content):
        for frame in frames:
            idx = frame.get("index")

            if idx == frame_index:
                frame["content"] = new_frame_content
        return frames

    def reassemble_slides(self, original_latex, frames):
        updated_latex = original_latex

        for frame in frames:
            original_frame = frame.get("original_content")
            current_frame = frame.get("content")

            if not original_frame or not current_frame:
                continue
            if original_frame == current_frame:
                continue

            updated_latex = updated_latex.replace(
                original_frame,
                current_frame,
                1
            )
        return updated_latex


