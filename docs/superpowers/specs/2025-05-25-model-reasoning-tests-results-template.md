# Model Reasoning Test Results — Template

> **Note**: As of June 2026, `test_results/` moved to `tests/results/`. All historical references to `test_results/` in this document remain accurate for the time period described.

Each test script (`test_planner_isolated.py`, `test_judge_isolated.py`, `test_generator_isolated.py`) MUST produce a report following this template. Reports go to `test_results/`.

---

## Planner Isolated Results (`test_results/planner_isolated_report.md`)

```
# Planner Isolated Reasoning Report

**Date:** YYYY-MM-DD
**Model:** Qwen2.5-Coder-3B-Instruct
**Cases:** 15 code+instruction pairs
**Calls:** 45 (3 model calls per case: classifier → analysis → synthesis)

---

## Summary

| Metric | Result |
|--------|--------|
| Total cases | 15 |
| Classifier accuracy (intent matches expected) | X/15 |
| Scope anchor validity (member+class exist in AST) | X/15 |
| Analysis completeness (targets+preserve captured) | X/15 |
| Plan executability (mutations reference real targets) | X/15 |
| Hallucination rate (invented names in plan) | X hallucinations |
| Analysis→Plan coherence (plan references analysis items) | X/15 |

---

## By Intent

| Intent | Cases | Class Acc | Scope | Analysis | Plan | Hallucinations |
|--------|-------|-----------|-------|----------|------|----------------|
| FLATTEN_CONDITIONAL | N | X/N | X/N | X/N | X/N | X |
| EXTRACT_METHOD | N | X/N | X/N | X/N | X/N | X |
| ... | | | | | | |

---

## Detailed Results

### Case N: {case_name} ({PASS/FAIL})

- **Input:** code ({N} chars) + instruction "{abbreviated}"
- **Expected intent:** {REFACTOR_INTENT}
- **Classifier output:** {actual intent} {✓/✗}
- **Scope anchor:** {class}.{member}, {UNIT_TYPE} {✓/✗ — reason}
- **Analysis targets:** {[list]} {✓/✗ — reason}
- **Analysis must_preserve:** {[list]} {✓/✗ — reason}
- **Plan mutations:** {count} mutations {✓/✗ — reason}
- **Hallucinations:** {list of invented names, or "None"} {✓/✗}
- **Coherence:** Analysis→Plan {aligned/misaligned} {✓/✗ — reason}
- **Duration:** {X.X}s
- **Verdict:** {PASS/FAIL}

#### What happened
_{2-3 sentences describing what the model did right or wrong}_

#### Why this likely happened
_{2-4 sentences diagnosing the root cause: hypothesis about model limitation, prompt weakness, or data characteristic that caused the outcome}_

#### Raw output

```json
{ full 3-step output JSON }
```
```

---

## Judge Isolated Results (`test_results/judge_isolated_report.md`)

```
# Judge Isolated Reasoning Report

**Date:** YYYY-MM-DD
**Model:** Llama-3.2-3B-Instruct
**Cases:** 10 cases × 5 runs = 50 calls
**Design:** 5 ACCEPT-expected + 5 REVISE-expected, each run 5× for consistency

---

## Summary

| Metric | Result |
|--------|--------|
| Total runs | 50 |
| Correct verdict (matches expected) | X/50 (X%) |
| False ACCEPT rate (REVISE-expected but ACCEPT) | X/25 |
| False REVISE rate (ACCEPT-expected but REVISE) | X/25 |
| Accuracy on ACCEPT-expected cases | X/25 (X%) |
| Accuracy on REVISE-expected cases | X/25 (X%) |
| Unanimous cases (5/5 same verdict) | X/10 |
| Volatile cases (3-2 split) | X/10 |
| Avg scratchpad length | X chars |
| Avg issues count | X.X |

---

## Per-Case Detail

### Case N: {case_name} (expected: {ACCEPT|REVISE})

| Run | Verdict | Issues | Scratchpad len | Duration |
|-----|---------|--------|----------------|----------|
| 1 | {ACCEPT/REVISE} | "{issues or empty}" | N | X.Xs |
| 2 | | | | |
| ... | | | | |
- **Accuracy:** X/5
- **Consistency:** {unanimous/4-1/3-2} split
- **Raw verdicts:** [{verdicts list}]

#### What happened
_{2-3 sentences on what the Judge got right or wrong}_

#### Why this likely happened
_{2-4 sentences diagnosing the root cause: scratchpad analysis, task ordering hypothesis, model limitation diagnosis}_

#### Raw output per run

```json
{ array of 5 audit JSONs }
```
```

---

## Generator Isolated Results (`test_results/generator_isolated_report.md`)

```
# Generator Isolated Reasoning Report

**Date:** YYYY-MM-DD
**Model:** Qwen2.5-Coder-3B-Instruct
**Cases:** 15 (12 real plans + 3 bad-plan stress tests)

---

## Summary

| Metric | Result |
|--------|--------|
| Total cases | 15 |
| Syntax pass rate | X/15 (X%) |
| Plan compliance rate (real cases) | X/12 (X%) |
| Planned elements present (total / total expected) | X / Y |
| Anti-pattern violation rate (real cases) | X/12 (X%) |
| Bad-plan graceful handling | X/3 (X%) |

---

## By Intent

| Intent | Cases | Syntax | Compliance | Anti-patterns |
|--------|-------|--------|------------|---------------|
| EXTRACT_METHOD | N | X/N | X/N | X/N |
| FLATTEN_CONDITIONAL | N | X/N | X/N | X/N |
| RENAME_SYMBOL | N | X/N | X/N | X/N |
| ADD_CONSTANT | N | X/N | X/N | X/N |
| DECOMPOSE_CONDITIONAL | N | X/N | X/N | X/N |
| Bad-plan stress | 3 | X/3 | N/A | N/A |

---

## Detailed Results

### Case N: {case_name} ({PASS/FAIL})

- **Input:** code ({N} chars) + plan with {N} mutations
- **Syntax:** {Valid/Invalid} {✓/✗}
- **Planned elements:** {present/total} present
  - {mutation_action}({target}) — {present/missing/unchanged} {✓/✗}
  - ...
- **Anti-pattern violations:** {list or "None"} {✓/✗}
- **Duration:** {X.X}s
- **Verdict:** {PASS/FAIL}

#### What happened
_{2-3 sentences describing what the Generator produced}_

#### Why this likely happened
_{2-4 sentences diagnosing: capability limit, anti-pattern rule overload, plan complexity, code length impact}_

#### Plan fed to Generator

```json
{ the ast_modification_plan }
```

#### Generated output

```java
{ the refactored code or original if unchanged }
```
```

---

## Cross-Case Analysis (append to each report)

```
## Cross-Case Analysis

### {Model role} succeeds reliably when:

| Pattern | Pass rate | Cases |
|---------|-----------|-------|
| {condition X} | X% | {list case IDs} |
| {condition Y} | X% | {list case IDs} |

### {Model role} struggles when:

| Pattern | Pass rate | Cases |
|---------|-----------|-------|
| {condition A} | X% | {list case IDs} |
| {condition B} | X% | {list case IDs} |

### Key findings

_{3-5 bullet points of the most important patterns observed across all cases}_

### Recommendations

_{2-3 actionable suggestions based on the findings: prompt changes, model constraints to add, where to invest improvement effort}_
```

---

## Raw Data Appendix (append to each report)

```
## Raw Data

Full results as JSON array saved to:
`test_results/{role}_isolated_results.json`

Each entry:
{
  "case": "case_name",
  "input": { case-specific inputs },
  "output": { model output },
  "metrics": { computed metrics },
  "diagnosis": { "what_happened": "...", "why": "..." }
}
```
