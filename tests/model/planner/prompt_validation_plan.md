# Prompt Validation Test Suite — Implementation Plan

**Directory:** `tests/validation/`  
**Models:** Qwen2.5-Coder-3B (Planner)  
**Context:** 6144 tokens  
**Goal:** Validate new classifier prompt, dynamic analysis guidance, architect prompt + synthesis guidance before wiring into orchestrator.

---

## Prerequisites

- [x] New classifier prompt with intent definitions (`prompts.yaml planner.classifier`)
- [x] `analysis_guidance` dict — 12 intents (`prompts.yaml planner.analysis_guidance`)
- [x] Non-overfitting architect base prompt (`prompts.yaml planner.architect`)
- [x] `synthesis_guidance` dict — 12 intents (`prompts.yaml planner.synthesis_guidance`)
- [x] YAML valid

---

## Test Structure

```
tests/validation/
├── prompt_validation_plan.md          # This file
├── test_classifier_new.py             # Script 1: 10 cases, classifier only
├── test_analysis_new.py               # Script 2: 8 cases, analysis with guidance
├── test_architect_new.py              # Script 3: 8 cases, architect with guidance
└── test_planner_chain_new.py          # Script 4: 10 cases, full classifier → analysis → architect
```

No orchestrator dependency. All scripts call `ModelTestHarness` directly and inject guidance inline.

---

### Script 1: `test_classifier_new.py` — Classifier Isolated

**10 test cases. 5 existing + 5 new.** Tests intent-definition-based classification.

**Existing cases (regression check):**

| # | Source | Expected |
|---|--------|----------|
| 1 | flat_demo_orderprocessor (1168 chars) | FLATTEN_CONDITIONAL |
| 2 | extract_set_zeroes (641 chars) | EXTRACT_METHOD |
| 3 | rename_remove_nth (421 chars) | RENAME_SYMBOL |
| 4 | const_circle_pi (221 chars) | EXTRACT_CONSTANT |
| 5 | decomp_closed_island (770 chars) | DECOMPOSE_CONDITIONAL |

**New cases (from polish file + custom code):**

| # | Source | Instruction | Expected |
|---|--------|-------------|----------|
| 6 | polish idx=275 (canWinNim, 70 chars) | "Remove the method and inline the return expression" | INLINE_METHOD |
| 7 | polish idx=2174 (minOperations, 470 chars) | "Separate the counting loop from the checking loop" | SPLIT_LOOP |
| 8 | polish idx=152 (findMin, 310 chars) | "Replace the while loop with stream operations" | REPLACE_LOOP_WITH_PIPELINE |
| 9 | Custom code (variable extraction) | "Extract the expression n * n into a local variable called squared" | EXTRACT_VARIABLE |
| 10 | Custom code (flag removal) | "Remove the found flag variable and use early return instead" | REMOVE_CONTROL_FLAG |

**Metrics:** intent_match, scratchpad_len, scope_anchor fields present, duration

---

### Script 2: `test_analysis_new.py` — Analysis with Dynamic Guidance

**8 test cases. Intent pre-set.** Tests whether `analysis_guidance[intent]` produces complete analysis.

| # | Intent | Code | Key Check |
|---|--------|------|-----------|
| 1 | EXTRACT_CONSTANT | Circle (2 methods use 3.14159) | primary has BOTH ["calculateArea","calculateCircumference"] |
| 2 | EXTRACT_CONSTANT | compute (1 method uses 1000000007) | primary=["compute"], new=["MOD"] |
| 3 | RENAME_SYMBOL | UserManager (field n + getN + setN) | primary=["n","getN","setN"] — all 3 |
| 4 | RENAME_SYMBOL | removeNthFromEnd (first, slow, head) | primary has all variables |
| 5 | EXTRACT_METHOD | Calculator (tax extraction) | primary=["calculateTotal"], new=["computeTaxWithRounding"] |
| 6 | DECOMPOSE | LoanApprover (compound condition) | new has booleans for each condition part, plain strings |
| 7 | FLATTEN | OrderProcessor (nested ifs + exceptions) | must_preserve lists ALL exception types and messages |
| 8 | CONSOLIDATE | wordPattern (duplicate branches) | primary identifies correct method, new=[] |

**Metrics:** completeness (all expected targets found), no_hallucinations, format_valid (strings, no objects), scratchpad_len

---

### Script 3: `test_architect_new.py` — Architect with Guidance

**8 test cases. Pre-generated analysis input.** Tests whether architect base prompt + `synthesis_guidance[intent]` produces correct plans.

| # | Intent | Analysis Input | Expected Plan |
|---|--------|---------------|---------------|
| 1 | EXTRACT_CONSTANT | primary=["calcArea","calcCirc"] new=["PI"] | 3 mutations: ADD_CONSTANT + MODIFY×2 |
| 2 | EXTRACT_CONSTANT | primary=["compute"] new=["MOD"] | 2 mutations: ADD_CONSTANT + MODIFY |
| 3 | RENAME_SYMBOL | primary=["n","getN","setN"] new=[] | 3 mutations: RENAME + MODIFY×2 |
| 4 | EXTRACT_METHOD | primary=["calcTotal"] new=["computeTax"] | 2 mutations: ADD_METHOD + MODIFY |
| 5 | DECOMPOSE | primary=["isEligible"] new=["isAdult","hasCredit"] | 3 mutations: ADD_FIELD×2 + MODIFY |
| 6 | FLATTEN | primary=["processOrder"] new=[] | 1 mutation: MODIFY, body about guard clauses |
| 7 | SPLIT_LOOP | primary=["process"] new=[] | 1 mutation: MODIFY |
| 8 | CONSOLIDATE | primary=["wordMatch"] new=[] | 1 mutation: MODIFY |

**Metrics:** mutation_count matches expected, actions_correct, targets_clean (no slashes/signatures), no_template_bleed, target_class_valid

---

### Script 4: `test_planner_chain_new.py` — Full Planner Chain

**10 cases. 5 existing + 5 new.** Full Classifier → Analysis (with guidance) → Architect (with guidance).

**Existing:**

| # | Case | Expected Intent |
|---|------|-----------------|
| 1 | flat_demo_orderprocessor | FLATTEN_CONDITIONAL |
| 2 | extract_tax_calculator | EXTRACT_METHOD |
| 3 | rename_user_manager | RENAME_SYMBOL |
| 4 | const_circle_pi | EXTRACT_CONSTANT |
| 5 | decomp_closed_island | DECOMPOSE_CONDITIONAL |

**New:**

| # | Polish Source | Instruction | Expected |
|---|--------------|-------------|----------|
| 6 | idx=275 (canWinNim) | "Decompose n % 4 != 0 into a named boolean called isNotMultipleOfFour" | DECOMPOSE_CONDITIONAL |
| 7 | idx=2174 (minOperations) | "Split the counting loop from the result-check loop" | SPLIT_LOOP |
| 8 | idx=152 (findMin) | "Rename left to lowBound and right to highBound" | RENAME_SYMBOL |
| 9 | idx=1576 (Solution.isPalindrome) | "Extract the while-loop palindrome check into checkPalindrome" | EXTRACT_METHOD |
| 10 | idx=125 trimmed (uniquePaths method) | "Flatten the nested loops using guard clauses" | FLATTEN_CONDITIONAL |

**Metrics:** classifier_correct, analysis_complete, plan_executable, plan_mutation_count, chain_coherent, no_hallucinations

---

## Execution

```bash
conda activate horizon_env

# Script 1
python tests/validation/test_classifier_new.py

# Script 2
python tests/validation/test_analysis_new.py

# Script 3
python tests/validation/test_architect_new.py

# Script 4
python tests/validation/test_planner_chain_new.py
```

## Model Calls

| Script | Cases | Calls | ~Time |
|--------|-------|-------|-------|
| Classifier | 10 | 10 | 1 min |
| Analysis | 8 | 8 | 1 min |
| Architect | 8 | 8 | 2 min |
| Chain | 10 | 30 | 5 min |
| **Total** | **36** | **56** | **~9 min** |
