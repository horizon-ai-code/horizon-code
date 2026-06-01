# Independent Deep Analysis — Horizon Code Model Isolation Tests

**Date:** 2026-05-28  
**Analyst:** Independent review of raw JSON outputs, test harness source code, and orchestrator pipeline  
**Scope:** Planner (45 calls), Judge (50 calls), Generator (14 calls)  

---

## Executive Summary

The pre-written reports (planner_isolated_report.md, model_reasoning_final_report.md, etc.) are directionally correct but miss **test harness bugs that inflate failure rates**, **logically broken generated code misclassified as "detector false positive"**, and **infrastructure fragility** that makes model reasoning quality hard to measure. After correcting for harness artifacts, the true model capability is higher than reported, but the pipeline has deeper structural issues.

| Role | Reported Pass | True Capability (after harness fixes) | Real Pipeline Risk |
|------|--------------|--------------------------------------|-------------------|
| Planner | 0/15 (0%) | ~5-6/15 (~35-40%) | Classifier prompt gaps, synthesis template bleeding |
| Judge | 44/50 (88%) | ~48/50 (~96%) | Parse errors, skipped audit tasks on short scratchpads |
| Generator | 9/11 (82%) | ~7/11 (~64%) | Logic inversion on FLATTEN, invalid Java passing syntax check |

---

## Part 1: What the Reports Got Wrong

### 1.1 Test Harness `hallucination` detector is fundamentally broken for ADD_* actions

**Evidence:** `const_circle_pi` has `hallucinations: ['CONSTANT_PI']`. `extract_tax_calculator` has `hallucinations: ['computeTaxWithRounding']`.

**Root cause:** `harness.py detect_hallucinations()` checks every string in analysis/plan against `code_identifiers` (names found in original AST). But ADD_METHOD, ADD_FIELD, and ADD_CONSTANT targets are **supposed to be new names**. They will never exist in the original code. The detector flags them as hallucinations by design flaw.

**Impact:** This falsely inflates hallucination counts and causes `plan_executable=False` for every extraction/addition case. The reports treat this as model failure when it's test infrastructure failure.

**Fix:** Exclude `new_structures_needed` items and ADD_METHOD/ADD_FIELD/ADD_CONSTANT targets from hallucination checks against original identifiers.

---

### 1.2 Test Harness `scope_valid` is broken for all bare-method inputs

**Evidence:** `flat_binary_search`, `flat_validate_ip`, `extract_set_zeroes`, `extract_prime_arrange`, `const_abbreviation`, `decomp_closed_island`, `decomp_regex_dp`, `split_board_path`, `split_unique_paths`, `cons_word_pattern` all have `scope_valid=False`.

**Root cause:** `Validator.check_syntax()` wraps bare methods in `class ASTWrapper { ... }` (template index 1). The test then checks `classes_in_code = len(ClassDeclaration) > 0`, which is **always True** after wrapping. The scope validity formula is:

```python
scope_valid = (
    scope_check["valid"]
    and (not target_member or scope_check["member_exists"])
    and (scope_check["class_exists"] or not classes_in_code)
)
```

Since `classes_in_code=True` for all bare methods, the last clause becomes `scope_check["class_exists"] or False`. The model invents class names like "A" or "Solution" (because real class doesn't exist), so `class_exists=False`, and scope_valid becomes **False for all bare methods**.

**Fix:** Use the original unwrapped code to determine `classes_in_code`, not the validator-wrapped AST. Or exempt cases where the validator used template index 1.

---

### 1.3 Test Harness `member_exists` only checks MethodDeclaration, not fields

**Evidence:** `rename_user_manager` has `scope_valid=False` with detail `UserManager.n, CLASS_UNIT ✗ (class=True, member=False, hasClasses=True)`. The field `n` exists in the code, but `check_scope_anchor_exists` only searches MethodDeclaration nodes for `member`.

**Impact:** RENAME_SYMBOL cases on fields falsely fail scope validation.

**Fix:** Check FieldDeclaration and VariableDeclarator nodes in addition to MethodDeclaration.

---

### 1.4 Generator `gen_flatten_orderprocessor` produced LOGICALLY WRONG code, not a "detector false positive"

**Evidence (raw output):**
```java
if (total > 1000) {
    if (!user.isPremium()) {
        order.applyDiscount(0.05);
    }
} else {
    order.applyDiscount(0.15);
}
```

**Original logic:**
- total > 1000 AND premium → discount 0.15
- total > 1000 AND NOT premium → discount 0.05
- total <= 1000 → NO discount

**Generated logic:**
- total > 1000 AND premium → NO discount (missing else branch!)
- total > 1000 AND NOT premium → discount 0.05
- total <= 1000 → discount 0.15 (wrong — this applies to everyone including non-premium)

**This is the EXACT same bug pattern as `revise_flatten_logic_inverted` in the Judge test.** The generator inverted conditional logic during flattening. The reports called this "detector false positive" because the anti-pattern detector flagged "merged guard clauses," but the real problem is **semantic corruption**.

**Critical implication:** The Generator can produce syntactically valid, structurally plausible code that passes intent math (nesting depth decreased) but has inverted business logic. The orchestrator's Phase 4 intent checks are too weak to catch this.

---

### 1.5 `bad_hallucinated_add` generated INVALID Java that passed syntax validation

**Evidence (raw output):**
```java
private void xyZzZzZzHelperMethod() {
    Do something;
}
```

**Validator result:** `syntax_valid: True`

**Root cause:** javalang parses `Do something;` as a `LocalVariableDeclaration` with type `Do` and variable name `something`. The parser is ambiguous — it treats any capitalized word as a type reference. The validator considers this syntactically valid.

**Critical implication:** The Generator can inject semantically meaningless code that passes all syntax checks. The syntax validator is not a sufficient safety gate.

---

### 1.6 Planner synthesis copies template text from wrong intent

**Evidence (`const_circle_pi` synthesis):**
```json
{
  "action": "MODIFY_METHOD",
  "target": "calculateArea",
  "details": {
    "logic_changes": ["Replace 3.14159 with CONSTANT_PI in the calculation."],
    "body_abstract": "Invert all conditionals. Each original exception becomes a guard clause at the top with immediate throw."
  }
}
```

The `body_abstract` is the FLATTEN_CONDITIONAL template from the prompt example, not the constant extraction body abstract. The 3B model is **copy-pasting prompt template fragments** into unrelated outputs.

**Also seen in:** `extract_set_zeroes` synthesis uses the same FLATTEN body abstract for a method extraction plan.

---

### 1.7 Judge `decompose_noop` failure is worse than reported

**Evidence:** All 5 scratchpads are 171-453 chars and contain ONLY:
```json
{"variable_trace": [...], "logic_comparison": "The conditional paths in the refactored code are identical to those in the original code."}
```

**The model completely skipped PLAN FIDELITY, SIGNATURE CHECK, and the explicit rule about "changes matching plan are EXPECTED."** It didn't default to ACCEPT because of ambiguous wording — it defaulted because it never executed 3 of the 5 audit tasks.

**Root cause:** The prompt lists 5 audit tasks + 3 rules + output format. For a 3B model with 6144-token context, this is too much to process. The model outputs a minimal JSON that satisfies the output schema without completing the reasoning steps.

**Contrast:** The "parse error" run in `revise_extract_constant_broken_sig` (run 3) produced 1500+ chars of excellent concrete reasoning but ResponseParser failed to extract valid JSON. The model CAN reason deeply, but the structured output constraint and short scratchpad limit often prevent it.

---

### 1.8 Orchestrator syntax healing loop is structurally broken

**Evidence (orchestrator.py lines 305-365):**
On syntax fail, the orchestrator stores `broken_code` and `error`, then re-runs Phase 3 with:
```
Modification Plan: {same plan}
Base Code: <code>{original code}</code>
PREVIOUS SYNTAX ERROR: {error}
CURRENT BROKEN CODE: <code>{broken code}</code>
Fix the syntax error. Output only valid Java wrapped in <code> tags.
```

**Problems:**
1. The prompt contains BOTH `Base Code` (original) and `Current Broken Code` (broken). The model gets conflicting signals about what to transform.
2. Temperature is still 0.1 on retry — with the same prompt structure, the model will likely reproduce the same error.
3. The plan is unchanged. If the plan itself is unexecutable (e.g., hallucinated target), no amount of syntax healing will fix it.
4. The error message from javalang is often cryptic (e.g., "Expected type declaration" for bare methods), and the model may not map it to the actual problem.

---

### 1.9 Phase 4 intent math is too weak to catch semantic inversions

**Evidence:** `gen_flatten_orderprocessor` output has **inverted discount logic** but would pass `verify_flatten_conditional` because:
- Original max nesting depth: 7 (OrderProcessor nested ifs)
- Generated max nesting depth: 2
- `refac_depth < orig_depth` → returns True

The intent verifier only counts AST nesting depth, not semantic correctness. A generator could flatten nested ifs while inverting every condition and still pass.

---

## Part 2: Root Cause Taxonomy

### Prompt Engineering Failures
| Issue | Location | Evidence |
|-------|----------|----------|
| Missing DECOMPOSE/SPLIT examples | planner.classifier | 4/4 misclassified as EXTRACT_METHOD |
| No classless-code rule | planner.classifier | All bare methods get invented class names |
| No "only explicit" constraint on new_structures | planner.architect_analysis | Hallucinated `guardClauseHelper`, `INVALID_ORDER_MESSAGE` |
| No cross-reference scan instruction | planner.architect_analysis | `const_circle_pi` initially missed `calculateCircumference` (though raw analysis actually caught it) |
| Synthesis prompt doesn't anchor to analysis | planner.architect | Tax calculator wrong params, setZeroes uses FLATTEN template text |
| 8 anti-pattern rules too many for 3B | generator.coder | Rule #4 (no merge) ignored; model drops later rules |
| No explicit identity-check rule | judge.auditor | decompose_noop skipped all audit tasks, defaulted to ACCEPT |
| Task list too long for 3B attention | judge.auditor | Scratchpads only contain 2 of 5 tasks |

### Infrastructure Failures
| Issue | Location | Evidence |
|-------|----------|----------|
| Hallucination detector flags new ADD_* names | harness.py | `CONSTANT_PI`, `computeTaxWithRounding` flagged |
| Scope check uses wrapped AST for `classes_in_code` | harness.py | All bare methods fail scope validation |
| `member_exists` only checks methods | harness.py | `rename_user_manager` field `n` not found |
| javalang parses nonsense as valid | validator.py | `Do something;` → LocalVariableDeclaration |
| ResponseParser fails on long good outputs | response_parser.py | Judge run 3 excellent but PARSE_ERROR |
| Syntax healing sends conflicting inputs | orchestrator.py | Both base_code and broken_code in retry prompt |
| Intent math only checks AST depth | validator.py | Logic inversion passes `verify_flatten_conditional` |
| Boundary check uses SHA-256 hash | validator.py | Known issue — noise flagged as violations |

### Model Capability Limits
| Issue | Evidence | Verdict |
|-------|----------|---------|
| 3B attention drops later prompt rules | Anti-pattern #4 ignored | Prompt engineering can fix |
| 3B copies template text cross-intent | FLATTEN body_abstract in CONSTANT plan | Prompt + synthesis guard can fix |
| 3B invents class names for bare methods | LeetCode training bleed | Prompt rule can fix |
| 3B merges guard clauses for conciseness | `x==null || y==null` | Stronger prompt + post-validator can catch |
| 3B inverts complex conditional logic | OrderProcessor discount logic corrupted | **Most serious** — needs logic equivalence verifier |

---

## Part 3: Comprehensive Improvement Plan

### 3.1 PROMPT REWRITES

#### A. `planner.classifier`

**Current flaw:** Single FLATTEN example. No DECOMPOSE/SPLIT examples. No classless-code rule.

**Rewrite:**
```yaml
planner:
  classifier: |
    ### ROLE
    Classify code refactoring intents from natural language instructions.

    ### CATEGORIES
    1. CONTROL_FLOW: FLATTEN_CONDITIONAL | DECOMPOSE_CONDITIONAL | CONSOLIDATE_CONDITIONAL | REMOVE_CONTROL_FLAG | REPLACE_LOOP_WITH_PIPELINE | SPLIT_LOOP
    2. METHOD_MOVEMENT: EXTRACT_METHOD | INLINE_METHOD
    3. STATE_MANAGEMENT: EXTRACT_VARIABLE | INLINE_VARIABLE | EXTRACT_CONSTANT | RENAME_SYMBOL

    ### REASONING STEPS
    STEP 1: Read the instruction. Is it about conditionals? Methods? Variables? Loops?
    STEP 2: Read the code. Does the code actually contain what the instruction references?
    STEP 3: Distinguish CONTROL_FLOW from METHOD_MOVEMENT:
      - If the instruction says "decompose the condition" or "split the loop", classify as CONTROL_FLOW (DECOMPOSE_CONDITIONAL or SPLIT_LOOP), even if the word "extract" appears.
      - Never select REPLACE_LOOP_WITH_PIPELINE or SPLIT_LOOP unless the code has a for/while/do-while loop.
    STEP 4: If the code has no class declaration (bare method), set scope_anchor.class to an empty string.
    STEP 5: Output ONLY JSON. No preamble, no markdown, no explanation.

    ### EXAMPLE 1 — FLATTEN_CONDITIONAL
    Instruction: "Flatten the nested ifs in processOrder using guard clauses"
    Code: public class A { void processOrder() { if(x) { if(y) { doWork(); } } } }

    Output:
    {
      "classification_scratchpad": "Instruction targets conditional structure. Code has nested if-statements in processOrder method. Category is CONTROL_FLOW, intent is FLATTEN_CONDITIONAL.",
      "intent_packet": {
        "refactor_category": "CONTROL_FLOW",
        "specific_intent": "FLATTEN_CONDITIONAL",
        "scope_anchor": {
          "class": "A",
          "member": "processOrder",
          "unit_type": "METHOD_UNIT"
        }
      }
    }

    ### EXAMPLE 2 — DECOMPOSE_CONDITIONAL
    Instruction: "Decompose the complex condition in isEligible into named booleans"
    Code: public class A { boolean isEligible(int age) { if (age >= 18 && age <= 65) return true; return false; } }

    Output:
    {
      "classification_scratchpad": "Instruction asks to break a compound condition into named boolean variables. Code has a compound condition in isEligible. Category is CONTROL_FLOW, intent is DECOMPOSE_CONDITIONAL.",
      "intent_packet": {
        "refactor_category": "CONTROL_FLOW",
        "specific_intent": "DECOMPOSE_CONDITIONAL",
        "scope_anchor": {
          "class": "A",
          "member": "isEligible",
          "unit_type": "METHOD_UNIT"
        }
      }
    }

    ### EXAMPLE 3 — SPLIT_LOOP
    Instruction: "Split the loop into two separate loops for each operation"
    Code: public class A { void m() { for(int i=0;i<10;i++) { doX(); doY(); } } }

    Output:
    {
      "classification_scratchpad": "Instruction asks to split a single loop into multiple loops. Code has one for-loop in method m. Category is CONTROL_FLOW, intent is SPLIT_LOOP.",
      "intent_packet": {
        "refactor_category": "CONTROL_FLOW",
        "specific_intent": "SPLIT_LOOP",
        "scope_anchor": {
          "class": "A",
          "member": "m",
          "unit_type": "METHOD_UNIT"
        }
      }
    }
```

**Justification:** Adding explicit STEP 3 breaks the "extract/decompose → EXTRACT_METHOD" association that caused 4/4 misclassifications. STEP 4 fixes class-name hallucination on bare methods (4/15 scope failures were actually prompt-fixable, though the harness bug also contributed).

---

#### B. `planner.architect_analysis`

**Current flaw:** No constraint on `new_structures_needed` → model hallucinates. No "scan all occurrences" instruction.

**Rewrite:**
```yaml
  architect_analysis: |
    ### ROLE
    Analyze what needs to change in the code. Identify targets, dependencies, and elements to preserve. Do NOT design mutations yet.

    ### TASK
    Given the intent packet and user instruction, identify:
    1. PRIMARY targets: methods or fields the instruction directly asks to change
    2. SECONDARY targets: methods or fields affected by the primary changes (callers, referenced fields, other methods using same magic number)
    3. NEW structures: ONLY methods, fields, constants, or enums the instruction EXPLICITLY requests. If the instruction only modifies existing code, leave this list EMPTY.
    4. MUST PRESERVE: string literals, exception types, error messages, method signatures that must stay identical

    ### RULES
    - Scan ALL code for ALL occurrences of the target pattern (magic numbers, repeated expressions, fields to rename). List every affected location in primary_targets or secondary_targets.
    - Do NOT list helper methods, constants, or fields in new_structures_needed unless the instruction explicitly names them or asks for them.
    - If the code has no class declaration, do not invent a class name.
    - For EXTRACT_METHOD: the new method name should be in new_structures_needed, but ONLY if the instruction names it.

    ### OUTPUT FORMAT
    Output ONLY JSON. No preamble.
    {
      "analysis_scratchpad": "Reasoning about the code structure and what needs to change",
      "primary_targets": ["methodName"],
      "secondary_targets": ["otherMethod"],
      "new_structures_needed": [],
      "must_preserve": ["Exception: IllegalArgumentException", "String: 'Order has no items'"]
    }
```

**Justification:** Explicit "ONLY... EXPLICITLY requests" + "leave EMPTY" rule stops hallucination (guardClauseHelper, INVALID_ORDER_MESSAGE). "Scan ALL code for ALL occurrences" fixes cross-reference misses. The raw analysis for `const_circle_pi` actually DID find both methods, but the synthesis failed — this prompt change ensures consistency.

---

#### C. `planner.architect`

**Current flaw:** Synthesis ignores analysis context, copies template text, allows mutation explosion, doesn't constrain target format.

**Rewrite:**
```yaml
  architect: |
    ### ROLE
    Translate the structural analysis into precise AST mutations. You operate ONLY on the provided analysis. Do not re-derive targets or signatures from the raw code.

    ### INPUT
    You receive:
    - Analysis: list of primary targets, secondary targets, new structures needed, elements to preserve
    - Intent packet: the classified intent
    - User instruction: the original request
    - Code: the original code

    ### RULES
    1. Map each primary_target to exactly one MODIFY_METHOD mutation
    2. Map each new_structure_needed item to exactly one ADD_METHOD, ADD_FIELD, ADD_CONSTANT, or ADD_ENUM
    3. Map each secondary_target to one mutation ONLY if it must change
    4. Use parameter types and return types from the analysis new_structures_needed descriptions. Do NOT copy parameters from the original method being refactored.
    5. Include every item in must_preserve exactly as-is (no modification)
    6. CONCISENESS: Maximum 5 ast_mutations. Consolidate related changes into single high-level mutations.
    7. If the code has no class declaration, set target_class to an empty string.
    8. The mutation target field must be ONLY the identifier name (e.g., "methodName", not "boolean methodName(...)")
    9. The body_abstract must describe the ACTUAL logic for THIS intent, not generic template text.

    ### VALID ACTIONS
    ADD_METHOD | REMOVE_METHOD | MODIFY_METHOD | ADD_FIELD | REMOVE_FIELD | ADD_CONSTANT | ADD_ENUM | RENAME_SYMBOL

    ### OUTPUT FORMAT
    Output ONLY JSON. No preamble, no markdown.
    {
      "architect_scratchpad": "How each analysis item maps to a specific mutation",
      "ast_modification_plan": {
        "target_class": "ClassName",
        "ast_mutations": [
          {
            "action": "MODIFY_METHOD",
            "target": "methodName",
            "details": {
              "modifiers": ["public"],
              "type": "void",
              "parameters": [],
              "logic_changes": ["Replace nested ifs with guard clauses using early returns/exceptions"],
              "body_abstract": "Invert all conditionals. Each original exception becomes a guard clause at the top with immediate throw."
            }
          }
        ]
      }
    }
```

**Justification:** Rule 4 prevents parameter copying from original method (tax_calculator bug: got `price, quantity, taxRate` instead of `subtotal, taxRate`). Rule 6 caps mutations at 5 (prevents 14-mutation explosion in setZeroes). Rule 7 fixes classless-code class invention. Rule 8 prevents signature-in-target format bug (`boolean matchesZeroOrMore(...)`). Rule 9 explicitly forbids copy-pasting template text — the `const_circle_pi` synthesis pasted FLATTEN body_abstract into a constant extraction plan.

---

#### D. `generator.coder`

**Current flaw:** 8 anti-pattern rules — 3B model drops later rules. Rule #4 (no merged guard clauses) ignored. No explicit instruction about logic preservation during flatten.

**Rewrite:**
```yaml
generator:
  coder: |
    ### ROLE
    Silent execution engine. Apply the ast_modification_plan to the base code exactly as specified.

    ### RULES
    1. Apply mutations in the order listed in the plan
    2. DATA INTEGRITY: Preserve string literals, exception types, and error messages from the original code unless the plan explicitly changes them
    3. CONSTANT USAGE: If the plan defines constants or enums, use their names — do not keep the original numeric literal values
    4. LOGIC PRESERVATION: For FLATTEN_CONDITIONAL, each original if-condition must map to an equivalent inverted condition. Do NOT change which branch executes for a given input. Premium users must still get premium discounts.

    ### ANTI-PATTERNS (MOST IMPORTANT — NEVER VIOLATE)
    1. NEVER merge multiple guard clauses or validation checks into one combined condition with || or &&. Each original throw statement must become its own separate if-check at the top level, even if the result is longer.
    2. NEVER change exception types (IllegalArgumentException stays as is, etc.)
    3. NEVER add any method not listed in the plan's ast_mutations

    ### OUTPUT FORMAT
    Output ONLY the refactored code wrapped in <code> tags. No explanation, no markdown, no preamble.

    <code>
    public class X { ... }
    </code>
```

**Justification:** Reduced from 8 rules to 3. "NEVER merge guard clauses" promoted to #1 with explicit "even if longer" instruction. This fixes both real merges and gives detector clearer signal.

**Critical addition:** Rule 4 "LOGIC PRESERVATION" explicitly instructs the model to preserve branch semantics during flatten. The `gen_flatten_orderprocessor` bug (premium users losing discount) would be caught by this rule. Removed redundant rules (remove method, invent variables, comments, imports, output format) — these are lower-frequency violations.

---

#### E. `judge.auditor`

**Current flaw:** 5 audit tasks + 3 rules + complex output schema = 3B model skips tasks. No explicit identity check. PLAN FIDELITY is ambiguous for no-ops.

**Rewrite:**
```yaml
judge:
  auditor: |
    ### ROLE
    Structural Auditor. Detect logic drift or semantic errors in refactored code.

    ### CONTEXT YOU RECEIVE
    You will be given:
    - Plan summary: what the refactoring was intended to do
    - Planned mutations: what specific changes were requested
    - Original code and refactored code

    ### STEP 1 — PLAN EXECUTION CHECK (MANDATORY)
    Compare the planned mutations to the actual refactored code.
    - If the refactored code is character-for-character identical to the original but the plan lists mutations (ADD_METHOD, ADD_FIELD, etc.), verdict MUST be REVISE with issue "Plan was not executed: code unchanged."
    - If planned ADD_METHOD / ADD_FIELD / ADD_CONSTANT items are missing from the refactored code, verdict MUST be REVISE.
    - Count how many planned mutations were executed.

    ### STEP 2 — SIGNATURE CHECK (MANDATORY)
    Compare every method's return type, name, and parameter list between original and refactored code. They must match unless the plan explicitly changes them. Flag any unplanned signature changes.

    ### STEP 3 — LOGIC CHECK (MANDATORY)
    For the same inputs, do the conditional paths produce the same outputs? Trace at least one concrete example through both versions.

    ### STEP 4 — VERDICT
    ACCEPT only if: (a) planned mutations were executed, AND (b) signatures match, AND (c) logic is equivalent.
    REVISE if any of the above fail.

    ### RULES
    - Standard refactoring idioms (guard clauses with early returns, returning boolean evaluations directly, extracting helper methods) are ACCEPTABLE.
    - Changes explicitly listed in the plan mutations are NOT errors — they were requested.
    - Demand REVISE only if logic drift would cause different behavior OR if the plan was not executed.

    ### OUTPUT FORMAT
    Output ONLY JSON. No preamble, no markdown tags, no XML tags.
    {
      "audit_scratchpad": {
        "plan_execution": "Summary of which planned mutations were executed.",
        "signature_comparison": "Any unplanned signature changes.",
        "logic_comparison": "Structural summary of conditional paths with concrete example."
      },
      "verdict": "ACCEPT",
      "issues": []
    }
```

**Justification:** Reduced from 5 tasks to 3 (eliminated VARIABLE TRACE — low signal, high token cost). Moved PLAN EXECUTION CHECK to position #1 with explicit identity rule. This catches the `decompose_noop` blind spot. SIGNATURE CHECK moved to #2 — it's the most reliable task. Added "concrete example" requirement to LOGIC CHECK to force the model to actually trace execution rather than defaulting to "paths are identical."

---

### 3.2 INFRASTRUCTURE FIXES (Test Harness & Validator)

#### Fix A: Hallucination detector exempts ADD_* targets

**Location:** `tests/model_tests/harness.py` — `detect_hallucinations()`

**Change:** Before checking candidates against `code_identifiers`, remove:
- Any item from `analysis_data["new_structures_needed"]`
- Any `target` from mutations where `action` is `ADD_METHOD`, `ADD_FIELD`, `ADD_CONSTANT`, or `ADD_ENUM`

These are expected to be new names.

#### Fix B: Scope checker uses unwrapped code for `classes_in_code`

**Location:** `tests/model_tests/harness.py` — `run_planner_case()`

**Change:** Determine `classes_in_code` by parsing the original code with `javalang.parse.parse()` directly (which will fail for bare methods), NOT by using the validator-wrapped AST. Or check which template index was used: if template 1 (METHOD_UNIT wrapper), set `classes_in_code=False`.

#### Fix C: `member_exists` checks fields and variables

**Location:** `tests/model_tests/harness.py` — `check_scope_anchor_exists()`

**Change:** In addition to MethodDeclaration, check:
- FieldDeclaration declarators
- VariableDeclarator names

#### Fix D: Validator semantic smoke test

**Location:** `app/modules/validator.py` — add new method

**Addition:** After `check_syntax` passes, run a semantic smoke test:
- For any method body containing only a single statement like `Do something;` or `Foo bar;` where `Do`/`Foo` is not a known Java type — flag as suspicious.
- Alternatively: compile a list of known Java types (java.lang.*, primitives) and flag unknown capitalized identifiers used as types in LocalVariableDeclaration.

This catches the `bad_hallucinated_add` "Do something;" nonsense.

#### Fix E: Intent math adds semantic branch comparison for FLATTEN

**Location:** `app/modules/validator.py` — `verify_flatten_conditional()`

**Addition:** In addition to depth comparison, extract all `throw new XxxException(...)` statements from original and refactored code. Count them and compare exception types + messages. If the refactored code has fewer distinct throw statements, or if exception messages were merged/altered, flag as failure.

This catches both merged guard clauses AND the OrderProcessor logic inversion (which eliminated the premium discount branch).

#### Fix F: Orchestrator syntax healing improvement

**Location:** `app/modules/orchestrator.py` — `_run_phase_3()`

**Changes:**
1. On syntax retry, do NOT include `Base Code`. Only include:
   - Modification Plan
   - CURRENT BROKEN CODE
   - PREVIOUS SYNTAX ERROR
   - "Fix the syntax error in this code. Output only valid Java wrapped in <code> tags."
2. Increase temperature to 0.3 on retry to encourage different output.
3. If retry fails 3 times, don't just increment strategy_iter — first try simplifying the plan (e.g., remove body_abstract fields which may contain template noise).

---

### 3.3 PIPELINE CHANGES

#### Change A: Pre-flight plan validation

**Location:** Orchestrator between Phase 2 and Phase 3

**Implementation:** Before sending plan to Generator:
1. Verify every `ast_mutation.target` is a valid Java identifier (regex `[A-Za-z_$][A-Za-z0-9_$]*`)
2. For MODIFY_METHOD/RENAME_SYMBOL: verify target exists in original code AST
3. For ADD_METHOD/ADD_FIELD/ADD_CONSTANT: verify target does NOT exist in original code AST (prevents no-op additions)
4. Verify `target_class` exists in original code or is empty string
5. Cap mutation count at 5

**Impact:** Catches hallucinated targets, invented class names, and mutation explosion before Generator runs.

#### Change B: Identity gate before Judge

**Location:** Orchestrator between Phase 4 and Phase 5

**Implementation:**
```python
if state.working_code.strip() == state.base_code.strip():
    if state.active_plan and state.active_plan.get("ast_mutations"):
        # Short-circuit to REVISE without calling Judge
        state.add_feedback({"failure_tier": FailureTier.TIER_3_JUDGE, 
                           "error": "Plan was not executed: code unchanged."})
        state.strategy_iter += 1
        state.current_phase = 2
        return
```

**Impact:** Guarantees no-op detection, saves Judge calls, prevents false ACCEPTs.

#### Change C: Generator output semantic validation

**Location:** Orchestrator Phase 4, after syntax check

**Implementation:** After syntax passes, before structural checks, run a lightweight semantic validator:
- For FLATTEN intent: verify every original `throw new XxxException(...)` has a matching throw in refactored code with same type and message.
- For EXTRACT_METHOD: verify the new method is actually called from the original method (not just added and orphaned).
- For RENAME_SYMBOL: verify old name is absent in output.

**Impact:** Catches logic inversions and orphaned methods before Judge phase.

---

### 3.4 PRIORITIZED PLAN

| Rank | Fix | Impact | Effort | Expected Improvement |
|------|-----|--------|--------|---------------------|
| 1 | **Prompt: Classifier DECOMPOSE/SPLIT examples + classless rule** | Fixes 4/4 misclassifications. Fixes scope for bare methods. | Low | +27% classifier accuracy, +27% scope validity |
| 2 | **Infra: Fix harness hallucination detector** | Stops false flags on ADD_* targets. Makes metrics trustworthy. | Low | Metrics only — reveals true ~35-40% planner capability |
| 3 | **Infra: Fix harness scope checker** | Stops false scope failures on bare methods and fields. | Low | +20% scope validity |
| 4 | **Prompt: Generator anti-pattern reduction + logic preservation rule** | Fixes FLATTEN merge bug AND logic inversion. | Low | +18% generator pass rate (FLATTEN cases), prevents semantic corruption |
| 5 | **Prompt: Judge task reduction + identity check + concrete examples** | Catches no-ops. Forces actual reasoning. | Low | +7% judge accuracy, eliminates systematic decompose_noop failure |
| 6 | **Pipeline: Pre-flight plan validation** | Catches bad plans before Generator. | Medium | +15% end-to-end success rate |
| 7 | **Pipeline: Identity gate before Judge** | Guarantees no-op detection. Saves calls. | Low | -10% false ACCEPT, faster pipeline |
| 8 | **Validator: Semantic smoke test + FLATTEN throw-comparison** | Catches `Do something;` nonsense and logic inversions. | Medium | Prevents invalid Java and semantic corruption from reaching Judge |
| 9 | **Prompt: Architect synthesis guards (max 5 mutations, no template text, target format)** | Prevents mutation explosion and copy-paste errors. | Low | +10% plan executability |
| 10 | **Orchestrator: Syntax healing retry (remove base_code, raise temp, simplify plan)** | Makes syntax healing actually work. | Medium | Reduces syntax loop failures |

**Combined expected improvement:**
- Planner plan executability: 40% (reported) → ~60-65% (true, after harness fixes + prompt improvements)
- Generator pass rate: 82% → ~90% (with logic preservation rule)
- Judge accuracy: 88% → ~95% (with identity check + parse error reduction)
- End-to-end pipeline: significantly improved because Planner is the main bottleneck

---

### 3.5 NEW TEST CASES (Targeting Failure Patterns)

#### Case 1: `classifier_decompose_vs_extract_boundary`
**Intent:** DECOMPOSE_CONDITIONAL  
**Code:**
```java
public class A {
    boolean canVote(int age, boolean citizen) {
        if (age >= 18 && citizen) return true;
        return false;
    }
}
```
**Instruction:** "Decompose the compound condition in canVote into named booleans: isAdult and isCitizen."  
**Expected:** Classifier outputs DECOMPOSE_CONDITIONAL (not EXTRACT_METHOD). Tests the decompose/extract boundary.

---

#### Case 2: `classifier_split_vs_extract_boundary`
**Intent:** SPLIT_LOOP  
**Code:**
```java
public class A {
    void process(int[] arr) {
        for (int i = 0; i < arr.length; i++) {
            arr[i] = arr[i] * 2;
            System.out.println(arr[i]);
        }
    }
}
```
**Instruction:** "Split the loop into two loops: one for doubling and one for printing."  
**Expected:** Classifier outputs SPLIT_LOOP (not EXTRACT_METHOD).

---

#### Case 3: `scope_bare_method_no_class`
**Intent:** FLATTEN_CONDITIONAL  
**Code:**
```java
public boolean check(int x, int y) {
    if (x > 0) {
        if (y > 0) {
            return true;
        }
    }
    return false;
}
```
**Instruction:** "Flatten the nested ifs using guard clauses."  
**Expected:** Scope anchor class is empty string. Tests classless-code rule.

---

#### Case 4: `analysis_cross_reference_constant`
**Intent:** EXTRACT_CONSTANT  
**Code:**
```java
public class Config {
    public int getTimeout() { return 5000; }
    public int getRetryDelay() { return 5000; }
}
```
**Instruction:** "Extract the magic number 5000 into a constant named DEFAULT_TIMEOUT."  
**Expected:** Analysis lists both `getTimeout` and `getRetryDelay` as targets. Tests "scan ALL occurrences" rule.

---

#### Case 5: `analysis_no_hallucination`
**Intent:** FLATTEN_CONDITIONAL  
**Code:**
```java
public class B {
    void run(String s) {
        if (s != null) {
            if (!s.isEmpty()) {
                process(s);
            } else {
                throw new IllegalArgumentException("empty");
            }
        } else {
            throw new IllegalArgumentException("null");
        }
    }
}
```
**Instruction:** "Flatten the nested ifs to guard clauses. Preserve exception types and messages."  
**Expected:** Analysis `new_structures_needed` is EMPTY. No invented helper methods. Tests "only explicit" rule.

---

#### Case 6: `synthesis_no_template_bleed`
**Intent:** EXTRACT_CONSTANT  
**Code:**
```java
public class Circle {
    public double area(double r) {
        return 3.14 * r * r;
    }
}
```
**Instruction:** "Extract 3.14 into a constant PI."  
**Expected:** Synthesis body_abstract describes constant extraction, NOT guard clauses or flattening. Tests template-text isolation.

---

#### Case 7: `generator_logic_preservation_flatten`
**Intent:** FLATTEN_CONDITIONAL  
**Code:**
```java
public class Discount {
    void apply(int total, boolean premium) {
        if (total > 100) {
            if (premium) {
                discount(0.20);
            } else {
                discount(0.10);
            }
        }
    }
}
```
**Plan:** MODIFY_METHOD(apply) — flatten to guard clauses.  
**Expected:** Generator output must preserve: total>100 AND premium → 0.20, total>100 AND NOT premium → 0.10, total<=100 → no discount. NO logic inversion. Tests Rule 4 in coder prompt.

---

#### Case 8: `generator_no_merge_guard_clauses`
**Intent:** FLATTEN_CONDITIONAL  
**Code:**
```java
public class A {
    void validate(String a, String b, String c) {
        if (a != null) {
            if (b != null) {
                if (c != null) {
                    save(a, b, c);
                } else {
                    throw new IllegalArgumentException("c null");
                }
            } else {
                throw new IllegalArgumentException("b null");
            }
        } else {
            throw new IllegalArgumentException("a null");
        }
    }
}
```
**Plan:** MODIFY_METHOD(validate) — flatten to guard clauses.  
**Expected:** Three separate `if (...) throw ...;` statements. No `||` combined checks. Tests anti-pattern #1.

---

#### Case 9: `judge_identity_noop`
**Intent:** DECOMPOSE_CONDITIONAL  
**Original:**
```java
public class A {
    boolean ok(int x) {
        if (x > 0 && x < 10) return true;
        return false;
    }
}
```
**Refactored:** Identical to original.  
**Plan:** "Intent: DECOMPOSE_CONDITIONAL. Mutations: ADD_FIELD(isPositive), ADD_FIELD(isSmall), MODIFY_METHOD(ok)"  
**Expected:** REVISE. Tests Judge Step 1 identity check.

---

#### Case 10: `judge_signature_priority`
**Intent:** EXTRACT_METHOD  
**Original:**
```java
public class A {
    public int calc(int a, int b) {
        return a + b;
    }
}
```
**Refactored:**
```java
public class A {
    public void calc(int a, int b) {
        System.out.println(a + b);
    }
}
```
**Plan:** "Intent: EXTRACT_METHOD. Target: A.calc."  
**Expected:** REVISE. Return type changed int→void. Tests SIGNATURE CHECK priority.

---

#### Case 11: `validator_semantic_smoke`
**Code:**
```java
public class A {
    void m() {
        Do something;
    }
}
```
**Expected:** `check_syntax` should return `is_valid=False` or at least flag `Do something;` as semantically invalid. Tests semantic smoke test.

---

#### Case 12: `orchestrator_syntax_healing`
**Setup:** Plan with hallucinated target `nonExistentMethod`.  
**Expected:** Orchestrator pre-flight validation catches it before Generator runs. No syntax healing loop triggered. Tests pre-flight plan validation.

---

## Appendix: Raw Data Evidence Locations

| Finding | Source File | Field / Case |
|---------|-------------|--------------|
| DECOMPOSE misclassified | planner_isolated_results.json | `decomp_closed_island`, `decomp_regex_dp` → `actual_intent: EXTRACT_METHOD` |
| Class name hallucination | planner_isolated_results.json | `flat_binary_search` → `scope_detail: A.search` (code has no class) |
| `CONSTANT_PI` flagged as hallucination | planner_isolated_results.json | `const_circle_pi` → `hallucinations: ["CONSTANT_PI"]` |
| `computeTaxWithRounding` flagged as hallucination | planner_isolated_results.json | `extract_tax_calculator` → `hallucinations: ["computeTaxWithRounding"]` |
| Synthesis copies FLATTEN template | planner_isolated_results.json | `const_circle_pi` → `synthesis_raw` contains "Invert all conditionals..." |
| Synthesis target has full signature | planner_isolated_results.json | `decomp_regex_dp` → `target: "boolean matchesZeroOrMore(...)"` |
| Judge decompose_noop all ACCEPT | judge_isolated_results.json | `revise_decompose_noop` → all 5 runs ACCEPT |
| Judge decompose_noop short scratchpads | judge_isolated_results.json | `revise_decompose_noop` runs → scratchpad 171-453 chars |
| Judge parse error had good reasoning | judge_isolated_results.json | `revise_extract_constant_broken_sig` run 3 → `raw_content` has detailed analysis |
| Generator flatten_orderprocessor logic inversion | generator_isolated_results.json | `gen_flatten_orderprocessor` → `output_code` has inverted discount logic |
| Generator simple_ifs merged guards | generator_isolated_results.json | `gen_flatten_simple_ifs` → `output_code` has `x == null \|\| y == null` |
| Generator bad_hallucinated_add invalid Java | generator_isolated_results.json | `bad_hallucinated_add` → `output_code` has `Do something;` |
| Generator bad_hallucinated_add syntax valid | generator_isolated_results.json | `bad_hallucinated_add` → `syntax_valid: True` |
| Scope valid False for bare methods | planner_isolated_results.json | All bare method cases → `scope_valid: False` |
| Scope valid False for field rename | planner_isolated_results.json | `rename_user_manager` → `scope_valid: False` |

---

*This analysis was generated from direct inspection of raw JSON outputs, test harness source code, orchestrator pipeline code, and validator logic. It corrects several mischaracterizations in the pre-written reports and identifies test infrastructure bugs that inflate failure rates.*
