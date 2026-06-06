# Generator Optimization — Detailed Session Report

**Date:** 2026-06-03  
**Branch:** `generator-optimization` (off `optimization`)  
**Goal:** Improve Generator output quality within existing orchestration architecture  

---

## 1. Starting State

### Baseline Metrics (from `optimization` branch)

| Metric | Value |
|--------|:---:|
| Pipeline SUCCESS | 6/20 (30%) |
| Pipeline ABORT | 11/20 |
| SUCCESS rate distribution | 1 ABORT + ~1 timeout |
| Flatten worst CC | 6→14 (+8, 3× original) |
| Averaged duration | 84-90s |
| Plans correct | 20/20 |
| Judge correct (isolated) | 47/50 (94%) |
| Generator bottleneck | 86% of failures are Generator quality |

### Root Cause

The 3B Qwen2.5-Coder model is trained on code completion (write new code), not constrained editing (transform existing code within rules). When asked to restructure, it adds defensive code:
- `throws XxxException` to method signatures
- `if (x == null)` validation checks
- `try/catch` blocks  
- Extra methods like `initialize()`, `setAge()`
- Merged guard clauses with `||`

These additions increase cyclomatic complexity (CC), trigger boundary violations, and fail intent math checks.

---

## 2. Approaches Tested

### Approach 1: Post-Generation Repair (Deterministic)

**Description:** After Generator produces code, run regex-based stripping to remove added `throws`, null checks, and `public` modifiers.

**Implementation:** Static method `_repair_generator_output()` in orchestrator, called in `_run_phase_3` after code extraction.

**Lines changed:** ~60 (orchestrator.py)

**Result:**

| Metric | Before | After | Δ |
|--------|:---:|:---:|:---:|
| SUCCESS | 6 | 6 | 0 |
| ABORT | 11 | 11 | 0 |
| Flatten worst CC | 14 | 11-14 | No change |

**Verdict:** ✗ INEFFECTIVE. Regex strips `throws` from method signatures but the if-check BODIES remain. The CC increase comes from nested if-checks inside method bodies, not from throws declarations alone.

---

### Approach 2: Multi-Sample Generation (3 temps)

**Description:** Generate 3 outputs at temperatures [strategy_retry, 0.3, 0.5]. Quick syntax + CC check on each. Pick best by lowest CC increase.

**Implementation:** Modified `_run_phase_3` generation loop to try 3 temperatures instead of 1. `sample_score()` ranks by syntax valid + CC delta.

**Lines changed:** ~125 (orchestrator.py)

**Result:**

| Metric | Before | After | Δ |
|--------|:---:|:---:|:---:|
| **SUCCESS** | **6** | **7** | **+1** |
| ABORT | 11 | 11 | 0 |
| Flatten worst CC | 14 | **9** | **-36%** |
| inlinevar_dp duration | 296s | **100s** | **-66%** |
| extvar_med_seconds duration | 80s | **49s** | **-39%** |
| Avg duration | 84s | 92s | +9% |
| Best temp picked | — | 0.3 (67%) | |

**Verdict:** ✅ **WORKS.** Only approach that improved results. Multi-sample catches a good output on the first try, reducing syntax healing cycles. Trade-off: +9% latency for +17% SUCCESS and cleaner CC.

**Commit:** `c46b581`

---

### Approach 3: Structural Error Feedback

**Description:** When Phase 4 finds structural failures, send the Generator its own broken code + specific error messages (e.g., "CC increased from 6 to 11. Remove 3 added if-checks.") for a targeted fix, instead of regenerating the entire plan.

**Implementation:** Added `structural_fix_attempts` counter. On first structural failure, set `syntax_error_context` with Phase 4 error messages. Route to Phase 3 with context. On second failure, route to Phase 2 normally.

**Lines changed:** ~25 (orchestrator.py)

**Result:**

| Metric | Before | After | Δ |
|--------|:---:|:---:|:---:|
| SUCCESS | 7 | 7 | 0 |
| ABORT | 11 | 11 | 0 |
| Feedback routings | — | 21 | — |

**Verdict:** ✗ INEFFECTIVE. 21 feedback routings but zero improvement. The 3B Generator cannot fix its own output. The model produces the same class of errors regardless of specific feedback.

**Commit:** `dfb2adc`

---

### Approach 4: Scope Isolation (Experimental — Reverted)

**Description:** Extract only the target method from the class, send to Generator. The model sees 80% less code. Orchestrator re-inserts generated method into preserved class skeleton.

**Implementation:** Added `_isolate_target_scope()` (AST-based method extraction) and `_reconstruct_class()` (method re-insertion). Wired into `_run_phase_3`.

**Lines changed:** ~100 (orchestrator.py)

**Result:**

| Metric | Before | After | Δ |
|--------|:---:|:---:|:---:|
| SUCCESS | 7 | **5** | **-2 (REGRESSION)** |
| ABORT | 11 | 12 | +1 |
| NEW timeouts | 1 | **2** (const_long_derangement) | +1 |
| Duration | 92s | 110s | +20% |

**Verdict:** ✗ **REGRESSION.** The Generator needs class-level context to add fields (`ADD_CONSTANT`), understand imports, and see other methods. Isolation breaks intents that require class-level changes. **Reverted — no commit.**

---

## 3. Subagent Workflow

### Workflow Used

```
IDEATION agent ──→ DISCUSS agent ──→ EXECUTION agent ──→ TEST (manual) ──→ DISCUSS again
```

### IDEATION Agent

**Role:** Generate decomposition ideas for Generator phase

**Output:** 10 ideas — ranked by feasibility
1. Mutation-by-Mutation Sequential Application
2. Two-Phase: Draft then Defense-Strip
3. Skeleton-First, Body-Later
4. Reverse-Order Generation (EXTRACT_METHOD)
5. Independent Mutation Generation + Merge
6. Fill-in-the-Blank Templates
7. Constraint-Verified Intermediate Output
8. Contrastive "Before/After" Prompting
9. Parallel Candidate + Majority Vote
10. **Single-Target Prompt Isolation** (top pick)

### DISCUSS Agent

**Role:** Evaluate and prioritize ideas

**Output:** Ranked list with effort/risk/compatibility assessment

| Rank | Idea | Impact | Effort | Decision |
|:---:|------|--------|:---:|------|
| 1 | #10 — Single-Target Isolation | HIGH | LOW | → Implement first |
| 2 | #4 — Reverse-Order Generation | HIGH | LOW | → Implement second |
| 3 | #8 — Contrastive Prompting | MEDIUM | LOW | → Implement third |
| 4 | #6 — Fill-in-the-Blank Templates | MED-HIGH | MED | → Backlog |
| 5 | #1 — Mutation-by-Mutation | MEDIUM | MED | → Backlog |
| 6-10 | Others | LOW-MED | VARIES | → Not recommended |

### EXECUTION Agent

**Role:** Implement top-ranked approach (#10 — Scope Isolation)

**Output:** Code changes to `app/modules/orchestrator.py` with two new static methods (`_isolate_target_scope`, `_reconstruct_class`) and wiring in `_run_phase_3`.

**Result:** Implementation completed, but testing showed **regression** (SUCCESS 7→5). Decision: revert. The agent correctly implemented the approach but the approach itself was wrong for the problem.

---

## 4. What Worked and What Didn't

| Approach | Mechanism | Outcome | Why |
|----------|-----------|:---:|------|
| Post-gen repair | Regex strip defensive additions | ✗ | Strips throws declarations, but if-check bodies remain — CC unchanged |
| **Multi-sample** | **3 temps, pick best CC** | **✅ +1 SUCCESS** | **Higher temp (0.3-0.5) occasionally produces cleaner output** |
| Structural feedback | Send errors to Generator for fix | ✗ | **3B model cannot self-correct: 0/21 fixes succeeded** |
| Scope isolation | Show only target method to Generator | ✗ Regression | **Breaks class-level context needed for ADD_CONSTANT, ADD_FIELD** |

### Multi-Sample — Detailed Win

| Case | Before | After | How |
|------|--------|-------|-----|
| SUCCESS count | 6 | **7** | One additional case passed all gates |
| Flatten CC (worst) | 14 (+8) | **9 (+3)** | temp=0.3 produced fewer defensive additions |
| inlinevar_dp | 296s (33 heals) | **100s (1 audit)** | temp=0.3 hit syntax-valid on first try |
| extvar_med_seconds | 80s (5 heals) | **49s (1 audit)** | temp=0.3 hit valid on first try |

---

## 5. Current State

### Branch: `generator-optimization`

```
dfb2adc feat: structural error feedback — route Phase 4 failures to Generator for targeted fix
c46b581 feat: multi-sample generator — 3 temps, pick best CC
```

### Branch: `optimization` (unchanged since session start)

Latest commit: `840bf9e` — test suite additions

### Diffs

| File | `optimization` → `generator-optimization` |
|------|------|
| `app/modules/orchestrator.py` | +125 lines (multi-sample) + +25 lines (feedback) |
| `prompts.yaml` | No changes |
| Tests | No new tests |

---

## 6. Key Learnings

1. **The 3B Generator cannot self-correct.** Even with precise error feedback, the model produces the same class of defensive additions.

2. **The 3B Generator cannot restructure without adding complexity.** Flatten at best reduces CC from +8 to +3. It never reaches ≤orig. CC increase is inherent to the model's approach.

3. **Context isolation doesn't help a 3B model.** Unlike larger models (Claude, GPT-4) that benefit from focused context, the 3B model needs the full class to understand its role.

4. **Temperature diversity is the cheapest lever.** For the cost of 3× generation runs, we get +17% SUCCESS and dramatically cleaner outputs. The stochasticity at higher temperatures sometimes breaks the defensive-programming pattern.

5. **Subagent delegation worked for ideation/discussion but not for execution.** The scope isolation idea was correctly implemented but the approach was wrong. The agents correctly identified the risk but rated it low (HIGH impact, LOW risk) — showing the gap between analysis and real-world model behavior.

---

## 7. Remaining Options

| # | Idea | Effort | Expected Impact | Risk |
|---|------|:---:|:---:|------|
| 1 | Alternative 3B model (granite_coder, stable_coder) | MEDIUM | Unknown | Different model, different bias |
| 2 | Contrastive ICL examples for Generator | LOW | LOW-MEDIUM | Already partially done (ICL guidance) |
| 3 | Reverse-order generation (EXTRACT_METHOD) | LOW | MEDIUM | Only helps one intent |
| 4 | Mutation-at-a-time decomposition | MEDIUM | MEDIUM | 3× latency, cascade risk |
| 5 | Intent downgrade (FLATTEN→EXTRACT_METHOD) | LOW | LOW-MEDIUM | Better than nothing |
| 6 | Accept 3B ceiling | ZERO | Zero | Report "cannot refactor FLATTEN/DECOMPOSE" |

---

## 8. Recommendation

**Merge `generator-optimization` → `optimization`** for the multi-sample improvement (+1 SUCCESS). The structural feedback approach is harmless (no improvement but no regression).

**Next session:** Test alternative 3B models (`granite_coder.gguf`, `stable_coder.gguf`) as Generator. Different training data → different biases → potentially different defensive patterns.
