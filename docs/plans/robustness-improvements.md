# System Robustness Improvements

## Goal
Fix four critical robustness issues in the orchestration pipeline: the broken syntax healing loop, unbounded context growth, and the boundary/complexity check problems.

---

## Issue 1: Syntax Healing Loop is Broken

### Current Behavior
When the generator produces invalid Java (`check_syntax` returns `is_valid: False`), Phase 4 sets `state.current_phase = 3` and returns. Phase 3 then re-runs the generator with the **same exact prompt** — `base_code` + `active_plan` — with no syntax error context. The generator has no idea what went wrong, so it produces the same (or similar) invalid output. The "up to 3 inner loop attempts" is effectively pointless.

### Root Cause
- `_run_phase_3` uses only `state.base_code` and `state.active_plan` — it never receives error feedback
- `_run_phase_4` correctly detects the syntax failure and increments `syntax_iter`, but gives no structured error back to the generator
- The spec says "Send error to Generator (Step 6)" but the implementation doesn't do this

### New Design
When syntax validation fails, the error must be passed back to the generator as additional context in the prompt.

#### Prompt Injection
The coder prompt in Phase 3 currently looks like:

```
Modification Plan: {plan}
Base Code: <code>{code}</code>
```

When called from a syntax heal attempt, append:

```
### PREVIOUS SYNTAX ERROR (Attempt {n}/3)
{javalang_error_message}

### CURRENT BROKEN CODE (for reference)
<code>{broken_code}</code>

Fix the syntax error above. Ensure the output is valid Java wrapped in <code> tags.
```

This gives the generator three pieces of information it currently lacks:
1. What the syntax error was (javalang message)
2. What the broken code looks like (so it can localize the fix)
3. Which attempt number (so it can escalate if needed)

#### Implementation Plan

1. **Add `error_context` parameter to `_run_phase_3`**
   - Default `None`
   - Syntax heals pass a dict: `{"error": str, "attempt": int, "broken_code": str}`

2. **Modify `_run_phase_3` prompt construction**
   - If `error_context` is provided, append the PREVIOUS SYNTAX ERROR block
   - Use `broken_code` instead of `base_code` as the code to fix (the generator should fix its last attempt, not start from scratch)

3. **Modify `_run_phase_4` syntax fail path**
   - Capture the javalang error message from `syntax_res["errors"]`
   - Set `state.current_phase = 3` with the error context
   - Do NOT return to Phase 2 (strategy revision) unless syntax_iter exceeds 3

4. **Reset `syntax_iter` correctly**
   - Currently never reset after successful syntax heal — stays at 0 or accumulated value
   - Reset to 0 after `working_code` passes syntax check

#### State Changes
Add to `OrchestrationState`:
```python
syntax_error_context: Optional[Dict] = None
```

#### Tests
- `test_syntax_heal_inner_loop` — generator produces invalid code, syntax error is fed back, second attempt produces valid code
- `test_syntax_heal_exhaustion` — 3 syntax failures trigger outer loop instead of infinite inner loop
- `test_syntax_heal_prompt_contains_error` — verify the prompt sent on heal includes the javalang error

---

## Issue 2: Unbounded Context Growth

### Current Behavior
`cumulative_feedback` in `OrchestrationState` is a `List[Dict]` that grows with every outer loop iteration. Each entry contains the full JSON dump of `ValidationFinding` objects. After 3 outer loops of structural + judge feedback, this list can hold 10+ detailed error objects. This entire list is serialized into the next planner prompt.

For 3B models with 6144 token context, this silently consumes the available window. The model may:
- Lose the beginning of the code/instruction (which is at the top of the prompt)
- Produce incoherent output from truncated context
- Crash with a context overflow error

### Root Cause
No cap or summarization on `cumulative_feedback`. The code at `orchestrator.py` appends feedback in Phase 4 and Phase 5 unconditionally.

### New Design
Two options — I recommend doing both:

#### Option A: Fixed-size ring buffer (primary defense)
Cap `cumulative_feedback` to the **3 most recent entries**. When a new entry is added and the list exceeds 3, remove the oldest.

```python
state.cumulative_feedback.append(new_entry)
if len(state.cumulative_feedback) > 3:
    state.cumulative_feedback.pop(0)
```

#### Option B: Token-aware truncation (belt-and-suspenders)
Before injecting feedback into the planner prompt, estimate token count of the serialized feedback. If it exceeds ~1000 tokens, truncate older entries.

```python
def _truncate_feedback(feedback: List[Dict], max_chars: int = 2000) -> List[Dict]:
    total = sum(len(json.dumps(f)) for f in feedback)
    while total > max_chars and feedback:
        removed = feedback.pop(0)
        total -= len(json.dumps(removed))
    return feedback
```

#### Implementation Plan

1. **Modify `OrchestrationState` in `orchestrator.py`**
   - Change `cumulative_feedback` from `List[Dict]` to a capped list
   - Add a helper method or property setter that enforces the cap

2. **Modify feedback append points in `_run_phase_4` and `_run_phase_5`**
   - Insert truncation logic after appending new findings

3. **Modify prompt construction in `_run_phase_2` (both classifier and architect)**
   - Apply token-aware truncation before injecting `cumulative_feedback` into the prompt

#### Prompt Before/After

**Before (3 outer loops of feedback):**
```
Intent Packet: {...}
User Instruction: Refactor X
Code: <code>...</code>

### PREVIOUS ATTEMPT FEEDBACK
[
  {"failure_tier": "TIER_2_B", "error": "..."},
  {"failure_tier": "TIER_2_C", "error": "..."},
  {"failure_tier": "TIER_3", "error": "..."},
  {"failure_tier": "TIER_2_B", "error": "..."},
  {"failure_tier": "TIER_2_A", "error": "..."},
]
```
(5 entries, potentially 1500+ chars)

**After (capped to 3):**
```
Intent Packet: {...}
User Instruction: Refactor X
Code: <code>...</code>

### PREVIOUS ATTEMPT FEEDBACK
[
  {"failure_tier": "TIER_2_A", "error": "..."},
]
```
(Only the most recent 3 entries, ~800 chars — the model focuses on what went wrong last time)

#### Tests
- `test_cumulative_feedback_capped` — 5 entries added, only last 3 retained
- `test_feedback_truncation_in_prompt` — prompt string length is bounded
- `test_token_aware_truncation` — large entries are truncated before prompt size limit

---

## Issue 3: Boundary Check — Structural-Only Comparison

### Current Behavior
`verify_boundary()` computes SHA-256 hashes of full AST serializations. Any difference (whitespace, comments, imports, formatting) on a non-target method triggers a violation. This produces false positives with small models and does not actually measure logic preservation.

### New Design
Compare only the **control-flow structure** of non-target methods, ignoring cosmetic/formatting noise.

#### Structural Signature Algorithm
For each non-target method AST node, compute a signature from:

1. **Node-type skeleton** — the tree shape (IfStatement→Block→ReturnStatement, etc.)
2. **Operator tokens** — set of binary/unary operators used (`>`, `&&`, `+`, etc.)
3. **Branching paths** — count of conditional branches and their nesting depth
4. **Method invocation names** — the set of called method names (not arguments)
5. **String/error message literals** — exact text of string constants

#### Excluded from comparison (noise):
- Variable names
- Whitespace, formatting, comments
- Import statements
- Annotations
- Numeric literal values

#### Implementation Plan

1. **Add `get_structural_signature(node) -> str` to `ASTWalker`**
   - Recursively walk the AST subtree
   - Emit a string like: `If(Op(>), Block(Return))` for each node
   - Collect all method invocation names as sorted set
   - Collect all string literals as sorted set
   - Hash the concatenation via SHA-256

2. **Modify `verify_boundary()` in `validator.py`**
   - Replace current `serialize_node + get_hash` with `get_structural_signature`
   - Keep the same comparison logic (check each non-target method, raise `ValidationFinding` on mismatch)
   - Keep the exemption for new top-level declarations (enums, helper classes)

3. **Update `verify_rename_symbol` intent math**
   - Already uses name-stripped hashes, which aligns with structural approach
   - No change needed

#### Tests
- `test_boundary_ignores_whitespace` — formatting changes only
- `test_boundary_ignores_import_changes` — added/removed imports
- `test_boundary_detects_logic_drift` — flipped condition in non-target method
- `test_boundary_allows_new_helper_enum` — adds new enum, no violation

---

## Issue 4: Per-Intent Complexity Check Exceptions

### Current Behavior
`get_complexity()` returns the max CC across all methods, and the check is always `CC_refactored ≤ CC_original`. This incorrectly rejects valid refactors like `EXTRACT_METHOD` (which adds a method, increasing total CC).

### New Design
Add a per-intent CC rule table. For most intents, keep `max(CC_refactored) ≤ max(CC_original)`. For three intents, use different rules:

| Intent | CC Rule | Rationale |
|--------|---------|-----------|
| FLATTEN_CONDITIONAL | `CC_refactored ≤ CC_original` | Must reduce nesting |
| DECOMPOSE_CONDITIONAL | `CC_refactored ≤ CC_original` | Must reduce operator count |
| CONSOLIDATE_CONDITIONAL | `CC_refactored ≤ CC_original` | Must reduce conditional nodes |
| REMOVE_CONTROL_FLAG | `CC_refactored ≤ CC_original` | Must reduce flag variables |
| REPLACE_LOOP_WITH_PIPELINE | `CC_refactored ≤ CC_original` | Loop → stream reduces branches |
| SPLIT_LOOP | `CC_refactored ≤ CC_original + 1` | Splitting adds one loop, slight CC increase is expected |
| **EXTRACT_METHOD** | **`CC_source_refactored ≤ CC_source_original`** | Source method's CC must decrease; ignore new helper method |
| **INLINE_METHOD** | **skipped** | Inlining inherently increases caller CC; Judge handles semantic check |
| EXTRACT_VARIABLE | `CC_refactored ≤ CC_original` | Variable extraction doesn't change control flow |
| INLINE_VARIABLE | `CC_refactored ≤ CC_original` | Same logic as extract |
| EXTRACT_CONSTANT | `CC_refactored ≤ CC_original` | Constant extraction doesn't change control flow |
| RENAME_SYMBOL | `CC_refactored ≤ CC_original` | Rename doesn't change control flow |

#### EXTRACT_METHOD Rule Detail
- Parse the original code, find the target method by name (from `scope_anchor.member`)
- Compute that method's CC in isolation: `CC_source_original`
- Parse the refactored code, find the corresponding method (same name)
- Compute that method's CC in isolation: `CC_source_refactored`
- Verify: `CC_source_refactored ≤ CC_source_original`
- The new extracted helper method is **not** included in the CC comparison — extraction moves logic out of the source method, so only the source matters

#### Implementation Plan

1. **Add `get_method_complexity(code: str, method_name: str) -> int` to `Validator`**
   - Parse code with javalang
   - Find the method declaration matching `method_name`
   - Extract that method's source text
   - Run lizard on it to get its CC
   - Return the value (or 0 if method not found)

2. **Add CC rule lookup to `orchestrator.py` Phase 4 Check A**
   - Pass `state.intent_packet` to the complexity check
   - Map each `RefactorIntent` to its rule: `STRICT`, `LOOSENED(+1)`, `SKIP`, or `EXTRACT_RULE`
   - Dispatch accordingly:
     - `STRICT`: `max(CC_refactored) ≤ max(CC_original)` (current behavior)
     - `LOOSENED`: `max(CC_refactored) ≤ max(CC_original) + 1`
     - `SKIP`: always pass
     - `EXTRACT_RULE`: use `get_method_complexity` on target method

3. **Add `_get_cc_rule(intent: RefactorIntent) -> str` helper to `Orchestrator`**
   - Returns the rule string for routing

#### Tests
- `test_extract_method_cc_exception` — extract reduces source method CC but adds a helper
- `test_split_loop_cc_exception` — split increases total CC by exactly 1, passes
- `test_inline_method_cc_skip` — inline increases CC, passes (skipped)
- `test_strict_cc_enforcement` — FLATTEN still fails if CC increases (no exception)
- `test_extract_method_source_cc_increase` — source method's CC increased, should fail

---

## Files Modified

| File | Changes |
|------|---------|
| `app/modules/orchestrator.py` | Add `syntax_error_context` state, modify `_run_phase_3` prompt, modify Phase 4 syntax path, cap `cumulative_feedback`, add CC rule lookup |
| `app/modules/validator.py` | Add `get_structural_signature()`, modify `verify_boundary()`, add `get_method_complexity()` |
| `tests/test_validator_new.py` | Add boundary structural tests + per-intent CC tests |
| `tests/test_orchestrator_flow.py` | Add syntax heal inner loop test + context cap test |
