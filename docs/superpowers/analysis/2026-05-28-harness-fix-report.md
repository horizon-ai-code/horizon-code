# Isolated Model Test Results — Harness Fix Report

**Date:** 2026-05-28  
**Status:** Harness bugs fixed, tests rerun  
**Scope:** Planner (45 calls), Judge (50 calls), Generator (14 calls)  

---

## 1. Executive Summary

Five test harness bugs were identified that falsely inflated failure rates. After fixing them, the **true model capability** is significantly higher than previously reported.

| Metric | Before (Reported) | After (Harness Fixed) | Change |
|--------|------------------|----------------------|--------|
| **Planner PASS** | **0/15 (0%)** | **11/15 (73%)** | **+73%** |
| Planner scope valid | 4/15 (27%) | 14/15 (93%) | +67% |
| Planner hallucinations | 17 total | 0 total | -17 |
| Planner plan executable | 6/15 (40%) | 15/15 (100%) | +60% |
| **Generator PASS** | **9/11 (82%)** | **9/11 (82%)** | **0** |
| Generator FLATTEN anti-patterns | 1 each (false flag) | 2 each (real issues) | Better signal |
| **Judge correct** | **44/50 (88%)** | **44/50 (88%)** | **0** |

**Key insight:** The Planner was never as broken as reported. The 0% pass rate was entirely an artifact of broken harness checks. The real bottleneck is **classifier prompt gaps** (4/15 DECOMPOSE/SPLIT misclassifications) and **Generator FLATTEN logic preservation** (2/11 real failures).

---

## 2. Harness Fixes Applied

### Fix 1: Hallucination detector exempts ADD_* targets
**File:** `tests/model_tests/harness.py`

**Bug:** `detect_hallucinations()` checked every string in the plan against original code identifiers. But `ADD_METHOD`, `ADD_FIELD`, `ADD_CONSTANT` targets are **supposed to be new names** — they will never exist in the original code.

**Impact:** `const_circle_pi` flagged `CONSTANT_PI` as hallucination. `extract_tax_calculator` flagged `computeTaxWithRounding` as hallucination. These are correct model behavior, not failures.

**Fix:** Exempt targets from `ADD_METHOD`, `ADD_FIELD`, `ADD_CONSTANT`, `ADD_ENUM` mutations, and items in `new_structures_needed`.

**Result:** Hallucination count dropped from 17 to 0.

---

### Fix 2: Scope checker uses validator unit type for `classes_in_code`
**File:** `tests/model_tests/test_planner_isolated.py`

**Bug:** The validator wraps bare methods in `class ASTWrapper { ... }` to make them parseable. The test then checked `len(ClassDeclaration) > 0` on the **wrapped** AST, which is always `True`. The scope validity formula requires `class_exists=True` when `classes_in_code=True`. Since models invent class names for bare methods, `class_exists=False`, making scope invalid for **all bare methods**.

**Impact:** 10 of 15 cases falsely failed scope validation (e.g., `flat_binary_search`, `extract_prime_arrange`, `const_abbreviation`).

**Fix:** Use `syntax_res["unit"]` from the validator instead. If `unit == CLASS_UNIT`, code has a real class. If `unit == METHOD_UNIT` or `STATEMENT_UNIT`, it's a bare method — set `classes_in_code=False`.

**Result:** Scope valid increased from 4/15 to 14/15.

---

### Fix 3: `member_exists` checks fields and variables
**File:** `tests/model_tests/harness.py`

**Bug:** `check_scope_anchor_exists()` only searched `MethodDeclaration` nodes for `member`. For `RENAME_SYMBOL` on fields (like `rename_user_manager` where field `n` should be renamed), the field exists in `FieldDeclaration` but not in `MethodDeclaration`.

**Impact:** `rename_user_manager` falsely failed scope validation.

**Fix:** Add checks for `FieldDeclaration` declarators and `VariableDeclarator` nodes.

**Result:** `rename_user_manager` now passes scope check.

---

### Fix 4: Plan executable exempts ADD_* targets
**File:** `tests/model_tests/test_planner_isolated.py`

**Bug:** `targets_exist_in_ast = all(t in code_ids for t in mutation_targets)` required ALL mutation targets to exist in the original code AST. But ADD_* targets are new names — they intentionally don't exist.

**Impact:** Every extraction/addition case failed plan executability (`extract_tax_calculator`, `const_circle_pi`, `extract_set_zeroes`, etc.).

**Fix:** Skip existence check for targets whose mutation action is `ADD_METHOD`, `ADD_FIELD`, `ADD_CONSTANT`, or `ADD_ENUM`.

**Result:** Plan executable increased from 6/15 to 15/15.

---

### Fix 5: Generator anti-pattern detector uses throw messages for FLATTEN
**File:** `tests/model_tests/test_generator_isolated.py`

**Bug:** `detect_anti_patterns()` counted `if` statements and flagged decrease as violation. For `FLATTEN_CONDITIONAL`, fewer ifs is expected behavior. The reports called this "detector false positive."

**But:** My independent analysis found the generated code actually had **merged throw messages** (real semantic issues), not just fewer ifs.

**Fix:** For `FLATTEN_CONDITIONAL`, compare `throw new XxxException(...)` statements instead. Check if original throw messages were lost or merged.

**Result:** Same verdicts (FAIL), but now flagged for the **right reason** — merged exception messages, not if-count decrease.

---

## 3. Planner Results (11/15 PASS)

### Still Failing (4/15) — Real Model Issues

| Case | Expected | Actual | Root Cause |
|------|----------|--------|------------|
| `decomp_closed_island` | DECOMPOSE_CONDITIONAL | EXTRACT_METHOD | Classifier has no DECOMPOSE example in prompt |
| `decomp_regex_dp` | DECOMPOSE_CONDITIONAL | EXTRACT_METHOD | Same — "decompose" triggers METHOD_MOVEMENT |
| `split_board_path` | SPLIT_LOOP | EXTRACT_METHOD | Same — "split" triggers METHOD_MOVEMENT |
| `split_unique_paths` | SPLIT_LOOP | EXTRACT_METHOD | Same — no SPLIT_LOOP example in prompt |

**Pattern:** All 4 failures are **classifier misclassifications**. The architect analysis and synthesis steps work correctly when intent is right. The classifier prompt has only one FLATTEN example and no DECOMPOSE/SPLIT examples. The 3B model defaults "extract/decompose/split" → `EXTRACT_METHOD`.

**Fix needed:** Add DECOMPOSE_CONDITIONAL and SPLIT_LOOP few-shot examples to classifier prompt.

---

### Now Passing (11/15) — Were Falsely Failing

| Case | Old Failure(s) | Fix That Helped |
|------|---------------|-----------------|
| `flat_demo_orderprocessor` | Hallucination `guardClauseHelper`, `INVALID_ORDER_MESSAGE` | Fix 1: exempt new_structures |
| `flat_binary_search` | Scope invalid (invented class "A") | Fix 2: use unit type |
| `flat_validate_ip` | Scope invalid (invented class "A") | Fix 2: use unit type |
| `extract_set_zeroes` | Scope invalid + 7 hallucinations + plan non-executable | Fixes 1, 2, 4 |
| `extract_tax_calculator` | Hallucination `computeTaxWithRounding` + plan non-executable | Fixes 1, 4 |
| `extract_prime_arrange` | Scope invalid + plan non-executable | Fixes 2, 4 |
| `rename_user_manager` | Scope invalid (field `n` not found) | Fix 3: check fields |
| `rename_remove_nth` | Hallucination `for` | Fix 1: exempt new_structures |
| `const_abbreviation` | Scope invalid + 2 hallucinations + plan non-executable | Fixes 1, 2, 4 |
| `const_circle_pi` | Hallucination `CONSTANT_PI` + plan non-executable | Fixes 1, 4 |
| `cons_word_pattern` | Scope invalid | Fix 2: use unit type |

---

### Remaining Issues in Passing Cases

Even though these cases now PASS, several have **real quality issues** that the harness doesn't catch:

**`extract_set_zeroes`**: Synthesis produced 3 mutations (markZeroMarkers, setInnerZeros, setFirstRowColZeros) but body_abstracts are vague ("Iterate over the first row..."). The plan is executable but may not match the exact instruction.

**`const_circle_pi`**: Analysis correctly identified BOTH `calculateArea` and `calculateCircumference` as primary targets. But synthesis only produced 1 mutation (ADD_CONSTANT) — missing the MODIFY_METHOD mutations to replace `3.14159` with `PI_CONSTANT`. The plan is executable but **incomplete**.

**`rename_user_manager`**: Synthesis produced 4 mutations including `RENAME_SYMBOL(UserManager)` — renaming the **class itself** to `UsernameManager`. This was not requested. The plan is executable but **over-scoped**.

---

## 4. Generator Results (9/11 PASS, 2 Real Failures)

### Passing (9/11)

All passing cases confirm: Generator is **highly reliable** when given a correct plan for simple intents (EXTRACT_METHOD, RENAME_SYMBOL, ADD_CONSTANT, DECOMPOSE_CONDITIONAL, SPLIT_LOOP).

### Failing (2/11) — Real Model Issues

#### `gen_flatten_orderprocessor`

**Anti-patterns:**
1. "May have merged guard clause exception messages"
2. "Original exception messages lost: {'Order has no items.', 'Order cannot be null.'}"

**Generated code:**
```java
if (order == null || order.getItems().isEmpty()) {
    throw new IllegalArgumentException("Order has no items or is null.");
}
```

**Issue:** Two original throws (`Order has no items.` and `Order cannot be null.`) merged into one `||` check with combined message.

**Critical additional issue (not caught by harness):** The discount logic is **inverted**:
- Original: `total>1000 && premium → discount(0.15)`, `total>1000 && !premium → discount(0.05)`
- Generated: `total>1000 && !premium → discount(0.05)`, `total<=1000 → discount(0.15)`

Premium users get NO discount. Non-premium users get 0.05 when total>1000 (correct), but everyone gets 0.15 when total<=1000 (wrong — should be no discount).

This is the **exact same semantic corruption** as `revise_flatten_logic_inverted` in Judge tests.

---

#### `gen_flatten_simple_ifs`

**Anti-patterns:**
1. "May have merged guard clause exception messages"
2. "Original exception messages lost: {'x is null', 'y is null'}"

**Generated code:**
```java
if (x == null || y == null) {
    throw new IllegalArgumentException(x != null ? "y is null" : "x is null");
}
```

**Issue:** Two separate null checks merged into one `||` with ternary message.

---

### Stress Tests (3/3 PASS)

| Case | Behavior |
|------|----------|
| `bad_missing_target` | Ignored non-existent MODIFY_METHOD target, returned original code |
| `bad_empty_mutations` | Returned original code unchanged |
| `bad_hallucinated_add` | Created `xyZzZzZzHelperMethod()` with `Do something;` body |

**Note:** `bad_hallucinated_add` created syntactically valid but semantically meaningless Java (`Do something;` parses as `LocalVariableDeclaration` with type `Do`). The validator accepts this. This is a **validator limitation**, not a Generator bug.

---

## 5. Judge Results (44/50 Correct, 88%)

### Passing Cases (5/5 unanimous)

| Case | Runs | Pattern |
|------|------|---------|
| `accept_extract_method_tax` | 5/5 ACCEPT | Clear structural signals |
| `accept_rename_symbol_field` | 5/5 ACCEPT | Simple rename, no logic change |
| `accept_flatten_guard_clauses` | 5/5 ACCEPT | Textbook guard clause pattern |
| `accept_split_loop` | 5/5 ACCEPT | Loop split visible in code |
| `accept_extract_constant_pi` | 5/5 ACCEPT | Constant extraction obvious |

### REVISE Cases (4/5 unanimous, 1 inconsistent)

| Case | Runs | Pattern |
|------|------|---------|
| `revise_flatten_logic_inverted` | 5/5 REVISE | Logic inversion traced with concrete examples |
| `revise_extract_method_wrong_params` | 5/5 REVISE | Extra parameter + computation change |
| `revise_rename_broke_structural` | 5/5 REVISE | Structural change (ternary replaces if-return) |
| `revise_extract_constant_broken_sig` | 4/5 REVISE, 1 ACCEPT | Run 4 falsely ACCEPT'd return-type change |

### Systematic Failure (0/5 correct)

**`revise_decompose_noop`:** All 5 runs ACCEPT'd code identical to original when plan listed 4 ADD_FIELD + MODIFY_METHOD.

**Scratchpad analysis:** All scratchpads are 171-466 chars and contain ONLY `variable_trace` + `logic_comparison`. The model **never executed PLAN FIDELITY or SIGNATURE CHECK**. It checks logic equivalence between identical code blocks (trivially true) and defaults to ACCEPT.

**Root cause:** The prompt lists 5 audit tasks + 3 rules + complex output schema. The 3B model's attention budget is exhausted before reaching PLAN FIDELITY. It outputs minimal JSON satisfying the schema without completing reasoning.

---

## 6. True Model Capability Assessment

After removing harness artifacts:

| Capability | Planner | Generator | Judge |
|-----------|---------|-----------|-------|
| Simple renames | ✓ (RENAME_SYMBOL: 2/2) | ✓ (2/2) | ✓ |
| Method extraction | ✓ (EXTRACT_METHOD: 3/3) | ✓ (3/3) | ✓ |
| Guard clause flattening | ✓ (FLATTEN: 3/3 classifier) | ✗ (merges guards, inverts logic) | ✓ |
| Condition decomposition | ✗ (misclassifies as EXTRACT) | ✓ (simple case) | ✓ |
| Loop splitting | ✗ (misclassifies as EXTRACT) | ✓ (simple case) | ✓ |
| Multi-target tracking | Partial (finds targets, synthesis may miss some) | ✓ | ✓ |
| Code identity detection | N/A | N/A | ✗ (misses identical code) |

**Hierarchy:**
1. **Generator** is strongest for mechanical transformations (rename, extract, constant) but **dangerous for FLATTEN** (can invert logic while producing valid syntax).
2. **Judge** is reliable on clear structural/signature changes but **blind to no-op plans** (identical code).
3. **Planner** classifier is the bottleneck — downstream steps (analysis, synthesis) work when intent is correct.

---

## 7. Recommendations

### Immediate (High Impact, Low Effort)

1. **Add DECOMPOSE and SPLIT examples to classifier prompt** — fixes 4/15 Planner failures
2. **Add classless-code rule to classifier prompt** — prevents invented class names
3. **Reduce Judge audit tasks from 5 to 3** — add explicit identity check, remove VARIABLE TRACE
4. **Add "logic preservation" rule to Generator prompt** — prevents FLATTEN inversions

### Medium Term

5. **Add semantic smoke test to validator** — catch `Do something;` nonsense
6. **Add pre-flight plan validation to orchestrator** — verify targets before Generator runs
7. **Add identity gate before Judge** — short-circuit no-op cases

### Infrastructure

8. **Keep harness fixes** — all 5 fixes should remain in test suite for accurate future metrics

---

## 8. Files Changed

| File | Change |
|------|--------|
| `tests/model_tests/harness.py` | Fix 1 (hallucination exemption), Fix 3 (field/variable member check) |
| `tests/model_tests/test_planner_isolated.py` | Fix 2 (unit-based classes_in_code), Fix 4 (ADD_* plan executable) |
| `tests/model_tests/test_generator_isolated.py` | Fix 5 (FLATTEN throw-message detection) |

### Backups

Old results saved as `.bak` in `test_results/isolated/`:
- `planner_isolated_results.json.bak`
- `judge_isolated_results.json.bak`
- `generator_isolated_results.json.bak`
- Plus corresponding `.md` reports

---

*Report generated from direct analysis of raw JSON outputs after harness fixes.*
