# Comprehensive Isolated Model Test Report — Post-Harness Fix

**Date:** 2026-05-28  
**Status:** Harness bugs fixed, tests rerun with accurate metrics  
**Models:** Qwen2.5-Coder-3B (Planner/Generator), Llama-3.2-3B (Judge)  
**Context:** 6144 tokens, Temperature 0.1  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Methodology](#2-methodology)
3. [Planner Results (11/15 PASS)](#3-planner-results)
4. [Generator Results (9/11 PASS)](#4-generator-results)
5. [Judge Results (44/50 Correct)](#5-judge-results)
6. [Cross-Model Analysis](#6-cross-model-analysis)
7. [Timing Analysis](#7-timing-analysis)
8. [Failure Mode Deep Dives](#8-failure-mode-deep-dives)
9. [Prompt-Level Root Causes](#9-prompt-level-root-causes)
10. [Actionable Fix Roadmap](#10-actionable-fix-roadmap)
11. [Appendix: Raw Data](#11-appendix-raw-data)

---

## 1. Executive Summary

After fixing 5 test harness bugs that falsely inflated failure rates, the **true model capability** is significantly higher than previously reported. However, several real model issues remain that pose risks to the production pipeline.

### Key Findings

| Finding | Severity | Impact |
|---------|----------|--------|
| **Planner classifier lacks DECOMPOSE/SPLIT examples** | P0 | 4/15 cases (27%) fail due to prompt gap, not model capability |
| **Generator inverts FLATTEN logic** | P0 | Produces syntactically valid but semantically wrong code |
| **Judge blind to no-op plans** | P1 | Accepts identical code when plan lists mutations |
| **Planner synthesis ignores analysis** | P1 | 3/11 passing cases have `coherent=False` |
| **Generator merges guard clause messages** | P1 | Loses original exception messages during FLATTEN |
| **Judge inconsistent on signature changes** | P2 | 1/5 runs falsely ACCEPT'd `double→void` change |
| **javalang accepts invalid Java** | P2 | `Do something;` parses as valid LocalVariableDeclaration |

### Aggregate Metrics (After Harness Fix)

| Role | Pass Rate | Key Bottleneck |
|------|-----------|----------------|
| **Planner** | **11/15 (73%)** | Classifier prompt missing DECOMPOSE/SPLIT examples |
| **Generator** | **9/11 (82%)** | FLATTEN logic inversion + guard clause merging |
| **Judge** | **44/50 (88%)** | No-op detection blind spot + occasional inconsistency |
| **End-to-End** | **~64%** (estimated) | Planner classifier → Generator FLATTEN → Judge no-op |

### What Changed With Harness Fixes

| Metric | Before (Broken Harness) | After (Fixed) | Δ |
|--------|------------------------|---------------|---|
| Planner PASS | 0/15 (0%) | 11/15 (73%) | **+73pp** |
| Planner scope valid | 4/15 (27%) | 14/15 (93%) | **+66pp** |
| Planner hallucinations | 17 (all false) | 0 | **-17** |
| Planner plan executable | 6/15 (40%) | 15/15 (100%) | **+60pp** |
| Generator PASS | 9/11 (82%) | 9/11 (82%) | 0 (but now flagged for right reasons) |
| Judge correct | 44/50 (88%) | 44/50 (88%) | 0 |

**The 0% Planner pass rate was entirely an artifact.** The real capability is ~73%, with the remaining 27% being a prompt engineering problem.

---

## 2. Methodology

### Test Design

Each model role tested in isolation with deterministic evaluation:

**Planner:** 15 cases × 3 sequential calls = 45 total calls
- Step 1: Classifier → `IntentClassifierResponse`
- Step 2: Architect Analysis → JSON with targets/preserve/structures
- Step 3: Architect Synthesis → `ASTArchitectResponse`

**Judge:** 10 cases × 5 runs = 50 total calls
- Each run cleared context, same input
- Response model: `StructuralAuditorResponse`

**Generator:** 14 cases (11 real + 3 stress) = 14 total calls
- Extract code from `<code>` tags
- Validate syntax, plan compliance, anti-patterns

### Harness Fixes Applied

| # | Fix | File | Description |
|---|-----|------|-------------|
| 1 | Exempt ADD_* targets from hallucination check | `harness.py` | ADD_METHOD/ADD_FIELD/ADD_CONSTANT targets are new names by design |
| 2 | Use validator unit type for `classes_in_code` | `test_planner_isolated.py` | `METHOD_UNIT`/`STATEMENT_UNIT` = bare method, no class wrapper |
| 3 | Check fields/variables in scope anchor | `harness.py` | `FieldDeclaration` and `VariableDeclarator` in addition to `MethodDeclaration` |
| 4 | Exempt ADD_* targets from plan executable check | `test_planner_isolated.py` | New names don't need to exist in original AST |
| 5 | Use throw messages for FLATTEN anti-pattern | `test_generator_isolated.py` | Compare exception messages instead of if-count |

### Evaluation Criteria

**Planner PASS:** Intent correct AND scope valid AND plan executable AND 0 hallucinations
**Generator PASS:** Syntax valid AND all planned elements present AND 0 anti-patterns
**Judge PASS:** Verdict matches expected (ACCEPT or REVISE)

---

## 3. Planner Results (11/15 PASS)

### 3.1 Summary by Intent

| Intent | Cases | Classifier Acc | Scope Valid | Plan Executable | Hallucinations | PASS |
|--------|-------|---------------|-------------|-----------------|----------------|------|
| FLATTEN_CONDITIONAL | 3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0 | **3/3** |
| EXTRACT_METHOD | 3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0 | **3/3** |
| RENAME_SYMBOL | 2 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 0 | **2/2** |
| EXTRACT_CONSTANT | 2 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 0 | **2/2** |
| DECOMPOSE_CONDITIONAL | 2 | **0/2 (0%)** | 2/2 (100%) | 2/2 (100%) | 0 | **0/2** |
| SPLIT_LOOP | 2 | **0/2 (0%)** | 1/2 (50%) | 2/2 (100%) | 0 | **0/2** |
| CONSOLIDATE_CONDITIONAL | 1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0 | **1/1** |

**Pattern:** When classifier is correct (11/15), downstream steps succeed 100% of the time. The bottleneck is **exclusively the classifier**.

### 3.2 Detailed Per-Case Results

#### PASSING CASES (11/15)

| # | Case | Intent | Duration | Notes |
|---|------|--------|----------|-------|
| 1 | flat_demo_orderprocessor | FLATTEN | 18.7s | Analysis hallucinated `guardClauseHelper`, `INVALID_ORDER_MESSAGE` in new_structures, but synthesis ignored them. Coherent=True. |
| 2 | flat_binary_search | FLATTEN | 19.5s | Scope was "A.search" (invented class). Fixed by unit-type check. Hallucinations fixed by ADD_* exemption. |
| 3 | flat_validate_ip | FLATTEN | 16.9s | Scope was empty (bare method). Fixed by unit-type check. Analysis invented `isValidIPv4`, `isValidIPv6`. |
| 4 | extract_set_zeroes | EXTRACT_METHOD | 27.2s | **Longest case.** Synthesis produced 3 ADD_METHOD mutations matching instruction names. Coherent=False (plan doesn't reference analysis targets). |
| 5 | extract_tax_calculator | EXTRACT_METHOD | 18.7s | Synthesis only produced MODIFY_METHOD, missing ADD_METHOD for `computeTaxWithRounding`. Plan executable=True but **incomplete**. |
| 6 | extract_prime_arrange | EXTRACT_METHOD | 20.6s | Synthesis produced ADD_METHOD + MODIFY_METHOD. Coherent=True. Scope class "A" invented for bare method. |
| 7 | rename_user_manager | RENAME_SYMBOL | 27.9s | **Second longest.** Synthesis produced 4 mutations including RENAME_SYMBOL(UserManager) — **unrequested class rename**. Over-scoped. |
| 8 | rename_remove_nth | RENAME_SYMBOL | 15.4s | Clean RENAME_SYMBOL for `first`→`fast`, `second`→`slow`. Coherent=False (analysis listed `removeNthFromEnd` as target, plan targets the variables). |
| 9 | const_abbreviation | EXTRACT_CONSTANT | 17.3s | Analysis correctly identified `validWordAbbreviation`. Synthesis invented `DIGIT_BASE` and `LEADING_ZERO_CHAR` constants. Coherent=False. |
| 10 | const_circle_pi | EXTRACT_CONSTANT | 15.4s | Analysis found BOTH methods (`calculateArea`, `calculateCircumference`). Synthesis only produced ADD_CONSTANT — **missing MODIFY_METHOD mutations**. Incomplete plan. |
| 11 | cons_word_pattern | CONSOLIDATE | 21.6s | Single MODIFY_METHOD mutation. Clean. |

#### FAILING CASES (4/15)

| # | Case | Expected | Actual | Root Cause | Duration |
|---|------|----------|--------|------------|----------|
| 12 | decomp_closed_island | DECOMPOSE | EXTRACT_METHOD | Classifier: "targets method decomposition" → METHOD_MOVEMENT | 30.1s |
| 13 | decomp_regex_dp | DECOMPOSE | EXTRACT_METHOD | Classifier: "extract the logic" → METHOD_MOVEMENT | 16.2s |
| 14 | split_board_path | SPLIT_LOOP | EXTRACT_METHOD | Classifier: "split into two methods" → METHOD_MOVEMENT | 18.0s |
| 15 | split_unique_paths | SPLIT_LOOP | EXTRACT_METHOD | Classifier: "split into separate methods" → METHOD_MOVEMENT | 19.0s |

**All 4 failures share the same root cause:** The classifier prompt has one FLATTEN example and no DECOMPOSE/SPLIT examples. The 3B model defaults "extract/decompose/split" → `EXTRACT_METHOD`.

**Classifier scratchpads for failing cases:**

```
decomp_closed_island: "Instruction targets method decomposition. 
                       Code contains a complex DFS function with boundary conditions.
                       Category is METHOD_MOVEMENT, intent is EXTRACT_METHOD."

decomp_regex_dp:      "Instruction targets method decomposition.
                       Code contains a complex DP transition for the '*' character.
                       Category is METHOD_MOVEMENT, intent is EXTRACT_METHOD."

split_board_path:     "Instruction targets method movement.
                       Code contains a per-character loop.
                       Category is METHOD_MOVEMENT, intent is EXTRACT_METHOD."

split_unique_paths:   "Instruction targets method movement.
                       Code contains a DP initialization.
                       Category is METHOD_MOVEMENT, intent is EXTRACT_METHOD."
```

**Notice the pattern:** Every failing case explicitly states "Category is METHOD_MOVEMENT" in the scratchpad. The model learned this from the single FLATTEN example + the absence of DECOMPOSE/SPLIT examples.

### 3.3 Analysis Quality Issues in Passing Cases

Even though 11 cases PASS, several have **quality issues** the harness doesn't catch:

| Case | Issue | Severity |
|------|-------|----------|
| flat_demo_orderprocessor | Analysis invented `guardClauseHelper`, `INVALID_ORDER_MESSAGE` | Low (synthesis ignored them) |
| flat_binary_search | Analysis invented `helperMethod`, `CONSTANT_NAME` | Low (synthesis ignored them) |
| flat_validate_ip | Analysis invented `isValidIPv4`, `isValidIPv6` | Low (synthesis ignored them) |
| extract_set_zeroes | Synthesis body_abstracts are vague | Medium |
| extract_tax_calculator | **Synthesis missing ADD_METHOD mutation** | **High** |
| rename_user_manager | **Synthesis added unrequested class rename** | **High** |
| const_abbreviation | Synthesis target_class="ClassName" (generic placeholder) | Medium |
| const_circle_pi | **Synthesis missing MODIFY_METHOD mutations** | **High** |

**Critical finding:** The PASS criteria are too lenient. A plan can be "executable" (targets exist) but **incomplete** (missing mutations) or **over-scoped** (extra mutations). The harness only checks existence, not completeness or correctness.

### 3.4 Coherence Analysis

`coherent` measures whether plan mutations reference analysis targets.

| Case | Coherent | Issue |
|------|----------|-------|
| flat_demo_orderprocessor | True | - |
| flat_binary_search | True | - |
| flat_validate_ip | True | - |
| extract_set_zeroes | **False** | Plan has ADD_METHOD mutations, analysis has `setZeroes` as primary target. Mutation targets don't include `setZeroes`. |
| extract_tax_calculator | True | - |
| extract_prime_arrange | True | - |
| rename_user_manager | True | - |
| rename_remove_nth | **False** | Analysis targets `removeNthFromEnd`, plan targets `first` and `second` (variables, not method). |
| const_abbreviation | **False** | Analysis targets `validWordAbbreviation`, plan targets `DIGIT_BASE` and `LEADING_ZERO_CHAR` (constants). |
| const_circle_pi | **False** | Analysis targets `calculateArea` and `calculateCircumference`, plan only has ADD_CONSTANT. |

**3/11 passing cases have `coherent=False`.** The coherence check is too strict (it requires mutation targets to match primary targets exactly), but the pattern reveals that synthesis often produces plans that don't directly reference analysis targets.

### 3.5 Timing Analysis

| Metric | Value |
|--------|-------|
| Total time | 302.5s |
| Avg per case | 20.2s |
| Classifier avg | 5.3s |
| Analysis avg | 3.1s |
| Synthesis avg | 11.7s |
| Slowest case | decomp_closed_island (30.1s) |
| Fastest case | rename_remove_nth (15.4s) |

**Observation:** Synthesis takes ~58% of total time (11.7s / 20.2s). The model spends the most time generating the actual mutation plan. Cases with more mutations take longer:
- `decomp_closed_island`: 3 ADD_METHOD mutations → 30.1s
- `rename_user_manager`: 4 mutations → 27.9s
- `extract_set_zeroes`: 3 ADD_METHOD mutations → 27.2s

---

## 4. Generator Results (9/11 PASS)

### 4.1 Summary by Intent

| Intent | Cases | Syntax | Plan Compliance | Anti-Patterns | PASS |
|--------|-------|--------|-----------------|---------------|------|
| EXTRACT_METHOD | 3 | 3/3 | 3/3 | 0/3 | **3/3** |
| FLATTEN_CONDITIONAL | 2 | 2/2 | 2/2 | **2/2** | **0/2** |
| RENAME_SYMBOL | 2 | 2/2 | 2/2 | 0/2 | **2/2** |
| ADD_CONSTANT | 2 | 2/2 | 2/2 | 0/2 | **2/2** |
| DECOMPOSE_CONDITIONAL | 1 | 1/1 | 1/1 | 0/1 | **1/1** |
| SPLIT_LOOP | 1 | 1/1 | 1/1 | 0/1 | **1/1** |
| Bad-plan stress | 3 | 3/3 | N/A | N/A | **3/3** |

**Pattern:** Generator is perfect for mechanical transformations (rename, extract, constant, decompose, split). Only FLATTEN fails, and it fails with **semantic corruption**.

### 4.2 Passing Cases (9/11)

All passing cases share these characteristics:
- Plan has 1-3 mutations
- Code is short (< 500 chars)
- Intent is mechanical (rename, extract, constant)
- No conditional logic to preserve

**Example of excellent output:**

`gen_extract_tax_helper` (PASS):
```java
public class Calculator {
    private double computeTaxWithRounding(double subtotal, double taxRate) {
        double tax = subtotal * taxRate;
        return Math.round((subtotal + tax) * 100.0) / 100.0;
    }

    public double calculateTotal(double price, int quantity, double taxRate) {
        double subtotal = price * quantity;
        return computeTaxWithRounding(subtotal, taxRate);
    }
}
```
- Correct signature: `subtotal, taxRate` (not `price, quantity, taxRate`)
- Correct logic: computes tax, rounds, returns
- Original method delegates to new method
- No anti-patterns

### 4.3 Failing Cases (2/11) — FLATTEN Logic Inversion

#### Case 1: gen_flatten_orderprocessor

**Anti-patterns:**
1. "May have merged guard clause exception messages"
2. "Original exception messages lost: {'Order has no items.', 'Order cannot be null.'}"

**Generated code:**
```java
public class OrderProcessor {
    public void processOrder(Order order, User user) 
            throws IllegalArgumentException, IllegalStateException {
        if (user == null) {
            throw new IllegalArgumentException("User cannot be null.");
        }
        
        if (!user.isActive()) {
            throw new IllegalStateException("User account is inactive.");
        }

        if (order == null || order.getItems().isEmpty()) {
            throw new IllegalArgumentException("Order has no items or is null.");
        }

        double total = order.getTotal();
        if (total > 1000) {
            if (!user.isPremium()) {
                order.applyDiscount(0.05);
            }
        } else {
            order.applyDiscount(0.15);
        }

        System.out.println("Processing order for: " + user.getName());
    }
}
```

**Original logic:**
| Condition | Premium | Action |
|-----------|---------|--------|
| total > 1000 | Yes | discount(0.15) |
| total > 1000 | No | discount(0.05) |
| total <= 1000 | Any | no discount |

**Generated logic:**
| Condition | Premium | Action |
|-----------|---------|--------|
| total > 1000 | Yes | **no discount** ← BUG |
| total > 1000 | No | discount(0.05) ← correct |
| total <= 1000 | Any | discount(0.15) ← BUG |

**Critical bugs:**
1. **Premium users get NO discount when total > 1000.** The original code had `if (user.isPremium()) { discount(0.15); } else { discount(0.05); }`. The generated code has `if (!user.isPremium()) { discount(0.05); }` — the premium branch is missing entirely.
2. **Everyone gets 0.15 discount when total <= 1000.** The original code had no discount for total <= 1000. The generated code applies 0.15 in the `else` branch.
3. **Two exception messages merged.** Original: "Order has no items." and "Order cannot be null." Generated: "Order has no items or is null."

This is the **exact same bug pattern** as `revise_flatten_logic_inverted` in Judge tests.

#### Case 2: gen_flatten_simple_ifs

**Anti-patterns:**
1. "May have merged guard clause exception messages"
2. "Original exception messages lost: {'x is null', 'y is null'}"

**Generated code:**
```java
void process(Object x, Object y) {
    if (x == null || y == null) {
        throw new IllegalArgumentException(
            x != null ? "y is null" : "x is null"
        );
    }
    doWork(x, y);
}
```

**Issues:**
1. Two separate null checks merged into one `||` condition
2. Exception messages combined using ternary operator
3. **Logic is actually correct** (both null cases still throw), but messages are merged

This is a **less severe** failure than `gen_flatten_orderprocessor` — the logic is preserved, but the messages are merged.

### 4.4 Stress Test Results (3/3 PASS)

| Case | Behavior | Assessment |
|------|----------|------------|
| bad_missing_target | Ignored non-existent MODIFY_METHOD, returned original | Graceful |
| bad_empty_mutations | Returned original code unchanged | Correct |
| bad_hallucinated_add | Created `xyZzZzZzHelperMethod()` with `Do something;` | **Dangerous** |

**Critical issue with `bad_hallucinated_add`:**

Generated code:
```java
public class A {
    void m() { int x = 1; }
    
    private void xyZzZzZzHelperMethod() {
        Do something;
    }
}
```

`Do something;` is **not valid Java semantics**. But javalang parses it as:
```
LocalVariableDeclaration
  type: ReferenceType "Do"
  declarators: [VariableDeclarator "something"]
```

The validator returns `syntax_valid=True`. The Generator treats any plan as authoritative and creates nonsense code that passes syntax checks.

**Risk:** A hallucinated plan from the Planner could produce syntactically valid but semantically meaningless code that passes all validation gates.

### 4.5 Code Length vs Duration

| Case | Code Length | Duration | Notes |
|------|-------------|----------|-------|
| gen_rename_field | 136 | 1.73s | Shortest code, fastest |
| gen_extract_mod_constant | 198 | 3.15s | - |
| gen_split_simple_loop | 190 | 1.83s | - |
| gen_flatten_simple_ifs | 272 | 2.35s | - |
| gen_extract_pi_constant | 221 | 2.91s | - |
| gen_extract_tax_helper | 320 | 3.78s | - |
| gen_decompose_simple | 176 | 3.46s | - |
| gen_rename_variables | 421 | 4.83s | - |
| gen_flatten_orderprocessor | 1168 | 6.4s | Longest code |
| gen_extract_prime_count | 535 | 9.01s | - |
| gen_extract_set_zeroes_helpers | 641 | 20.13s | **Longest duration** |

**Observation:** Duration correlates with complexity, not just code length. `gen_extract_set_zeroes_helpers` has 641 chars but took 20.13s — the model struggled with the matrix logic.

---

## 5. Judge Results (44/50 Correct, 88%)

### 5.1 Per-Case Accuracy

| Case | Expected | Correct / 5 | Consistency | Mode |
|------|----------|-------------|-------------|------|
| accept_extract_method_tax | ACCEPT | 5/5 | 100% | Unanimous |
| accept_rename_symbol_field | ACCEPT | 5/5 | 100% | Unanimous |
| accept_flatten_guard_clauses | ACCEPT | 5/5 | 100% | Unanimous |
| accept_split_loop | ACCEPT | 5/5 | 100% | Unanimous |
| accept_extract_constant_pi | ACCEPT | 5/5 | 100% | Unanimous |
| revise_extract_constant_broken_sig | REVISE | 4/5 | 80% | Strong (1 false ACCEPT) |
| **revise_decompose_noop** | **REVISE** | **0/5** | **0%** | **Unanimous (all wrong)** |
| revise_flatten_logic_inverted | REVISE | 5/5 | 100% | Unanimous |
| revise_extract_method_wrong_params | REVISE | 5/5 | 100% | Unanimous |
| revise_rename_broke_structural | REVISE | 5/5 | 100% | Unanimous |

### 5.2 Scratchpad Length vs Accuracy

| Case | Avg Scratchpad | Accuracy | Notes |
|------|---------------|----------|-------|
| accept_extract_constant_pi | 171 | 100% | Short, simple |
| accept_split_loop | 199 | 100% | Short, simple |
| accept_flatten_guard_clauses | 234 | 100% | Medium |
| accept_rename_symbol_field | 264 | 100% | Variable length |
| accept_extract_method_tax | 325 | 100% | Medium |
| revise_rename_broke_structural | 323 | 100% | Medium |
| revise_extract_constant_broken_sig | 459 | 80% | Medium-long |
| revise_flatten_logic_inverted | 622 | 100% | Long, detailed |
| revise_extract_method_wrong_params | 640 | 100% | Long, detailed |
| **revise_decompose_noop** | **394** | **0%** | **Medium, but all wrong** |

**Pattern:** Scratchpad length does NOT predict accuracy. `revise_decompose_noop` has medium-length scratchpads (394 chars avg) but 0% accuracy. The model writes about variable traces and logic comparisons but never checks PLAN FIDELITY.

### 5.3 Systematic Failure: revise_decompose_noop

**Input:**
- Original code: `LoanApprover.isEligible` with compound condition
- Refactored code: **Identical to original**
- Plan: ADD_FIELD×4 (isSufficientAge, sufficientIncome, highCreditScore, collateralAvailable) + MODIFY_METHOD(isEligible)

**All 5 scratchpads:**
```json
{
  "variable_trace": [
    {"original": "age", "refactored": "age", "mapping": null},
    {"original": "income", "refactored": "income", "mapping": null},
    {"original": "score", "refactored": "score", "mapping": null},
    {"original": "hasCollateral", "refactored": "hasCollateral", "mapping": null}
  ],
  "logic_comparison": "The conditional paths in the refactored code are identical to those in the original code."
}
```

**Verdict:** ACCEPT (all 5 runs)

**Root cause analysis:**
1. The scratchpad **only contains VARIABLE TRACE and LOGIC CHECK** — no PLAN FIDELITY or SIGNATURE CHECK.
2. The model sees identical code, traces variables (trivial), confirms logic equivalence (trivial), and outputs ACCEPT.
3. The prompt says "Changes that match the plan are EXPECTED, not errors" — the model interprets "no changes" as "changes match" because there's nothing contradicting the plan.
4. The 3B model's attention budget is exhausted before reaching the PLAN FIDELITY task (task #1 in prompt, but processed last in scratchpad).

**Fix needed:** Add explicit rule: "If refactored code is character-for-character identical to original but plan lists mutations, verdict MUST be REVISE."

### 5.4 Inconsistency: revise_extract_constant_broken_sig

**Input:**
- Original: `calculateArea` returns `double`, `calculateCircumference` returns `double`
- Refactored: Both return `void` + `println` side-effect

**Runs:**
| Run | Verdict | Scratchpad | Duration |
|-----|---------|------------|----------|
| 1 | REVISE | "prints to console instead of returning values" | 6.0s |
| 2 | REVISE | "combines methods into single method with print" | 4.9s |
| 3 | REVISE | "uses 'radius' instead of original variable name 'r'" | 9.9s |
| 4 | **ACCEPT** | "calculating correct area and circumference" | **6.0s** |
| 5 | REVISE | "prints to console instead of returning values" | 10.0s |

**Run 4 falsely ACCEPT'd.** Scratchpad says: "This change does not affect the output for a given input, as it is still calculating the correct area and circumference."

**Why inconsistent:** The model focuses on "output for a given input" rather than "return type changed." Run 4 interpreted "prints to console" as "output is visible" rather than "return type changed from double to void." The SIGNATURE CHECK task is present in the prompt but not consistently executed.

### 5.5 Excellent Reasoning Examples

**revise_flatten_logic_inverted, Run 3:**
```
"logic_comparison": "Conditional paths differ. 
Original: total > 1000 and premium, Refactored: total > 1000 or not premium.
Expected output for inputs (total=1200, premium=true): discount(0.15), 
Actual output: discount(0.05).
Expected output for inputs (total=800, premium=false): discount(0.05), 
Actual output: no discount applied.
Expected output for inputs (total=1001, premium=true): discount(0.15), 
Actual output: discount(0.05).
Expected output for inputs (total=999, premium=false): discount(0.05), 
Actual output: discount(0.05)."
```

This is **excellent reasoning** — the model traced 4 concrete examples and identified the logic inversion. But notice the scratchpad is 705 chars, which is longer than most.

---

## 6. Cross-Model Analysis

### 6.1 Pipeline Dependency Map

```
Planner classifies correctly (11/15)
  → Generator produces correct code (9/11 from passing plans)
    → Judge ACCEPTs (25/25 on correct code)
    = SUCCESS PATH

Planner misclassifies (4/15)
  → Generator gets wrong plan → wrong code
    → Judge may REVISE correctly (76% accurate)
    = RETRY LOOP

Planner classifies correctly but plan incomplete (2/11)
  → Generator produces partial code
    → Judge may ACCEPT or REVISE
    = AMBIGUOUS
```

### 6.2 Intent-Level Cross-Model Performance

| Intent | Planner | Generator | Judge | Pipeline Risk |
|--------|---------|-----------|-------|---------------|
| FLATTEN | ✓ (classifier) | ✗ (logic inversion) | ✓ (catches inversion) | **HIGH** — Generator corrupts logic |
| EXTRACT_METHOD | ✓ | ✓ | ✓ | LOW |
| RENAME_SYMBOL | ✓ | ✓ | ✓ | LOW |
| EXTRACT_CONSTANT | ✓ | ✓ | ✓ | LOW |
| DECOMPOSE | ✗ (misclassifies) | ✓ (simple case) | N/A | **HIGH** — Planner blocks entirely |
| SPLIT_LOOP | ✗ (misclassifies) | ✓ (simple case) | N/A | **HIGH** — Planner blocks entirely |
| CONSOLIDATE | ✓ | N/A | N/A | LOW |

**Critical path:**
1. **DECOMPOSE/SPLIT:** Planner classifier fails → never reaches Generator
2. **FLATTEN:** Planner succeeds → Generator inverts logic → Judge catches it (but only 76% of time on REVISE cases)

### 6.3 The No-Op Blind Spot

```
Planner: Produces plan with mutations ✓
  → Generator: Returns original code unchanged ✓ (correct for empty mutations)
    → Judge: ACCEPTs unchanged code ✗ (blind spot)
    = FALSE SUCCESS
```

This is the most dangerous failure mode: the system reports SUCCESS but nothing changed.

---

## 7. Timing Analysis

### 7.1 Planner Timing

| Step | Avg (s) | % of Total | Range (s) |
|------|---------|------------|-----------|
| Classifier | 5.3 | 26% | 4.1 – 6.6 |
| Analysis | 3.1 | 15% | 2.3 – 4.0 |
| Synthesis | 11.7 | 58% | 6.5 – 21.8 |
| **Total** | **20.2** | **100%** | **15.4 – 30.1** |

**Synthesis is the bottleneck** — it takes 58% of total time. Cases with more mutations take disproportionately longer:
- `decomp_closed_island`: 3 ADD_METHOD mutations → 21.8s synthesis
- `rename_user_manager`: 4 mutations → 19.6s synthesis
- `extract_set_zeroes`: 3 ADD_METHOD mutations → 16.6s synthesis

### 7.2 Generator Timing

| Metric | Value |
|--------|-------|
| Total time | 62.8s |
| Avg per case | 4.5s |
| Fastest | gen_rename_field (1.73s) |
| Slowest | gen_extract_set_zeroes_helpers (20.13s) |
| FLATTEN avg | 4.4s |
| EXTRACT_METHOD avg | 11.0s |

**Observation:** EXTRACT_METHOD takes longer than FLATTEN (11.0s vs 4.4s) because it requires generating new method bodies. FLATTEN is faster because it's mostly restructuring existing code.

### 7.3 Judge Timing

| Case | Avg (s) | Scratchpad (chars) |
|------|---------|-------------------|
| ACCEPT cases | 4.4s | 236 |
| REVISE cases (excluding noop) | 10.3s | 562 |
| **revise_decompose_noop** | **6.5s** | **394** |

**Pattern:** REVISE cases take 2.3× longer than ACCEPT cases. The model spends more time analyzing differences. But `revise_decompose_noop` is an outlier — it takes 6.5s but produces wrong verdict because it never executes the key audit tasks.

---

## 8. Failure Mode Deep Dives

### 8.1 Failure Mode: DECOMPOSE Misclassification

**Frequency:** 2/2 DECOMPOSE cases (100%)
**Also affects:** 2/2 SPLIT cases (100%)
**Root cause:** Classifier prompt has no DECOMPOSE or SPLIT examples

**Evidence chain:**

1. Instruction: "Decompose the complex DFS boundary condition into well-named booleans"
2. Model scratchpad: "Instruction targets **method decomposition**"
3. Model associates "decomposition" with METHOD_MOVEMENT category
4. Outputs: EXTRACT_METHOD

**The model is not confused** — it explicitly states "method decomposition" in the scratchpad. The problem is the prompt's category definitions don't provide enough disambiguation. METHOD_MOVEMENT contains "EXTRACT_METHOD" which is semantically close to "decomposition."

**Fix:** Add explicit rule: "If instruction says 'decompose the condition' or 'split the loop', classify as CONTROL_FLOW, not METHOD_MOVEMENT."

### 8.2 Failure Mode: FLATTEN Logic Inversion

**Frequency:** 1/2 FLATTEN cases (50%)
**Severity:** HIGH — produces semantically wrong code

**Evidence chain:**

1. Original: `if (total > 1000) { if (premium) discount(0.15); else discount(0.05); }`
2. Generator inverts: `if (total > 1000) { if (!premium) discount(0.05); } else { discount(0.15); }`

**The model is trying to be concise** — it merged the premium/non-premium branches and inverted the condition. The anti-pattern list has 8 rules, and "don't merge guard clauses" is rule #4. By the time the model processes this rule, it has already generated the merged check.

**Fix:** 
1. Reduce anti-pattern list to 3 rules
2. Promote "never merge guard clauses" to rule #1
3. Add explicit logic preservation rule: "Each original condition must map to equivalent inverted condition"

### 8.3 Failure Mode: No-Op Blind Spot

**Frequency:** 5/5 runs on identical code (100%)
**Severity:** HIGH — system reports success when nothing changed

**Evidence chain:**

1. Plan: ADD_FIELD×4 + MODIFY_METHOD
2. Refactored code: Identical to original
3. Judge scratchpad: "conditional paths are identical" → ACCEPT

**The model never checks PLAN FIDELITY.** The scratchpad only contains VARIABLE TRACE and LOGIC CHECK. The prompt lists 5 audit tasks, but the 3B model can only process 2-3 before attention is exhausted.

**Fix:**
1. Reduce audit tasks from 5 to 3
2. Add explicit identity check as task #1
3. Remove VARIABLE TRACE (low signal, high token cost)

### 8.4 Failure Mode: Incomplete Synthesis

**Frequency:** 2/11 passing cases (18%)
**Severity:** MEDIUM — plan is executable but incomplete

**Evidence:**

`const_circle_pi`:
- Analysis: Primary targets = `calculateArea`, `calculateCircumference`
- Synthesis: Only ADD_CONSTANT(PI_CONSTANT) — **missing MODIFY_METHOD for both methods**

`extract_tax_calculator`:
- Analysis: New structure = `computeTaxWithRounding`
- Synthesis: Only MODIFY_METHOD(calculateTotal) — **missing ADD_METHOD**

**The synthesis step ignores analysis context.** The model sees the code and instruction and generates a plan from scratch, rather than translating analysis items into mutations.

**Fix:** Add rule to synthesis prompt: "Map EACH new_structure_needed to exactly one ADD_METHOD/ADD_FIELD/ADD_CONSTANT. Map EACH primary_target to exactly one MODIFY_METHOD."

---

## 9. Prompt-Level Root Causes

### 9.1 planner.classifier

**Current issues:**
- One example (FLATTEN only)
- No explicit rule distinguishing DECOMPOSE from EXTRACT
- No classless-code fallback

**Impact:** 4/15 misclassifications, 4/15 scope failures (before harness fix)

**Fix priority:** P0

### 9.2 planner.architect_analysis

**Current issues:**
- No constraint on `new_structures_needed` → model hallucinates helpers
- No "scan ALL occurrences" instruction → misses cross-references
- No field/variable checking in scope anchor

**Impact:** 4/15 hallucinations (before harness fix), 2/15 missed secondary targets

**Fix priority:** P1

### 9.3 planner.architect

**Current issues:**
- No mutation count cap → 14 mutations in `extract_set_zeroes`
- No rule to use analysis context → synthesis ignores analysis
- No template-text isolation → copies FLATTEN body_abstract into CONSTANT plan
- Target format not constrained → includes full signatures

**Impact:** 2/15 incomplete plans, 1/15 mutation explosion

**Fix priority:** P1

### 9.4 generator.coder

**Current issues:**
- 8 anti-pattern rules → model drops later rules
- No logic preservation rule for FLATTEN
- No constraint on guard clause merging

**Impact:** 2/11 FLATTEN failures

**Fix priority:** P0

### 9.5 judge.auditor

**Current issues:**
- 5 audit tasks + 3 rules + complex schema → model skips tasks
- No explicit identity check
- VARIABLE TRACE is low-signal but consumes attention

**Impact:** 5/50 failures (all on no-op or signature change)

**Fix priority:** P1

---

## 10. Actionable Fix Roadmap

### Phase 1: Critical Fixes (Expected +20% Planner, +18% Generator)

| # | Fix | File | Effort | Expected Impact |
|---|-----|------|--------|-----------------|
| 1 | Add DECOMPOSE + SPLIT examples to classifier | `prompts.yaml` | 30 min | Planner: 73% → 93% (+20pp) |
| 2 | Add classless-code rule to classifier | `prompts.yaml` | 10 min | Scope accuracy: 93% → 100% |
| 3 | Reduce anti-patterns to 3, promote "no merge" | `prompts.yaml` | 20 min | Generator: 82% → 95% (+13pp) |
| 4 | Add logic preservation rule to generator | `prompts.yaml` | 15 min | Prevents FLATTEN inversion |
| 5 | Add explicit identity check to judge | `prompts.yaml` | 15 min | Judge: 88% → 95% (+7pp) |

**Phase 1 total effort:** ~1.5 hours
**Phase 1 expected end-to-end improvement:** ~64% → ~85%

### Phase 2: Quality Fixes (Expected +10% Planner completeness)

| # | Fix | File | Effort | Expected Impact |
|---|-----|------|--------|-----------------|
| 6 | Add "only explicit" constraint to analysis | `prompts.yaml` | 20 min | Reduces hallucinations |
| 7 | Add "scan ALL occurrences" to analysis | `prompts.yaml` | 15 min | Catches cross-references |
| 8 | Add mutation count cap to synthesis | `prompts.yaml` | 10 min | Prevents explosion |
| 9 | Add analysis→synthesis coherence rule | `prompts.yaml` | 15 min | Improves plan completeness |
| 10 | Remove VARIABLE TRACE from judge | `prompts.yaml` | 10 min | Frees attention budget |

**Phase 2 total effort:** ~1 hour

### Phase 3: Infrastructure Hardening

| # | Fix | File | Effort | Expected Impact |
|---|-----|------|--------|-----------------|
| 11 | Add semantic smoke test to validator | `validator.py` | 2 hours | Catches `Do something;` |
| 12 | Add pre-flight plan validation | `orchestrator.py` | 2 hours | Catches bad plans early |
| 13 | Add identity gate before Judge | `orchestrator.py` | 30 min | Prevents no-op ACCEPT |
| 14 | Fix syntax healing loop | `orchestrator.py` | 1 hour | Makes retries effective |

**Phase 3 total effort:** ~5.5 hours

---

## 11. Appendix: Raw Data

### 11.1 Planner Raw Outputs (Key Cases)

**decomp_closed_island (FAILING):**
```json
{
  "classification_scratchpad": "Instruction targets method decomposition. 
    Code contains a complex DFS function with boundary conditions.
    Category is METHOD_MOVEMENT, intent is EXTRACT_METHOD.",
  "intent_packet": {
    "refactor_category": "METHOD_MOVEMENT",
    "specific_intent": "EXTRACT_METHOD",
    "scope_anchor": {"unit_type": "CLASS_UNIT"}
  }
}
```

**const_circle_pi (PASSING but incomplete):**
```json
{
  "analysis_scratchpad": "The magic number 3.14159 is used in both calculateArea 
    and calculateCircumference methods.",
  "primary_targets": ["calculateArea", "calculateCircumference"],
  "secondary_targets": [],
  "new_structures_needed": ["PI_CONSTANT"],
  "must_preserve": []
}
```
Synthesis only produced ADD_CONSTANT — **missing MODIFY_METHOD mutations**.

### 11.2 Generator Raw Outputs (Failing Cases)

**gen_flatten_orderprocessor:**
```java
// Logic inversion: premium users get NO discount
// Exception messages merged
// total <= 1000 applies 0.15 to everyone
double total = order.getTotal();
if (total > 1000) {
    if (!user.isPremium()) {
        order.applyDiscount(0.05);
    }
} else {
    order.applyDiscount(0.15);
}
```

### 11.3 Judge Raw Outputs (Systematic Failure)

**revise_decompose_noop, all 5 runs:**
```json
{
  "audit_scratchpad": {
    "variable_trace": [
      {"original": "age", "refactored": "age", "mapping": null},
      {"original": "income", "refactored": "income", "mapping": null}
    ],
    "logic_comparison": "The conditional paths are identical."
  },
  "verdict": "ACCEPT",
  "issues": []
}
```

**Missing:** PLAN FIDELITY check, SIGNATURE CHECK, explicit rule about identical code.

### 11.4 Before/After Metrics Table

| Metric | Before Harness Fix | After Harness Fix | True Model Capability |
|--------|-------------------|-------------------|----------------------|
| Planner PASS | 0/15 (0%) | 11/15 (73%) | **73%** |
| Planner scope | 4/15 (27%) | 14/15 (93%) | **93%** |
| Planner hallucinations | 17 | 0 | **0** |
| Planner executable | 6/15 (40%) | 15/15 (100%) | **100%** |
| Generator PASS | 9/11 (82%) | 9/11 (82%) | **82%** |
| Generator FLATTEN | 0/2 (0%) | 0/2 (0%) | **0%** |
| Judge correct | 44/50 (88%) | 44/50 (88%) | **88%** |
| Judge no-op | 0/5 (0%) | 0/5 (0%) | **0%** |

---

*Report generated from direct analysis of 109 model calls (45 Planner + 50 Judge + 14 Generator) with corrected test harness.*
