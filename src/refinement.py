from src.agents import LLM


class Refiner():

    def __init__(self, llm):
        self.llm = llm

    def translate_feedback(self, feedback):
        prompt = f"""
You are an expert evaluator and instructional systems designer.

Your job is to convert feedback into HARD CONSTRAINTS that CONTROL another LLM’s behavior.

You are NOT summarizing feedback.
You are BUILDING ENFORCEMENT RULES.

Each feedback item MUST be converted into:

ERROR: <specific failure in current output>
ACTION: <what must change>
CONSTRAINT: <strict, measurable rule that forces the change>

---

ENFORCEMENT RULES (CRITICAL):

- Treat feedback as AUTHORITY. Your constraints OVERRIDE the original content behavior.
- You MUST translate EVERY feedback item into at least one constraint block
- If feedback implies removal/reduction → define MAX limits
- If feedback implies addition/increase → define MIN thresholds
- If feedback implies balance → define BOTH MIN and MAX ranges
- If feedback implies change in type → FORCE structural transformation

---

ANTI-WEAKNESS RULES:

- DO NOT paraphrase feedback
- DO NOT stay abstract
- DO NOT use vague words like "improve", "enhance", "better"
- DO NOT output soft suggestions

---

CONSTRAINT QUALITY RULES:

Every CONSTRAINT must be:

- measurable (%, counts, required sections)
- enforceable (LLM cannot ignore it)
- structural (changes behavior, not wording)

---

FORCING LOGIC (VERY IMPORTANT):

If feedback says:

- "too many MCQs" → enforce BOTH:
  - MAX % of MCQs (e.g., ≤ 40%)
  - MIN % of non-MCQ formats (e.g., ≥ 60%)

- "needs higher-order thinking" → enforce:
  - MIN % of application/analysis questions (e.g., ≥ 40%)
  - DEFINE what qualifies: must require explanation, reasoning, or scenario-based thinking

- "lack of variety" → enforce:
  - At least 3 distinct assessment formats
  - NO single format > 50% of total

- "missing rubric" → enforce:
  - Rubric REQUIRED per question OR per section
  - At least 3 criteria AND 3 performance levels

- "weak feedback" → enforce:
  - Feedback MUST be tied to each section or task
  - Minimum length AND actionable (must include how to improve)

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
        response,_,_ = self.llm.generate_response(messages)

        return response
    




    def plan(self, constraints, content_type):
        prompt = f"""
Constraints = {constraints}
Content Type = {content_type}
"""
        messages = [{"role": "user", "content": prompt}]

        plan, _, _ = self.llm.generate_response(messages)
        
        return plan

        



    def generate(self, content, constraints, content_type):
        prompt = f"""
You are a strict execution engine for instructional refinement.

You MUST apply ALL CONSTRAINTS exactly.
You are NOT allowed to partially follow them.

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

Constraints OVERRIDE the original content.
If original content conflicts → YOU MUST CHANGE IT.

---

STRICT EXECUTION RULES:

- You MUST satisfy EVERY constraint
- You MUST NOT ignore numeric thresholds
- You MUST NOT keep old structure if it violates constraints
- You MUST transform content, not decorate it

---

STRUCTURAL PLANNING (CRITICAL):

Before generating output, you MUST internally:

1. Determine total number of assessment items
2. Categorize each item into:
   - MCQ
   - open-ended
   - application/scenario-based
   - project/activity

3. PLAN the distribution so that ALL constraints are satisfied:
   - MCQ percentage ≤ MAX constraint
   - Higher-order questions ≥ MIN constraint
   - At least 3 distinct formats present

4. If distribution does NOT satisfy constraints:
   - RESTRUCTURE content BEFORE writing output

---

HIGHER-ORDER DEFINITION (STRICT):

A question ONLY qualifies as higher-order if it:

- Requires multi-step reasoning OR
- Requires applying concepts to a new scenario OR
- Requires justification beyond recalling facts

Adding "explain why" to a recall question DOES NOT count.

---

ANTI-CHEATING (ENFORCEMENT):

- You MUST NOT fake compliance by keeping MCQs and adding explanations
- You MUST CONVERT question types when required
- You MUST REMOVE excess formats if they violate MAX constraints

---

ANTI-COLLAPSE RULES (CRITICAL):

- You MUST NOT eliminate entire question types unless explicitly required
- If constraints require reduction (e.g., MCQs), REDUCE but DO NOT REMOVE completely
- Maintain a BALANCED distribution when constraints imply variety

---

DISTRIBUTION ENFORCEMENT:

- Respect BOTH minimum AND maximum percentages
- If a format has a MAX limit → ensure it does NOT exceed it
- If a format has a MIN requirement → ensure it is satisfied

---

HARD TRANSFORMATION LOGIC:

If constraints require:

- reduction → REMOVE excess content
- increase → ADD new content until threshold is met
- variety → REPLACE or MIX formats to satisfy distribution
- higher-order thinking → CONVERT questions (not just add explanation)
- rubric → ADD structured rubric (criteria + levels)
- feedback → ADD actionable improvement guidance PER SECTION or TASK

---

ANTI-CHEATING RULES:

- DO NOT satisfy constraints by adding filler text
- DO NOT append generic sections without fixing core issues
- DO NOT leave original low-quality questions unchanged

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

If content_type == "slides":
- bullet points only
- concise but meaningful

If content_type == "assessment":
- MUST upgrade question types
- MUST include applied/reasoning questions
- MUST enforce variety AND distribution
- MUST include rubrics where required

If content_type == "general":
- preserve format but improve depth

---

OUTPUT:

Return ONLY the final improved content.
NO explanations.
NO meta commentary.
"""
        
        messages = [{"role": "user", "content": prompt}]
        
        response, _, _ = self.llm.generate_response(messages)

        return response
    
    def generate_with_retry(self, content, validation, content_type):
        prompt = f"""
You are a strict execution engine for instructional refinement.

You MUST apply ALL CONSTRAINTS exactly.
You are NOT allowed to partially follow them.

---

ORIGINAL CONTENT:
{content}

---

VALIDATION:
{validation}

---

CONTENT TYPE:
{content_type}

---

CORE RULE:

Constraints OVERRIDE the original content.
If original content conflicts → YOU MUST CHANGE IT.

---

STRICT EXECUTION RULES:

- You MUST satisfy EVERY constraint
- You MUST NOT ignore numeric thresholds
- You MUST NOT keep old structure if it violates constraints
- You MUST transform content, not decorate it

---

STRUCTURAL PLANNING (CRITICAL):

Before generating output, you MUST internally:

1. Determine total number of assessment items
2. Categorize each item into:
   - MCQ
   - open-ended
   - application/scenario-based
   - project/activity

3. PLAN the distribution so that ALL constraints are satisfied:
   - MCQ percentage ≤ MAX constraint
   - Higher-order questions ≥ MIN constraint
   - At least 3 distinct formats present

4. If distribution does NOT satisfy constraints:
   - RESTRUCTURE content BEFORE writing output

---

HIGHER-ORDER DEFINITION (STRICT):

A question ONLY qualifies as higher-order if it:

- Requires multi-step reasoning OR
- Requires applying concepts to a new scenario OR
- Requires justification beyond recalling facts

Adding "explain why" to a recall question DOES NOT count.

---

ANTI-CHEATING (ENFORCEMENT):

- You MUST NOT fake compliance by keeping MCQs and adding explanations
- You MUST CONVERT question types when required
- You MUST REMOVE excess formats if they violate MAX constraints

---

ANTI-COLLAPSE RULES (CRITICAL):

- You MUST NOT eliminate entire question types unless explicitly required
- If constraints require reduction (e.g., MCQs), REDUCE but DO NOT REMOVE completely
- Maintain a BALANCED distribution when constraints imply variety

---

DISTRIBUTION ENFORCEMENT:

- Respect BOTH minimum AND maximum percentages
- If a format has a MAX limit → ensure it does NOT exceed it
- If a format has a MIN requirement → ensure it is satisfied

---

HARD TRANSFORMATION LOGIC:

If constraints require:

- reduction → REMOVE excess content
- increase → ADD new content until threshold is met
- variety → REPLACE or MIX formats to satisfy distribution
- higher-order thinking → CONVERT questions (not just add explanation)
- rubric → ADD structured rubric (criteria + levels)
- feedback → ADD actionable improvement guidance PER SECTION or TASK

---

ANTI-CHEATING RULES:

- DO NOT satisfy constraints by adding filler text
- DO NOT append generic sections without fixing core issues
- DO NOT leave original low-quality questions unchanged

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

If content_type == "slides":
- bullet points only
- concise but meaningful

If content_type == "assessment":
- MUST upgrade question types
- MUST include applied/reasoning questions
- MUST enforce variety AND distribution
- MUST include rubrics where required

If content_type == "general":
- preserve format but improve depth

---

OUTPUT:

Return ONLY the final improved content.
NO explanations.
NO meta commentary.
"""
        
        messages = [{"role": "user", "content": prompt}]
        
        response, _, _ = self.llm.generate_response(messages)

        return response


    def validate(self, response, plan):
        prompt = f"""
Original plan = {plan}
Generated response = {response}
"""
        messages = [{"role": "user", "content": prompt}]

        validation_text, _, _ = self.llm.generate_response(messages)

        # Simple parsing (no fancy JSON assumptions)
        if "PASS" in validation_text:
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
            validation = self.validate(response, constraints)

            if validation["status"] == "PASS":
                return response


            response = self.generate_with_retry(
                content,
                validation["raw"],
                content_type
            )

        return response