from src.agents import LLM


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





    def plan(self, constraints, content_type):
        prompt = f"""
Constraints = {constraints}
Content Type = {content_type}
"""
        messages = [{"role": "user", "content": prompt}]
        plan = self.llm.generate_response(messages)[0]
        return plan





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

        for i in range(max_retries):
            validation = self.validate(
                original_content=content,
                response=response,
                constraints=constraints,
                content_type=content_type
            )

            if validation["status"] == "PASS":
                return response

            response = self.generate_with_retry(
                original_content=content,
                previous_response=response,
                validation=validation["raw"],
                constraints=constraints,
                content_type=content_type
            )

        return response



class RefinementEngine:
    def __init__(self, llm):
        self.llm = llm
        self.refiner = Refiner(llm)

    def format_metrics_feedback(self, packet):

        feedback_text = f"""
        File: {packet.get("eval_filename")}
        Type: {packet.get("file_type")}
        Average Score: {packet.get("average")}
        """

        metrics = packet.get("metrics", {})

        for metric_name, metric_data in metrics.items():

            score = metric_data.get("score")
            thought = metric_data.get("thought")

            feedback_text += f"""
            Metric: {metric_name}
            Score: {score}
            Feedback: {thought}
            """

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
        if packet["route"] != "assessment":
            raise NotImplementedError("Sorry this file type isn't implemented yet")

        feedback_text = self.format_metrics_feedback(packet)
        content_type = self.get_content_type(packet["route"])
        constraints = self.refiner.translate_feedback(feedback_text, content_type)

        refined_content = self.refiner.run_refinement_loop(
            content=packet["content"],
            constraints=constraints,
            content_type=content_type,
            max_retries=retries
        )

        return {
            "eval_filename": packet["eval_filename"],
            "route": packet["route"],
            "constraints": constraints,
            "refined_content": refined_content,
            "max_attempts": retries
        }
