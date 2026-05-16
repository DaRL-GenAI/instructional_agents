from src.agents import LLM
from src.latex_to_pptx import LaTeXParser
import re



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
- Do NOT add citations, references, source notes, bibliography entries, footnotes, or attribution text.
- Do NOT invent sources, authors, years, URLs, papers, books, organizations, or citation keys.
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
    - Do NOT add citations, references, source notes, bibliography entries, footnotes, or attribution text.
    - Do NOT invent sources, authors, years, URLs, papers, books, organizations, or citation keys.
    - If evaluator feedback asks for attribution or citations, do NOT repair that issue in slide text.
    - Focus on non-attribution issues such as clarity, alignment, examples, depth, structure, and learner accessibility.
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

class Refiner():

    def __init__(self, llm):
        self.llm = llm

    def get_constraint_policy(self, content_type):
        if content_type == "assessment":
            return """
ASSESSMENT CONSTRAINT POLICY:

- Constraints may refer to assessment items, activities, rubrics, scoring guides, feedback, question formats, and learning-objective alignment.
- If feedback asks for higher-order thinking, define it as learner-produced reasoning, application, analysis, synthesis, evaluation, design, or justification.
- Do not let selected-response items count as higher-order unless learners must also write or explain reasoning and that reasoning has evaluation guidance.
- Prefer assessment-type-level rubrics over repeated scoring blocks after every question.
- If feedback asks for more rubrics or scoring criteria, scope them to major task types unless feedback explicitly requires item-level rubrics.
- If feedback asks for more variety, require a balanced mix across the whole assessment, not the same mix in every section.
- If feedback asks for feedback mechanisms, prefer reusable peer/self/instructor feedback directions tied to task types rather than repeated generic feedback after every question.
"""

        if content_type == "slides":
            return """
SLIDES CONSTRAINT POLICY:

- Slide refinement is not implemented yet.
- Do not generate detailed slide repair constraints until the slide refinement architecture is designed.
"""

        return """
GENERAL CONSTRAINT POLICY:

- General refinement is not implemented yet.
- Use only conservative, document-preserving constraints if this route is enabled later.
"""

    def get_generation_policy(self, content_type):
        if content_type == "assessment":
            return """
ASSESSMENT GENERATION POLICY:

- Preserve useful assessment questions, activities, learning objectives, explanations, and discussion prompts.
- Keep MCQs as MCQs when they are useful and allowed by constraints.
- A task only qualifies as higher-order if it requires reasoning, analysis, synthesis, application, transfer to a new scenario, or meaningful justification beyond factual recall.
- Adding the phrase "higher-order" or adding verbs like "analyze" does not make an item higher-order.
- Do not create fake higher-order MCQs by adding verbs like analyze, justify, evaluate, reflect, discuss, compare, or design while keeping only A/B/C/D choices.
- If a selected-response item requires reasoning, write it as two parts:
  1. select the best answer
  2. provide a brief justification
  Then include concise criteria for the justification.
- If a task is truly open-ended, remove A/B/C/D choices and provide expected-response guidance or a rubric.
- Prefer compact rubrics for major task types, activities, or sections. Do not add near-identical scoring criteria after every question unless the constraint explicitly requires item-level scoring.
- Feedback mechanisms should be reusable and specific: peer review, self-reflection, revision guidance, instructor checkpoints, or answer-improvement prompts tied to task types.
- Limit added material. If one rubric can cover a task type, do not repeat it many times.
"""

        if content_type == "slides":
            return """
SLIDES GENERATION POLICY:

- Slide refinement is not implemented yet.
- Do not attempt slide generation with this prompt policy.
"""

        return """
GENERAL GENERATION POLICY:

- General refinement is not implemented yet.
- Do not attempt general document generation with this prompt policy unless a route-specific design has been added.
"""

    def get_validation_policy(self, content_type):
        if content_type == "assessment":
            return """
ASSESSMENT VALIDATION POLICY:

- Check whether MCQ, constructed-response, activity, project, presentation, discussion, and reflection tasks have valid matching answer/scoring structures.
- A question with higher-order verbs such as analyze, justify, evaluate, reflect, discuss, compare, design, or explain in depth must require learner-produced reasoning. If it only has A/B/C/D choices and a letter answer, mark Format consistency as FAIL.
- If a selected-response item includes a written justification part, check that the justification has expected-response guidance or scoring criteria.
- Do not count repeated generic scoring blocks as high-quality rubrics.
- Prefer reusable task-type rubrics when they cover the relevant tasks clearly.
- Check whether required feedback mechanisms are actionable and tied to learner improvement, not just named.
- Check distribution constraints across the whole assessment, not by assuming each section must look identical.
"""

        if content_type == "slides":
            return """
SLIDES VALIDATION POLICY:

- Slide refinement is not implemented yet.
- Mark slide validation as unsupported if this route is reached before implementation.
"""

        return """
GENERAL VALIDATION POLICY:

- General refinement is not implemented yet.
- Mark general validation as unsupported if this route is reached before implementation.
"""

    def translate_feedback(self, feedback, content_type="general"):
        policy = self.get_constraint_policy(content_type)
        prompt = f"""
You are an expert evaluator and instructional systems designer.

Your job is to convert evaluation feedback into TARGETED REPAIR CONSTRAINTS
that control another LLM's behavior.

You are NOT rewriting the content.
You are NOT designing a new instructional artifact from scratch.
You are building a compact repair brief.

Each feedback item MUST be converted into:

ERROR: <specific failure in current output>
ACTION: <what must change>
CONSTRAINT: <strict, measurable rule that forces the smallest useful repair>

---

ENFORCEMENT RULES (CRITICAL):

- Treat feedback as authoritative for the identified weaknesses.
- Constraints should repair weak regions without disturbing unrelated strong content.
- Translate only substantive problems into constraints.
- Preserve good existing structure wherever possible.
- Prefer patching weak regions over replacing the whole document.
- If feedback implies removal/reduction, define MAX limits.
- If feedback implies addition/increase, define MIN thresholds.
- If feedback implies balance, define BOTH MIN and MAX ranges.
- If feedback implies change in type, force a limited structural transformation.

---

SCOPE CONTROL RULES:

- DO NOT force every section to follow the same structural pattern.
- DO NOT require repeated support structures after every individual item unless feedback explicitly demands it.
- Prefer section-level, assessment-type-level, or activity-level support structures over item-level ones.
- Keep added instructions concise: 1-3 bullets unless feedback explicitly asks for more.
- Keep added guidance concise and scoped to major tasks or weak regions.
- Do not create constraints that force large document expansion unless unavoidable.
- Preserve the document's existing content type and purpose.
- Do not require a full rewrite when a local repair can satisfy the feedback.

---

ANTI-WEAKNESS RULES:

- DO NOT paraphrase feedback
- DO NOT stay abstract
- DO NOT use vague words like "improve", "enhance", "better"
- DO NOT output soft suggestions
- DO NOT overfit by requiring the same repair everywhere

---

CONSTRAINT QUALITY RULES:

Every CONSTRAINT must be:

- measurable (counts, %, required sections, or required wording)
- enforceable (LLM cannot ignore it)
- scoped (states WHERE the change should happen)
- conservative (minimizes unnecessary rewriting)
- format-aware (does not create invalid structures for the content type)

---

FORCING LOGIC (VERY IMPORTANT):

If feedback says:

- content is repetitive → enforce structural diversity and limit repeated patterns
- too much of one format/type → enforce BOTH:
  - MAX % for dominant format
  - MIN % for alternative formats/types

- lacks higher-order thinking → enforce:
  - MIN % of reasoning/application-based tasks
  - DEFINE what qualifies as higher-order thinking

- lacks variety → enforce:
  - Multiple distinct formats/types across the document
  - NO single format dominating the document
  - Diversity should exist across the whole document, not necessarily every section

- missing support structures → enforce:
  - Rubrics, guidance, examples, or feedback only where pedagogically necessary
  - Compact support structures preferred unless feedback explicitly requests detail
  - State what the support structure must contain, not just that it must exist

- weak feedback or guidance → enforce:
  - Actionable and concise guidance tied to major tasks or weak regions

- unclear assessment expectations → enforce:
  - Clear learner-facing directions for major task types
  - Criteria that explain how quality will be judged

- selected-response assessments are too dominant → enforce:
  - Some selected-response items may remain
  - A limited number of items should be converted into constructed-response, applied, reflective, or project-style tasks

---

CONTENT-SPECIFIC POLICY:

{policy}

---

OUTPUT FORMAT (STRICT):

ERROR: ...
ACTION: ...
CONSTRAINT: ...

(No extra text. No explanations.)

---

FEEDBACK:
{feedback}
"""
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate_response(messages)[0]
        return response




    def generate(self, content, constraints, content_type):
        policy = self.get_generation_policy(content_type)
        prompt = f"""
You are a careful instructional document editor.

Your job is to repair the original content with the smallest set of changes
needed to satisfy the constraints.

You are NOT creating a new document from scratch.
You are preserving good existing content and patching weak parts.

---

ORIGINAL CONTENT:
{content}

---

CONSTRAINTS:
{constraints}

---

CONTENT TYPE:
{content_type}

---

CORE RULE:

Constraints override the original content only where there is a conflict.
If original content already works, preserve it.

---

PRESERVATION RULES:

- Preserve existing headings and section order.
- Preserve useful existing questions, activities, explanations, and examples.
- Do not expand the document more than necessary.
- Do not repeat the same repair pattern mechanically in every section.
- Do not convert all content into one uniform template.
- Do not remove useful content unless it conflicts with constraints.

---

STRICT EXECUTION RULES:

- Satisfy every constraint.
- Respect numeric thresholds.
- Use targeted edits rather than full redesign.
- If a small addition satisfies a constraint, prefer the small addition.
- If an existing element can be revised instead of replaced, revise it.
- Keep content-specific structures valid according to the content type policy.
- When converting an element from one format to another, update surrounding support content so the result remains internally consistent.
- Do not satisfy a requirement by adding labels only; the underlying task must actually change.

---

STRUCTURAL PLANNING:

Before generating output, you MUST internally:

1. Determine the major content/task types present in the document
2. Categorize important item types and identify dominant patterns
3. PLAN the distribution so that ALL constraints are satisfied:
   - No single format or type exceeds its MAX constraint
   - Required types or patterns meet MIN constraints
   - Diversity is present across the document
4. If constraints are violated:
   - Apply the minimum structural/content changes necessary to satisfy them

---

ANTI-CHEATING (ENFORCEMENT):

- You MUST NOT fake compliance by adding labels without changing task demands
- You MUST apply real structural/content changes when required
- You MUST reduce excess formats if they violate MAX constraints

---

ANTI-COLLAPSE RULES (CRITICAL):

- You MUST NOT eliminate entire useful content categories unless explicitly required
- If constraints require reduction, REDUCE but DO NOT REMOVE completely
- Maintain a BALANCED distribution when constraints imply variety
- Avoid repeating the same repair pattern across most sections

---

DISTRIBUTION ENFORCEMENT:

- Respect BOTH minimum AND maximum percentages
- If a format/type has a MAX limit → ensure it does NOT exceed it
- If a format/type has a MIN requirement → ensure it is satisfied

---

HARD TRANSFORMATION LOGIC:

If constraints require:

- reduction → modify or remove only enough content to satisfy the limit
- increase → add only enough material to satisfy the minimum requirement
- variety → diversify patterns/types across the document
- higher-order thinking → selectively transform low-depth content into reasoning/application-based content
- support structures → add compact rubrics, guidance, examples, or feedback where needed
- feedback/guidance → add concise actionable guidance tied to weak regions

---

ANTI-CHEATING RULES:

- DO NOT satisfy constraints by adding filler text
- DO NOT append generic sections without fixing core issues
- DO NOT leave clearly weak content unchanged when constraints directly target it

---

QUALITY CHECK BEFORE OUTPUT:

You MUST internally verify:

1. All constraints are satisfied
2. No constraint is partially satisfied
3. Distribution constraints are respected
4. Structure reflects required transformations

If ANY constraint is not satisfied → FIX before output

---

CONTENT TYPE RULES:

{policy}

---

OUTPUT:

Return ONLY the final improved content in the same general format as the original.
NO explanations.
NO meta commentary.
"""

        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate_response(messages)[0]
        return response

    def generate_with_retry(
        self,
        original_content,
        previous_response,
        validation,
        constraints,
        content_type
    ):
        policy = self.get_generation_policy(content_type)
        prompt = f"""
You are revising a previous refinement attempt after reviewer feedback.

Your job is to fix only the issues identified in VALIDATION while preserving
the original content and any already-successful repairs.

---

ORIGINAL CONTENT:
{original_content}

---

PREVIOUS REFINEMENT:
{previous_response}

---

VALIDATION OF PREVIOUS REFINEMENT:
{validation}

---

ORIGINAL CONSTRAINTS:
{constraints}

---

CONTENT TYPE:
{content_type}

---

CORE RULE:

Reviewer feedback identifies remaining failures in the PREVIOUS REFINEMENT.

Your job is to:
- preserve successful repairs from the previous refinement
- modify only the regions that still violate constraints
- continue satisfying every original constraint
- avoid unnecessary rewrites of already-correct sections

Fix failures with the smallest necessary changes.

---

STRICT EXECUTION RULES:

- Do not start over unless validation explicitly says the structure is unusable.
- Preserve sections that already satisfy the constraints.
- Do not add repetitive support or feedback blocks everywhere unless required.
- Do not expand the document more than needed.
- Keep the original heading structure when possible.
- Keep content-specific structures valid according to the content type policy.
- When converting an element from one format to another, update surrounding support content so the result remains internally consistent.
- Do not satisfy a requirement by adding labels only; the underlying task must actually change.

---

STRUCTURAL PLANNING (CRITICAL):

Before generating output, you MUST internally:

1. Determine the major content/task types present in the document
2. Categorize important item types and identify dominant patterns
3. PLAN the distribution so that ALL constraints are satisfied:
   - No single format or type exceeds its MAX constraint
   - Required types or patterns meet MIN constraints
   - Diversity is present across the document
4. If constraints are violated:
   - Apply the minimum structural/content changes necessary to satisfy them

---

ANTI-CHEATING (ENFORCEMENT):

- You MUST NOT fake compliance by adding labels without changing task demands
- You MUST apply real structural/content changes when required
- You MUST reduce excess formats if they violate MAX constraints

---

ANTI-COLLAPSE RULES (CRITICAL):

- You MUST NOT eliminate entire useful content categories unless explicitly required
- If constraints require reduction, REDUCE but DO NOT REMOVE completely
- Maintain a BALANCED distribution when constraints imply variety
- Avoid repeating the same repair pattern across most sections

---

DISTRIBUTION ENFORCEMENT:

- Respect BOTH minimum AND maximum percentages
- If a format/type has a MAX limit → ensure it does NOT exceed it
- If a format/type has a MIN requirement → ensure it is satisfied

---

HARD TRANSFORMATION LOGIC:

If constraints require:

- reduction → modify or remove only enough content to satisfy the limit
- increase → add only enough material to satisfy the minimum requirement
- variety → diversify patterns/types across the document
- higher-order thinking → selectively transform low-depth content into reasoning/application-based content
- support structures → add compact rubrics, guidance, examples, or feedback where needed
- feedback/guidance → add concise actionable guidance tied to weak regions

---

ANTI-CHEATING RULES:

- DO NOT satisfy constraints by adding filler text
- DO NOT append generic sections without fixing core issues
- DO NOT leave clearly weak content unchanged when constraints directly target it

---

QUALITY CHECK BEFORE OUTPUT:

You MUST internally verify:

1. All constraints are satisfied
2. No constraint is partially satisfied
3. Distribution constraints are respected
4. Structure reflects required transformations

If ANY constraint is not satisfied → FIX before output

---

CONTENT TYPE RULES:

{policy}

---

OUTPUT:

Return ONLY the final improved content in the same general format as the original.
NO explanations.
NO meta commentary.
"""
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate_response(messages)[0]
        return response


    def validate(self, original_content, response, constraints, content_type="general"):
        policy = self.get_validation_policy(content_type)
        prompt = f"""
You are a strict instructional artifact reviewer.

Your job is to determine whether the generated response satisfies ALL constraints
without unnecessary overgeneration or cosmetic compliance.

---

CONSTRAINTS:
{constraints}
---

ORIGINAL CONTENT:
{original_content}

---

GENERATED RESPONSE:
{response}

---

VALIDATION RULES:

- Check every constraint separately.
- Enforce numeric thresholds exactly. If a constraint uses a count, percentage, maximum, minimum, or "all/every", verify it from the generated response.
- Enforce structural requirements exactly. A required rubric, feedback mechanism, example, instruction, answer guide, or activity type must actually exist and be specific enough to use.
- Partial compliance is NOT acceptable.
- If even one constraint is violated, STATUS must be FAIL.
- If the response satisfies constraints by bloating the document unnecessarily, STATUS must be FAIL.
- If the response applies repetitive repair patterns mechanically across most of the document, STATUS must be FAIL.
- Preserve useful original structure and content unless constraints explicitly require major restructuring.
- Large rewrites of already-correct sections should be treated as unnecessary overgeneration.
- Do not infer compliance. Cite direct evidence from the generated response.

---

COSMETIC COMPLIANCE CHECKS:

STATUS must be FAIL if the response only appears compliant because it:

- adds labels like "higher-order", "rubric", "feedback", or "criteria" without changing the actual task or support structure
- adds generic filler that is not tied to a specific task, learner action, or evaluation criterion
- repeats the same repair pattern across sections without pedagogical reason
- adds support structures that are too vague for a learner or instructor to use

---

ASSESSMENT FORMAT CHECKS:

When the response is an assessment or contains assessment items:

- Multiple-choice items must have answer choices and a correct answer that matches one of those choices.
- Open-ended, analysis, comparison, design, reflection, project, presentation, or activity tasks must NOT use only a letter as the answer.
- Constructed-response tasks need an expected-response guide, rubric, criteria, or clear evaluation guidance.
- If a task asks the learner to justify, compare, analyze, design, evaluate, or apply, its answer/scoring support must match that demand.
- A selected-response item with higher-order verbs such as analyze, justify, evaluate, reflect, discuss, compare, or design must include a real constructed-response component and evaluation guidance. If it only has A/B/C/D choices plus a letter answer, mark Format consistency as FAIL.
- Do not count a selected-response item as higher-order merely because its wording contains a higher-order verb. Count it only when the learner must produce reasoning, apply a concept to a scenario, or justify an answer, and the response includes guidance for evaluating that reasoning.
- If the response converts an item from one format to another, the answer key, explanation, and scoring guidance must be converted too.

---

CONTENT-SPECIFIC VALIDATION POLICY:

{policy}

---

PRESERVATION AND SIZE CHECKS:

- Compare the generated response to the original content.
- Passing requires targeted repair, not arbitrary redesign.
- Added material must be traceable to a constraint.
- Removed material must either be unnecessary duplication or conflict with a constraint.
- Size changes are acceptable only when justified by the constraints.

---

PASS STANDARD:

STATUS may be PASS only if:

- every constraint is fully satisfied
- the generated response is internally consistent
- assessment item formats are valid when assessment items are present
- required support structures are usable, not just named
- the original artifact's useful structure is preserved
- no major unnecessary expansion, deletion, or repetitive pattern was introduced

---

OUTPUT FORMAT (STRICT):

STATUS: PASS or FAIL
CONSTRAINT CHECKS:
- <constraint summary>: PASS/FAIL - <direct evidence or missing requirement; include counts/percentages when relevant>
- <constraint summary>: PASS/FAIL - <direct evidence or missing requirement; include counts/percentages when relevant>
STRUCTURAL CHECKS:
- Format consistency: PASS/FAIL - <evidence>
- Preservation/scope control: PASS/FAIL - <evidence>
- Non-cosmetic compliance: PASS/FAIL - <evidence>
REASON: <short explanation>
FIXES REQUIRED:
- <required fix>
- <required fix>

---

Return ONLY the validation result.
"""

        messages = [{"role": "user", "content": prompt}]

        validation_text = self.llm.generate_response(messages)[0]

        validation_text = validation_text.strip()

        if validation_text.startswith("STATUS: PASS"):
            status = "PASS"
        else:
            status = "FAIL"

        return {
            "status": status,
            "raw": validation_text
        }

    def run_refinement_loop(self, content, constraints, content_type, max_retries=3):
        response = self.generate(content, constraints, content_type)
        validations = []
        retries_used = 0

        for i in range(max_retries + 1):
            validation = self.validate(
                original_content=content,
                response=response,
                constraints=constraints,
                content_type=content_type
            )
            validations.append(validation)

            if validation["status"] == "PASS":
                return {
                    "refined_content": response,
                    "validation_status": "PASS",
                    "retries_used": retries_used,
                    "final_validation": validation["raw"],
                    "validation_history": validations
                }

            if i == max_retries:
                return {
                    "refined_content": response,
                    "validation_status": "FAIL",
                    "retries_used": retries_used,
                    "final_validation": validation["raw"],
                    "validation_history": validations
                }

            response = self.generate_with_retry(
                original_content=content,
                previous_response=response,
                validation=validation["raw"],
                constraints=constraints,
                content_type=content_type
            )
            retries_used += 1

        return {
            "refined_content": response,
            "validation_status": "FAIL",
            "retries_used": retries_used,
            "final_validation": "",
            "validation_history": validations
        }



class RefinementEngine:
    def __init__(self, llm):
        self.llm = llm
        self.refiner = Refiner(llm)
        self.slide_refiner = SlideRefiner(llm)

    def format_metrics_feedback(self, packet, excluded_metrics=None):
        excluded_metrics = excluded_metrics or []

        feedback_text = f"""
        File: {packet.get("eval_filename")}
        Type: {packet.get("file_type")}
        Average Score: {packet.get("average")}
        """

        metrics = packet.get("metrics", {})

        for metric_name, metric_data in metrics.items():
            if metric_name in excluded_metrics:
                continue

            score = metric_data.get("score")
            thought = metric_data.get("thought")

            feedback_text += f"""
            Metric: {metric_name}
            Score: {score}
            Feedback: {thought}
            """

        validation_feedback = packet.get("validation_feedback")
        if validation_feedback:
            feedback_text += "\n\nVALIDATION FEEDBACK:\n\n"
            feedback_text += validation_feedback

        return feedback_text

    def get_content_type(self, route):
        if route == "assessment":
            return route
        elif route == "slides":
            return route
        elif route == "script":
            return "general"
        elif route == "syllabus":
            return "general"
        elif route == "objectives":
            return "general"
        else:
            return "general"




    def refine_packet(self, packet, retries):
        if packet["route"] == "assessment":

            feedback_text = self.format_metrics_feedback(packet)
            content_type = self.get_content_type(packet["route"])
            constraints = self.refiner.translate_feedback(feedback_text, content_type)

            refinement_result = self.refiner.run_refinement_loop(
                content=packet["content"],
                constraints=constraints,
                content_type=content_type,
                max_retries=retries
            )
            return {
                "eval_filename": packet["eval_filename"],
                "route": packet["route"],
                "constraints": constraints,
                "repair_plan": None,
                "structure_facts": None,
                "original_structure_facts": None,
                "refined_content": refinement_result["refined_content"],
                "validation_status": refinement_result["validation_status"],
                "retries_used": refinement_result["retries_used"],
                "final_validation": refinement_result["final_validation"],
                "validation_history": refinement_result["validation_history"],
                "max_retries": retries
            }

        elif packet["route"] == "slides":

            feedback_text = self.format_metrics_feedback(
                packet,
                excluded_metrics=["attribution"]
            )

            slide_result = self.slide_refiner.refine_slides(
                content=packet["content"],
                feedback_text=feedback_text,
                max_retries=retries
            )

            return {
                "eval_filename": packet["eval_filename"],
                "route": packet["route"],
                "constraints": feedback_text,
                "repair_plan": slide_result["locator_response"],
                "structure_facts": {
                    "target_indexes": slide_result["target_indexes"],
                    "edited_frames": slide_result["edited_frames"]
                },
                "original_structure_facts": None,
                "refined_content": slide_result["refined_content"],
                "validation_status": slide_result["slide_validation_status"],
                "retries_used": slide_result["retries_used"],
                "final_validation": "\n".join(
                    slide_result["slide_validation_errors"]
                ),
                "validation_history": slide_result["validation_history"],
                "slide_validation_errors": slide_result["slide_validation_errors"],
                "compile_status": "NOT_RUN",
                "compile_errors": [],
                "max_retries": retries
            }

        else:
            raise NotImplementedError("Current directory not implemented")
