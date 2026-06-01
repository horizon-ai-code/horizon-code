# Model Output Optimization — Master Roadmap

**Branch:** `optimization`  
**Created from:** `feat/substep-decomposition`  
**Date:** 2026-05-28  
**Source:** Full conversation history + analysis reports + robustness plan + substep-decomposition spec + additional issues + session summary

---

## Table of Contents

1. [Already Done (This Session)](#1-already-done-this-session)
2. [Phase 1 — Critical Prompt Fixes](#2-phase-1--critical-prompt-fixes)
3. [Phase 2 — Quality Prompt Fixes](#3-phase-2--quality-prompt-fixes)
4. [Phase 3 — Pipeline / Orchestrator Fixes](#4-phase-3--pipeline--orchestrator-fixes)
5. [Phase 4 — Validator / Infrastructure Hardening](#5-phase-4--validator--infrastructure-hardening)
6. [Phase 5 — Testing & Coverage](#6-phase-5--testing--coverage)
7. [Phase 6 — API / Misc Fixes](#7-phase-6--api--misc-fixes)
8. [Phase 7 — Experimental / Long-term](#8-phase-7--experimental--long-term)
9. [Expected Aggregate Improvement](#9-expected-aggregate-improvement)
10. [Appendix: Failure Mode Cross-Reference](#10-appendix-failure-mode-cross-reference)

---

## 1. Already Done (This Session)

| # | Item | Impact |
|---|------|--------|
| 1 | Fixed 5 test harness bugs (hallucination detector, scope checker, member lookup, plan executable, FLATTEN anti-pattern) | Revealed true model capability: Planner 0% → 73%, Scope 27% → 93% |
| 2 | Rerun isolated tests with accurate harness | Established trustworthy baseline |
| 3 | Committed everything to `feat/substep-decomposition` + created `optimization` branch | Ready for prompt engineering work |

---

## 2. Phase 1 — Critical Prompt Fixes

> **Effort:** ~1.5 hours  
> **Expected improvement:** Planner +20pp, Generator +18pp, Judge +7pp  
> **End-to-end:** ~64% → ~85%

| # | Fix | File | Effort | Expected Impact |
|---|-----|------|--------|-----------------|
| 1 | Add DECOMPOSE + SPLIT examples to classifier | `prompts.yaml` | 30 min | Planner: 73% → 93% (+20pp) |
| 2 | Add classless-code rule to classifier | `prompts.yaml` | 10 min | Scope accuracy: 93% → 100% |
| 3 | Reduce anti-patterns to 3, promote "no merge" | `prompts.yaml` | 20 min | Generator: 82% → 95% (+13pp) |
| 4 | Add logic preservation rule to generator | `prompts.yaml` | 15 min | Prevents FLATTEN inversion |
| 5 | Add explicit identity check to judge | `prompts.yaml` | 15 min | Judge: 88% → 95% (+7pp) |

### 2.1 [ ] Add DECOMPOSE + SPLIT examples + explicit extract/decompose disambiguation rule

**Source:** Analysis §8.1, Spec Task 2, Comprehensive Report §3.2  
**Root cause:** Classifier prompt has one FLATTEN example and no DECOMPOSE/SPLIT examples. The 3B model defaults "extract/decompose/split" → `EXTRACT_METHOD`.  
**Evidence:** 4/15 Planner cases misclassified:
- `decomp_closed_island` → EXTRACT_METHOD
- `decomp_regex_dp` → EXTRACT_METHOD
- `split_board_path` → EXTRACT_METHOD
- `split_unique_paths` → EXTRACT_METHOD

**Fix:** Add explicit STEP 3 to classifier prompt:
```
STEP 3: Distinguish CONTROL_FLOW from METHOD_MOVEMENT:
  - If the instruction says "decompose the condition" or "split the loop",
    classify as CONTROL_FLOW (DECOMPOSE_CONDITIONAL or SPLIT_LOOP),
    even if the word "extract" appears.
  - Never select REPLACE_LOOP_WITH_PIPELINE or SPLIT_LOOP unless the code
    has a for/while/do-while loop.
```

Add three examples (FLATTEN, DECOMPOSE, SPLIT) instead of one.

### 2.2 [ ] Add classless-code rule to classifier

**Source:** Analysis §1.2, §3.2, Spec Task 2  
**Root cause:** Bare methods (no class declaration) cause the model to invent class names like "A" or "Solution".  
**Evidence:** `flat_binary_search` → scope `A.search` (code has no class). `extract_set_zeroes` → invented class.  
**Fix:** Add STEP 4:
```
STEP 4: If the code has no class declaration (bare method),
  set scope_anchor.class to an empty string.
```

### 2.3 [ ] Reduce generator anti-patterns from 8 → 3, promote "NEVER merge guard clauses" to #1

**Source:** Analysis §8.2, §4.3, Spec Task 4  
**Root cause:** 8 anti-pattern rules — 3B model drops later rules. Rule #4 (no merged guard clauses) is ignored.  
**Evidence:**
- `gen_flatten_orderprocessor`: merged "Order has no items." + "Order cannot be null." into "Order has no items or is null."
- `gen_flatten_simple_ifs`: merged `x==null` and `y==null` into `x==null || y==null`

**Fix:** Reduce to 3 rules with "NEVER merge guard clauses" as #1:
```
1. NEVER merge multiple guard clauses or validation checks into one
   combined condition with || or &&. Each original throw statement must
   become its own separate if-check at the top level, even if the result is longer.
2. NEVER change exception types (IllegalArgumentException stays as is, etc.)
3. NEVER add any method not listed in the plan's ast_mutations
```

### 2.4 [ ] Add explicit LOGIC PRESERVATION rule to generator coder prompt

**Source:** Analysis §4.3, §8.2, Comprehensive Report §4.3  
**Root cause:** Generator inverts conditional logic during FLATTEN to be "concise."  
**Evidence:** `gen_flatten_orderprocessor` — premium users get NO discount when total > 1000. Original: `if (premium) discount(0.15) else discount(0.05)`. Generated: `if (!premium) discount(0.05)` with no premium branch.

**Fix:** Add Rule 4:
```
4. LOGIC PRESERVATION: For FLATTEN_CONDITIONAL, each original if-condition
   must map to an equivalent inverted condition. Do NOT change which branch
   executes for a given input. Premium users must still get premium discounts.
```

### 2.5 [ ] Add explicit identity-check rule + concrete example requirement to judge auditor

**Source:** Analysis §8.3, §5.3, Comprehensive Report §5.3  
**Root cause:** Judge never checks PLAN FIDELITY on identical code. Scratchpad only contains VARIABLE TRACE + LOGIC CHECK.  
**Evidence:** `revise_decompose_noop` — 5/5 runs ACCEPT on identical code. All scratchpads: "conditional paths are identical."

**Fix:** Reduce from 5 audit tasks to 3. Move identity check to position #1:
```
STEP 1 — PLAN EXECUTION CHECK (MANDATORY)
  Compare planned mutations to actual refactored code.
  - If refactored code is character-for-character identical to original
    but plan lists mutations, verdict MUST be REVISE.
  - If planned ADD_METHOD / ADD_FIELD / ADD_CONSTANT items are missing,
    verdict MUST be REVISE.

STEP 2 — SIGNATURE CHECK (MANDATORY)
  Compare method return types, names, parameter lists.
  Flag any unplanned signature changes.

STEP 3 — LOGIC CHECK (MANDATORY)
  For the same inputs, do conditional paths produce same outputs?
  Trace at least one concrete example through both versions.
```

Remove VARIABLE TRACE (low signal, high token cost).

---

## 3. Phase 2 — Quality Prompt Fixes

> **Effort:** ~1 hour  
> **Expected improvement:** +10pp Planner completeness

| # | Fix | File | Effort | Expected Impact |
|---|-----|------|--------|-----------------|
| 6 | Add "only explicit" constraint to analysis | `prompts.yaml` | 20 min | Reduces hallucinations |
| 7 | Add "scan ALL occurrences" to analysis | `prompts.yaml` | 15 min | Catches cross-references |
| 8 | Add mutation count cap to synthesis | `prompts.yaml` | 10 min | Prevents explosion |
| 9 | Add analysis→synthesis coherence rule | `prompts.yaml` | 15 min | Improves plan completeness |
| 10 | Remove VARIABLE TRACE from judge | `prompts.yaml` | 10 min | Frees attention budget |

### 3.1 [ ] Add "only explicit" + "scan ALL occurrences" to architect_analysis

**Source:** Analysis §9.2, §3.3, Comprehensive Report §3.3  
**Root cause:** No constraint on `new_structures_needed` → model hallucinates helpers. No cross-reference scan → misses secondary targets.  
**Evidence:**
- `flat_demo_orderprocessor`: analysis invented `guardClauseHelper`, `INVALID_ORDER_MESSAGE`
- `const_circle_pi`: analysis found BOTH methods but synthesis only produced ADD_CONSTANT

**Fix:**
```
- Scan ALL code for ALL occurrences of the target pattern (magic numbers,
  repeated expressions, fields to rename). List every affected location.
- Do NOT list helper methods, constants, or fields in new_structures_needed
  unless the instruction explicitly names them or asks for them.
```

### 3.2 [ ] Add mutation count cap, no-template-bleed, target-format rules to architect synthesis

**Source:** Analysis §9.3, §3.3, §1.6, Comprehensive Report §3.3  
**Root cause:**
- No mutation cap → 14 mutations in `extract_set_zeroes`
- Synthesis ignores analysis context → incomplete plans
- Template text bleed → FLATTEN body_abstract copied into CONSTANT plan
- Target format unconstrained → full signatures in target field

**Evidence:**
- `const_circle_pi`: synthesis `body_abstract` = "Invert all conditionals..." (FLATTEN template text in CONSTANT plan)
- `decomp_regex_dp`: `target` = "boolean matchesZeroOrMore(...)" (full signature, not identifier)
- `extract_set_zeroes`: 14 mutations (explosion)

**Fix:** Add rules to synthesis prompt:
```
1. Map each primary_target to exactly one MODIFY_METHOD mutation
2. Map each new_structure_needed item to exactly one ADD_METHOD/ADD_FIELD/ADD_CONSTANT
3. Map each secondary_target to one mutation ONLY if it must change
4. Use parameter types from analysis new_structures_needed descriptions.
   Do NOT copy parameters from the original method being refactored.
5. CONCISENESS: Maximum 5 ast_mutations. Consolidate related changes.
6. If code has no class declaration, set target_class to empty string.
7. The mutation target field must be ONLY the identifier name
   (e.g., "methodName", not "boolean methodName(...)")
8. The body_abstract must describe the ACTUAL logic for THIS intent,
   not generic template text.
```

### 3.3 [ ] Remove VARIABLE TRACE from judge auditor

**Source:** Analysis §8.3, §9.5, Comprehensive Report §5.3  
**Root cause:** VARIABLE TRACE is low-signal (mapping `age`→`age` is trivial) but consumes attention budget. The 3B model can only process 2-3 of 5 audit tasks.  
**Evidence:** `revise_decompose_noop` scratchpads: 171-453 chars, only variable_trace + logic_comparison. No PLAN FIDELITY, no SIGNATURE CHECK.

**Fix:** Remove VARIABLE TRACE from audit tasks. Keep PLAN EXECUTION CHECK, SIGNATURE CHECK, LOGIC CHECK.

---

## 4. Phase 3 — Pipeline / Orchestrator Fixes

| # | Fix | File | Effort | Expected Impact |
|---|-----|------|--------|-----------------|
| 11 | Fix syntax healing loop | `orchestrator.py` | 1 hour | Makes retries effective |
| 12 | Cap cumulative_feedback | `orchestrator.py` | 30 min | Prevents context overflow |
| 13 | Add pre-flight plan validation | `orchestrator.py` | 2 hours | Catches bad plans early |
| 14 | Add identity gate before Judge | `orchestrator.py` | 30 min | Prevents no-op ACCEPT |
| 15 | Fix strategy_iter multi-increment | `orchestrator.py` | 30 min | Prevents premature ABORT |
| 16 | Add generator semantic validation | `orchestrator.py` | 1 hour | Catches logic inversions |

### 4.1 [ ] Fix syntax healing loop

**Source:** Robustness Issue 1, Analysis §1.8  
**Root cause:** On syntax fail, orchestrator re-runs Phase 3 with the SAME prompt (`base_code` + `active_plan`). Generator has no idea what went wrong. Also includes BOTH `Base Code` (original) and `Current Broken Code` — conflicting signals.  
**Evidence:** Orchestrator lines 305-365 — broken code stored but same prompt reused.

**Fix:**
```python
# On syntax retry:
# 1. Do NOT include Base Code. Only include:
#    - Modification Plan
#    - CURRENT BROKEN CODE
#    - PREVIOUS SYNTAX ERROR
# 2. Increase temperature to 0.3 on retry
# 3. If retry fails 3 times, simplify plan before outer loop
```

### 4.2 [ ] Cap cumulative_feedback to last 3 entries + token-aware truncation

**Source:** Robustness Issue 2, AGENTS.md  
**Root cause:** `cumulative_feedback` grows unbounded. After 3 outer loops, 10+ detailed error objects. 6144-token context overflows silently.  
**Fix:**
```python
# Ring buffer (primary)
state.cumulative_feedback.append(new_entry)
if len(state.cumulative_feedback) > 3:
    state.cumulative_feedback.pop(0)

# Token-aware truncation (belt-and-suspenders)
def _truncate_feedback(feedback, max_chars=2000):
    total = sum(len(json.dumps(f)) for f in feedback)
    while total > max_chars and feedback:
        removed = feedback.pop(0)
        total -= len(json.dumps(removed))
    return feedback
```

### 4.3 [ ] Add pre-flight plan validation between Phase 2 and Phase 3

**Source:** Analysis §3.2, §3.3  
**Root cause:** Hallucinated targets, invented class names, mutation explosion reach Generator before being caught.  
**Fix:**
```python
# Before sending plan to Generator:
# 1. Verify every ast_mutation.target is valid Java identifier
#    (regex [A-Za-z_$][A-Za-z0-9_$]*)
# 2. For MODIFY_METHOD/RENAME_SYMBOL: verify target exists in original AST
# 3. For ADD_METHOD/ADD_FIELD/ADD_CONSTANT: verify target does NOT exist
#    in original AST (prevents no-op additions)
# 4. Verify target_class exists in original code or is empty string
# 5. Cap mutation count at 5
```

### 4.4 [ ] Add identity gate before Judge

**Source:** Analysis §6.3, §8.3  
**Root cause:** Most dangerous failure mode — system reports SUCCESS but nothing changed.  
**Evidence:** `revise_decompose_noop` — Judge ACCEPTs identical code 5/5 times.

**Fix:**
```python
if state.working_code.strip() == state.base_code.strip():
    if state.active_plan and state.active_plan.get("ast_mutations"):
        # Short-circuit to REVISE without calling Judge
        state.add_feedback({
            "failure_tier": FailureTier.TIER_3_JUDGE,
            "error": "Plan was not executed: code unchanged."
        })
        state.strategy_iter += 1
        state.current_phase = 2
        return
```

### 4.5 [ ] Fix strategy_iter incrementing multiple times per outer loop

**Source:** Additional Issue 16  
**Root cause:** Phase 3, 4, 5 all increment `strategy_iter` independently. A single outer loop pass can increment it 2-3 times, causing premature ABORT_STRATEGY.  
**Fix:** Use `strategy_iter_incremented` flag (already exists in state) consistently across all phases. Only increment once per outer loop.

### 4.6 [ ] Add generator output semantic validation after syntax check

**Source:** Analysis §3.2, §4.3  
**Root cause:** Syntax check passes but semantic correctness is not verified before Judge.  
**Fix:** After syntax passes, before structural checks:
```python
# For FLATTEN intent:
#   Verify every original throw new XxxException(...) has matching throw
#   in refactored code with same type and message.
# For EXTRACT_METHOD:
#   Verify new method is actually called from original method (not orphaned).
# For RENAME_SYMBOL:
#   Verify old name is absent in output.
```

---

## 5. Phase 4 — Validator / Infrastructure Hardening

| # | Fix | File | Effort | Expected Impact |
|---|-----|------|--------|-----------------|
| 17 | Add semantic smoke test | `validator.py` | 2 hours | Catches "Do something;" |
| 18 | Add throw-message comparison to FLATTEN check | `validator.py` | 1 hour | Catches merged guards + inversion |
| 19 | Fix boundary check (structural signature) | `validator.py` | 2 hours | Stops noise flags |
| 20 | Add per-intent CC rules | `orchestrator.py` | 1 hour | Fixes EXTRACT_METHOD always failing |
| 21 | Add get_method_complexity | `validator.py` | 1 hour | Enables source-only CC |
| 22 | Fix ResponseParser on long outputs | `response_parser.py` | 30 min | Captures good reasoning |
| 23 | Fix JSON repair second attempt | `response_parser.py` | 15 min | Removes overhead |
| 24 | Fix token counting | `agent_service.py` | 15 min | Accurate context mgmt |
| 25 | Strengthen syntax gate | `validator.py` | 30 min | Earlier nonsense rejection |

### 5.1 [ ] Add semantic smoke test

**Source:** Analysis §1.5, §4.4  
**Root cause:** javalang parses `Do something;` as `LocalVariableDeclaration` with type `Do` and variable `something`. Validator returns `syntax_valid=True`.  
**Evidence:** `bad_hallucinated_add` — generated `Do something;` passes all validation gates.

**Fix:**
```python
# After check_syntax passes:
# Compile list of known Java types (java.lang.*, primitives).
# Flag unknown capitalized identifiers used as types in LocalVariableDeclaration.
# Alternatively: flag single-statement method bodies where the "type" is not
# a known Java class/primitive.
```

### 5.2 [ ] Add throw-message comparison to verify_flatten_conditional

**Source:** Analysis §1.4, §1.9, §8.2  
**Root cause:** Intent math only checks AST nesting depth. Generator can flatten while inverting every condition and still pass.  
**Evidence:** `gen_flatten_orderprocessor` — inverted discount logic but `refac_depth < orig_depth` → would pass.

**Fix:**
```python
# In verify_flatten_conditional:
# 1. Extract all throw new XxxException("...") from original and refactored
# 2. Count distinct throw statements
# 3. Compare exception types + messages
# 4. If refactored has fewer distinct throws, or messages were merged/altered,
#    flag as failure
```

### 5.3 [ ] Fix boundary check — structural signature instead of SHA-256

**Source:** Robustness Issue 3  
**Root cause:** SHA-256 of full AST serialization. Any difference (whitespace, comments, imports) on non-target method triggers violation.  
**Fix:**
```python
# For each non-target method AST node, compute signature from:
#   1. Node-type skeleton (tree shape: IfStatement→Block→ReturnStatement)
#   2. Operator tokens (set of binary/unary operators: >, &&, +)
#   3. Branching paths (count of conditional branches and nesting depth)
#   4. Method invocation names (set of called method names, not arguments)
#   5. String/error message literals (exact text)
# Excluded: variable names, whitespace, comments, imports, annotations, numeric literals
```

### 5.4 [ ] Add per-intent CC rules

**Source:** Robustness Issue 4  
**Root cause:** `get_complexity()` always checks `max(CC_refactored) ≤ max(CC_original)`. EXTRACT_METHOD adds a method → total CC increases → always fails.  
**Fix:**

| Intent | CC Rule |
|--------|---------|
| FLATTEN_CONDITIONAL | `max(CC_refactored) ≤ max(CC_original)` |
| DECOMPOSE_CONDITIONAL | `max(CC_refactored) ≤ max(CC_original)` |
| CONSOLIDATE_CONDITIONAL | `max(CC_refactored) ≤ max(CC_original)` |
| REMOVE_CONTROL_FLAG | `max(CC_refactored) ≤ max(CC_original)` |
| REPLACE_LOOP_WITH_PIPELINE | `max(CC_refactored) ≤ max(CC_original)` |
| SPLIT_LOOP | `max(CC_refactored) ≤ max(CC_original) + 1` |
| **EXTRACT_METHOD** | **`CC_source_refactored ≤ CC_source_original`** (source method only, ignore new helper) |
| **INLINE_METHOD** | **skipped** (inlining increases caller CC; Judge handles semantic check) |
| EXTRACT_VARIABLE | `max(CC_refactored) ≤ max(CC_original)` |
| INLINE_VARIABLE | `max(CC_refactored) ≤ max(CC_original)` |
| EXTRACT_CONSTANT | `max(CC_refactored) ≤ max(CC_original)` |
| RENAME_SYMBOL | `max(CC_refactored) ≤ max(CC_original)` |

### 5.5 [ ] Add get_method_complexity(code, method_name)

**Source:** Robustness Issue 4  
**Purpose:** Enable EXTRACT_METHOD source-only CC comparison.  
**Implementation:**
```python
def get_method_complexity(code: str, method_name: str) -> int:
    # Parse code with javalang
    # Find MethodDeclaration matching method_name
    # Extract that method's source text
    # Run lizard on extracted text
    # Return CC (or 0 if not found)
```

### 5.6 [ ] Fix ResponseParser on long excellent outputs

**Source:** Analysis §1.7  
**Root cause:** `extract_json_text` fails on 1500+ char scratchpads. Judge run 3 of `revise_extract_constant_broken_sig` had excellent concrete reasoning but returned PARSE_ERROR.  
**Fix:** Improve `extract_json_text` to handle nested JSON, escaped quotes, and long content without truncation.

### 5.7 [ ] Fix JSON repair running as second attempt on every valid parse

**Source:** Additional Issue 5  
**Root cause:** Try/except hit on every valid parse — unnecessary overhead.  
**Fix:** Only run JSON repair when `json.loads()` actually fails, not as a second attempt on success.

### 5.8 [ ] Fix token counting

**Source:** Additional Issue 6  
**Root cause:** `len(chunks)` counts streaming chunks, not actual tokens. Inaccurate context management.  
**Fix:** Use actual token counting (e.g., via tiktoken or model tokenizer) instead of chunk count.

### 5.9 [ ] Strengthen weak Java syntax gate

**Source:** Additional Issue 8  
**Root cause:** Syntax gate only checks for `{` or `;`. Too permissive.  
**Fix:** Use javalang parse attempt as the gate, or at minimum check for balanced braces and valid Java keywords.

---

## 6. Phase 5 — Testing & Coverage

| # | Test | Target | File |
|---|------|--------|------|
| 26 | `classifier_decompose_vs_extract_boundary` | DECOMPOSE not misclassified as EXTRACT | `test_planner_isolated.py` |
| 27 | `classifier_split_vs_extract_boundary` | SPLIT not misclassified as EXTRACT | `test_planner_isolated.py` |
| 28 | `scope_bare_method_no_class` | Classless code → empty class string | `test_planner_isolated.py` |
| 29 | `analysis_cross_reference_constant` | Both methods found for magic number | `test_planner_isolated.py` |
| 30 | `analysis_no_hallucination` | No invented helpers for FLATTEN | `test_planner_isolated.py` |
| 31 | `synthesis_no_template_bleed` | body_abstract matches intent | `test_planner_isolated.py` |
| 32 | `generator_logic_preservation_flatten` | Premium discount preserved | `test_generator_isolated.py` |
| 33 | `generator_no_merge_guard_clauses` | Three separate throws, no `\|\|` | `test_generator_isolated.py` |
| 34 | `judge_identity_noop` | Identical code + plan → REVISE | `test_judge_isolated.py` |
| 35 | `judge_signature_priority` | int→void return type → REVISE | `test_judge_isolated.py` |
| 36 | `validator_semantic_smoke` | `Do something;` flagged invalid | `test_validator_new.py` |
| 37 | `orchestrator_syntax_healing` | Pre-flight catches hallucinated target | `test_orchestrator_flow.py` |
| 38 | `test_syntax_heal_inner_loop` | Error fed back, second attempt valid | `test_orchestrator_flow.py` |
| 39 | `test_cumulative_feedback_capped` | 5 entries → last 3 retained | `test_orchestrator_flow.py` |
| 40 | `test_boundary_ignores_whitespace` | Formatting changes pass | `test_validator_new.py` |
| 41 | `test_extract_method_cc_exception` | Source CC decreases, helper ignored | `test_validator_new.py` |
| 42 | `test_split_loop_cc_exception` | Total CC +1 passes | `test_validator_new.py` |
| 43 | Add integration tests (not just mocked units) | Additional Issue 14 | `tests/test_integration.py` |
| 44 | Update `test_orchestrator_flow` for new sub-step sequences | Analysis + Spec | `test_orchestrator_flow.py` |

---

## 7. Phase 6 — API / Misc Fixes

| # | Fix | File | Source |
|---|-----|------|--------|
| 45 | Add input validation on `code` and `user_instruction` | `main.py` or `schemas.py` | Additional Issue 10 |
| 46 | Send errors to frontend via WebSocket | `connection_manager.py` | Additional Issue 11 |
| 47 | Add structured syntax-error formatting | `orchestrator.py` | Additional Issue 12 |
| 48 | Fix DB migration column check on every load | `context_manager.py` | Additional Issue 15 |

---

## 8. Phase 7 — Experimental / Long-term

| # | Item | Rationale | Status |
|---|------|-----------|--------|
| 49 | Evaluate larger Generator model (7B+ instead of 3B) | Current 3B inverts FLATTEN logic; 7B+ may preserve semantics | Not started |
| 50 | Consider dropping Generator self-review entirely | Already tried — 3B returns false PASS on every case | Done (removed in fe32936) |

---

## 9. Expected Aggregate Improvement

| Metric | Current True Capability | After Phase 1+2 Prompts | After Phase 3+4 Pipeline+Validator |
|--------|------------------------|------------------------|-----------------------------------|
| Planner PASS | 73% | ~93% | ~93% |
| Generator PASS | 82% | ~95% | ~95% |
| Judge correct | 88% | ~95% | ~95% |
| End-to-End (estimated) | ~64% | ~85% | ~90% |

---

## 10. Appendix: Failure Mode Cross-Reference

| Failure Mode | Evidence | Root Cause | Fix Location |
|-------------|----------|------------|--------------|
| DECOMPOSE misclassified as EXTRACT_METHOD | 4/4 cases: "Category is METHOD_MOVEMENT" | Prompt has no DECOMPOSE/SPLIT examples | Phase 1 #1 |
| FLATTEN logic inversion | Premium users lose discount | Model drops anti-pattern #4 (no merge) | Phase 1 #3, #4 |
| No-op blind spot | 5/5 ACCEPT on identical code | Judge never checks PLAN FIDELITY | Phase 1 #5 |
| Hallucinated helpers in analysis | `guardClauseHelper`, `INVALID_ORDER_MESSAGE` | No "only explicit" constraint | Phase 2 #6 |
| Template text bleed | FLATTEN body_abstract in CONSTANT plan | No template-text isolation rule | Phase 2 #7 |
| Incomplete synthesis | Missing MODIFY_METHOD for const extraction | Synthesis ignores analysis context | Phase 2 #8 |
| Syntax healing ineffective | Same prompt on retry | Generator gets conflicting signals | Phase 3 #11 |
| Context overflow | Unbounded cumulative_feedback | No cap or truncation | Phase 3 #12 |
| Bad plans reach Generator | Hallucinated targets, invented classes | No pre-flight validation | Phase 3 #13 |
| False success on no-op | System reports success, nothing changed | No identity gate | Phase 3 #14 |
| `Do something;` passes syntax | javalang parses nonsense as valid | No semantic smoke test | Phase 4 #17 |
| Intent math too weak | Depth check only, no semantic comparison | No throw-message comparison | Phase 4 #18 |
| Boundary check noise | SHA-256 full AST, whitespace flags violation | Structural-only comparison needed | Phase 4 #19 |
| EXTRACT_METHOD always fails CC | Total CC increases with new helper | No per-intent CC rules | Phase 4 #20 |
| Good reasoning lost to parser | 1500+ char scratchpad → PARSE_ERROR | ResponseParser fails on long output | Phase 4 #22 |

---

*Generated from comprehensive analysis of isolated model tests, raw JSON inspection, test harness source code, orchestrator pipeline, and validator logic.*
