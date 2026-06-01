# Sub-Step Decomposition + Prompt Hardening for 3B Model Output Quality

## Problem

3B GGUF models produce poor refactoring output due to overloaded single-call prompts.
Three main failure modes:

1. **Architect** produces incoherent mutation plans (hallucinates methods, forgets exception types, invents targets)
2. **Generator** ignores the plan (merges guard clauses, changes exception types, invents methods, adds comments)
3. **Judge** rejects valid refactorings without plan context (false REVISE verdicts)

**Root cause:** Dense multi-instruction prompts exceed 3B model reasoning capacity.
The Architect prompt has 7 simultaneous rules. The Generator has vague "follow the plan" instruction with no guardrails.
The Judge sees only the code pair with no knowledge of what the plan intended.

## Solution

Split overloaded single LLM calls into chained sub-steps with narrower scope.
Add few-shot examples, chain-of-thought directives, and anti-pattern guardrails to all prompts.
Add generator self-review before validator to catch obvious errors early.

### New Orchestration Flow

```
Phase 2: Planner
  Step 3:  Classifier — few-shot + CoT restructured
  Step 4:  Clear context
  Step 5a: Architect ANALYSIS (NEW) — "WHAT needs to change"
  Step 4b: Clear context
  Step 5c: Architect SYNTHESIS — "Produce mutation JSON" from analysis

Phase 3: Generator
  Step 6:  Coder — anti-patterns + few-shot
  Step 6b: Generator SELF-REVIEW (NEW) — checklist audit, max 2 retries
  Step 6c: Retry loop if self-review finds issues

Phase 4: Validator (unchanged)

Phase 5: Judge
  Auditor — plan context injection + plan fidelity check

Phase 6: Finalization (unchanged)
```

### Latency Impact

+3 inference calls per orchestration: +1 architect analysis, +1 self-review, +1 potential retry.
Each call ~0.5-1.5s on 4GB GPU with 3B models. Total added ~3-5s per orchestration.

### Context Budget

All within 6144 token limit. KV cache purged between sub-steps.
Few-shot examples add ~200-500 tokens per prompt.
Total system prompt growth <2000 tokens.

## Prompt Changes

All changes in `prompts.yaml`.

### `planner.classifier` — Replace

Add STEP directives (4 sequential reasoning steps) + 1 complete few-shot example (~300 tokens).

### `planner.architect_analysis` — New

4 output fields: `analysis_scratchpad`, `primary_targets`, `secondary_targets`, `new_structures_needed`, `must_preserve`. Forces the model to enumerate scope before designing mutations.

### `planner.architect` — Replace

Narrow from 7 rules to 5. References the analysis output directly. Removes CC rule (that's validator's job). Removes magic number rule (that's generator's job).

### `generator.coder` — Replace

Add ANTI-PATTERNS block with 8 explicit forbidden behaviors:
- Do NOT add methods not in plan
- Do NOT remove methods not in plan
- Do NOT change exception types
- Do NOT merge guard clauses
- Do NOT invent variables/parameters/classes
- Do NOT add comments
- Do NOT output outside `<code>` tags

### `generator.coder_review` — New

5-point quality checklist → PASS/FAIL verdict:
1. All mutations applied?
2. Extra additions?
3. Changed literals?
4. Syntax issues?
5. Verdict

### `judge.auditor` — Replace

Add plan context injection: `plan_summary` + `mutations_list` so the judge knows what changes were intentional. Add plan fidelity check to audit tasks. Relax cosmetic rejection criteria.

## Code Changes

### `OrchestrationState` new fields (`app/modules/orchestrator.py`)

```python
architect_analysis: Optional[Dict] = None
generator_self_review: Optional[Dict] = None
self_review_attempts: int = 0
```

### `_run_phase_2` — split into 3 sub-calls

1. **Classifier** (unchanged — just prompt restructured)
2. **Clear context**
3. **Architect Analysis** — single-results call using `planner.architect_analysis` prompt. Response parsed into `state.architect_analysis`
4. **Clear context**
5. **Architect Synthesis** — uses analysis output as input context alongside intent + code + instruction. Produces `state.active_plan`

### `_run_phase_3` — add self-review after code generation

After successful `<code>` extraction:
1. Run `generator.coder_review` prompt with plan + original + refactored
2. If FAIL and <2 review attempts: append review issues to coder prompt, retry
3. If PASS or exhausted: proceed to Phase 4
4. Reset `self_review_attempts` on pass

### `_run_phase_5` — inject plan context

Build compact `plan_summary` string from `state.intent_packet` + `state.active_plan`.
Inject into audit prompt before the code pair.
Format: `"Intent: {intent}. Target: {class}.{method}. Mutations planned: {actions}."`

## New Schemas (`app/utils/schemas.py`)

```python
class ArchitectAnalysisResponse(BaseModel):
    analysis_scratchpad: str
    primary_targets: List[str] = []
    secondary_targets: List[str] = []
    new_structures_needed: List[str] = []
    must_preserve: List[str] = []

class CodeReviewResponse(BaseModel):
    review_scratchpad: str
    all_mutations_applied: bool
    extra_additions: List[str] = []
    changed_literals: List[str] = []
    syntax_issues: List[str] = []
    verdict: Literal["PASS", "FAIL"]
```

## Tests (`tests/test_orchestrator_flow.py`)

| Test | Validates |
|------|-----------|
| `test_architect_split_flow` | Analysis call produces target list, synthesis produces valid plan |
| `test_generator_self_review_pass` | Clean code passes review, phase advances to 4 |
| `test_generator_self_review_fail_retry` | Failed review triggers coder retry with issues in error context |
| `test_generator_self_review_fail_exhausted` | 2 failed reviews, proceeds to Phase 4 anyway |
| `test_auditor_gets_plan_context` | Audit prompt contains plan summary + mutations list |

## Verification

1. Run existing 41 unit tests — confirm no regressions
2. Run `demo_scenario.txt` (FLATTEN_CONDITIONAL) 3-5 times, record Judge ACCEPT rate
3. Run additional test snippets for EXTRACT_METHOD, RENAME_SYMBOL, EXTRACT_CONSTANT
4. Compare success rate vs pre-change baseline if available

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| 3B can't handle analysis+ synthesis format | Analysis prompt uses 4 flat fields, no nested JSON |
| Self-review false-positives blocking valid code | Cap at 2 retries, proceed to Validator regardless |
| Plan context makes auditor "too lenient" | Include plan fidelity check — if plan was bad, Judge still catches logic drift |
| Added inference calls blow context | Each sub-step clears KV cache before next call |
| Token cost of few-shot examples | 1 example per prompt, ~200-500 tokens. Well within 6144 |

## Files Modified Summary

| File | Changes |
|------|---------|
| `prompts.yaml` | 4 prompts replaced, 2 new prompts added |
| `app/modules/orchestrator.py` | Split `_run_phase_2`, add self-review to `_run_phase_3`, inject context in `_run_phase_5`, 3 new state fields |
| `app/utils/schemas.py` | 2 new Pydantic models |
| `tests/test_orchestrator_flow.py` | 5 new test methods |
