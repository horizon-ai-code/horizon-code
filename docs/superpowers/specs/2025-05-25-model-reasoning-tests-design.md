# Isolated Model Reasoning Test Suite — Design Spec

**Date:** 2025-05-25  
**Status:** Design approved  
**Goal:** Test each model role (Planner, Judge, Generator) in isolation to measure reasoning capability, identify limitations, and establish baseline metrics independent of the orchestration pipeline.

**Results template:** See `docs/superpowers/specs/2025-05-25-model-reasoning-tests-results-template.md` for the required output format. Each test script MUST produce a report following that template.

---

## 1. Architecture

```
tests/model_tests/
├── harness.py                # Shared model lifecycle + report generation
├── test_planner_isolated.py   # 15 code+instruction → classifier→analysis→synthesis
├── test_judge_isolated.py     # 10 cases × 5 runs = 50 Judge calls
└── test_generator_isolated.py # 12 real + 3 stress = 15 Generator calls
```

### harness.py — ModelTestHarness

Handles all model boilerplate shared across test scripts. Each test script instantiates one harness and calls its methods.

```python
class ModelTestHarness:
    def __init__(self, role: str):
        """Create harness for 'planner', 'judge', or 'generator' role.
        Loads model_config.yaml and prompts.yaml on init."""
    
    async def load_model(self):
        """Load GGUF model into VRAM via AgentService.load()"""
    
    async def unload_model(self):
        """Release VRAM"""
    
    async def generate(self, system_prompt: str, user_prompt: str, 
                       temp: float = 0.1, max_tokens: int, 
                       response_model: Optional[Type[BaseModel]] = None) -> str:
        """Run single inference. Returns raw text response."""
    
    async def clear_context(self):
        """Purge KV cache between test cases"""
    
    def save_report(self, results: List[Dict], role: str):
        """Save JSON to test_results/{role}_isolated_results.json"""
```

### Dependencies

- `app/modules/agent_service.py` — model lifecycle, inference
- `app/modules/validator.py` — `check_syntax`, `get_complexity`, `ASTWalker`, `RefactorVerifier` for structural checks
- `prompts.yaml` — system prompts per role
- `model_config.yaml` — model paths, context sizes, layer counts
- `java_polish_full.json` — test data source (extracted code snippets)
- `demo_scenario.txt` — test data source (OrderProcessor)

### Test execution order

Tests run in order: Planner → Judge → Generator. Each test loads its model, runs all cases, unloads. Models share VRAM — only one loaded at a time. Global `asyncio.Lock` from main.py is NOT needed (these are standalone scripts, not under the orchestrator).

---

## 2. Planner Test (`test_planner_isolated.py`)

### Input per case

```python
{
    "name": "flat_demo_orderprocessor",
    "code": "<java code from java_polish or demo_scenario>",
    "instruction": "<refactoring instruction>",
    "expected_intent": RefactorIntent.FLATTEN_CONDITIONAL,  # human-labeled
}
```

15 cases. Sources: demo_scenario.txt (1 case), java_polish_full.json (14 cases). Intents covered: FLATTEN, EXTRACT_METHOD, RENAME_SYMBOL, EXTRACT_CONSTANT, DECOMPOSE_CONDITIONAL, SPLIT_LOOP, CONSOLIDATE_CONDITIONAL — 2-3 cases per intent.

### Pipeline per case (3 sequential model calls)

**Step 1 — Classifier:**
- System prompt: `prompts.yaml planner.classifier`
- User prompt: `<code>{code}</code>\n<instruction>{instruction}</instruction>`
- Max tokens: 500
- Response model: `IntentClassifierResponse`
- Parse with `ResponseParser.extract_json()`

**Step 2 — Analysis:**
- System prompt: `prompts.yaml planner.architect_analysis`
- User prompt: `Intent: {classifier_output}\nInstruction: {instruction}\nCode: <code>{code}</code>`
- Max tokens: 1024
- Parse with `ResponseParser.extract_json_text()` → `json.loads()`

**Step 3 — Synthesis:**
- System prompt: `prompts.yaml planner.architect`
- User prompt: `Analysis: {analysis_json}\nIntent: {classifier_output}\nInstruction: {instruction}\nCode: <code>{code}</code>`
- Max tokens: 2048
- Response model: `ASTArchitectResponse`
- Parse with `ResponseParser.extract_json()`

Clear context between steps. No cumulative feedback injected (isolated test).

### Deterministic checks per case

| Check | Method | Pass condition |
|-------|--------|---------------|
| Classifier accuracy | `expected_intent` vs `intent_packet.specific_intent` | Match |
| Scope anchor validity | `Validator.check_syntax(code)` → find class/member in AST | Both exist |
| Unit type match | `scope_anchor.unit_type` vs actual code structure | CLASS_UNIT if code has class, METHOD_UNIT if single method |
| Analysis targets valid | Each `primary_target` + `secondary_target` exists in AST | All exist |
| Must_preserve valid | Each preserved item (exception type, string literal) exists in code | All exist |
| Plan executability | Each `ast_mutation.target` exists in AST | All exist |
| Hallucinated names | Any mutation target or analysis item NOT found in AST | Count = 0 |
| Analysis→Plan coherence | Plan mutations reference items from analysis (targets, preserve, new_structures) | At least 1 reference |

### Hallucination detection

Compare every string in `analysis` and `plan` that looks like a code identifier (matches `[a-zA-Z_][a-zA-Z0-9_]*` pattern) against:
- Class names in original AST
- Method names in original AST
- Field names in original AST
- Exception type names extracted from `throw new XxxException(...)`
- String literal contents extracted from `.equals("...")` or similar

Any identifier not found in any of the above is a hallucination.

### Duration tracking

Per-step timing (classifier time, analysis time, synthesis time) + total per case.

---

## 3. Judge Test (`test_judge_isolated.py`)

### Test data design

10 cases. 5 ACCEPT-expected, 5 REVISE-expected. Each run 5× for consistency measurement. Total: 50 calls.

Case structure:
```python
{
    "name": "extract_method_correct",
    "original_code": "<code>",
    "refactored_code": "<code>",
    "plan_context": "Intent: EXTRACT_METHOD. Target: Calculator.calculateTotal. Mutations: ADD_METHOD(computeTaxWithRounding), MODIFY_METHOD(calculateTotal)",
    "expected_verdict": "ACCEPT",  # or "REVISE"
}
```

**ACCEPT-expected cases (5):**
1. `extract_method_correct` — Tax logic extracted, signatures preserved
2. `rename_symbol_correct` — Field `n` → `username`, all refs updated, structural sig matches
3. `flatten_guard_clauses_correct` — Guard clauses with exceptions preserved
4. `split_loop_correct` — 1 loop split into 2, logic preserved
5. `extract_constant_correct` — PI extracted, return type preserved, no side-effects

**REVISE-expected cases (5):**
6. `extract_constant_broken_sig` — `double→void` return type + `println` side-effect
7. `decompose_returned_original` — Original code returned unchanged (no decomposition)
8. `flatten_logic_inverted` — Discount applied at wrong threshold, premium gets no discount
9. `extract_method_wrong_params` — Extracted method has extra parameter
10. `rename_broke_structural` — Rename changed control flow (ternary replaced if-return)

### Per-case execution

Same prompt format as orchestrator Phase 5:
```
System: prompts.yaml judge.auditor
User: ## Plan Context\n{plan_summary}\n{mutations_list}\n\n## Code\nOriginal: <code>{orig}</code>\nRefactored: <code>{refac}</code>\nIntent: {intent_json}
```

Max tokens: 1000, temp: 0.1, response model: `StructuralAuditorResponse`. Run 5× per case with context cleared between runs.

### Metrics captured per run

- Verdict (ACCEPT/REVISE)
- Issues list
- Scratchpad length (characters in `audit_scratchpad`)
- Duration

### Calculated per case

- Accuracy: % of runs matching expected verdict
- Consistency: majority verdict / 5
- Mode: unanimous (5/5), strong (4/5), split (3/2)

### Aggregate

- False ACCEPT rate: % of REVISE-expected runs that got ACCEPT
- False REVISE rate: % of ACCEPT-expected runs that got REVISE
- Scratchpad length vs accuracy correlation
- Consistency does NOT imply accuracy — flagged in cross-case analysis

---

## 4. Generator Test (`test_generator_isolated.py`)

### Test data design

12 real cases + 3 bad-plan stress tests = 15 total.

**Real case structure:**
```python
{
    "name": "extract_tax_helper",
    "code": "<original java code>",
    "plan": { "target_class": "Calculator", "ast_mutations": [...] },  # hand-crafted, known correct
}
```

Plan mutations must reference only real targets in the code. These plans are hand-crafted (not generated by the Planner) to isolate Generator behavior from Planner quality.

**12 real cases across intents:**
- EXTRACT_METHOD: 3 (simple extraction, nested extraction, extraction with constant)
- FLATTEN_CONDITIONAL: 2 (simple flatten, flatten with exceptions)
- RENAME_SYMBOL: 2 (field rename, method rename)
- ADD_CONSTANT: 2 (single constant, multiple constants)
- DECOMPOSE_CONDITIONAL: 2 (simple condition, multi-clause condition)
- SPLIT_LOOP: 1

**3 bad-plan stress cases:**
- `bad_missing_target` — Plan has MODIFY_METHOD on method that doesn't exist in code
- `bad_empty_mutations` — Plan has empty `ast_mutations` list
- `bad_hallucinated_name` — Plan has ADD_METHOD with nonsense name `xyZzZzZzHelper`

### Per-case execution

```
System: prompts.yaml generator.coder
User: Modification Plan: {plan_json}\nBase Code: <code>{code}</code>
```

Max tokens: 2048, temp: 0.1. Parse output with `ResponseParser.extract_xml(text, "code")`.

### Deterministic checks

| Check | Method | Pass condition |
|-------|--------|---------------|
| Syntax validity | `Validator.check_syntax(output)` | `is_valid == True` |
| Planned ADD_METHOD present | `ASTWalker.find_nodes(output_ast, MethodDeclaration)` → check name | All exist |
| Planned ADD_FIELD present | `ASTWalker.find_nodes(output_ast, FieldDeclaration)` → check name | All exist |
| Planned ADD_CONSTANT present | Same as ADD_FIELD with `static final` check | All exist |
| Planned MODIFY_METHOD present | Target method name exists in output AST | All exist |
| Planned REMOVE_METHOD absent | Target method name NOT in output AST | All absent |
| Anti-pattern: merged checks | Count `||` and `&&` connections in original guard clauses vs output | No merging |
| Anti-pattern: invented methods | Any MethodDeclaration name not in plan's ADD_METHOD list or original code | None |
| Anti-pattern: exception type changed | `throw new XxxException` types in original vs output | Same types |
| Bad-plan handling | Behavior on stress cases: graceful (valid output) or crash? | Valid Java output |

### Anti-pattern detection methodology

For each rule in the coder prompt's anti-pattern list:
1. **Merged guard clauses:** Compare number of `if` → `throw` chains in original vs output. If original has 4 separate checks and output has 1-3, or if exception messages were combined, flag it.
2. **Invented methods:** Extract all MethodDeclaration names from output. Remove any that existed in original code. Remove any that are in the plan's ADD_METHOD list. Remaining are invented.
3. **Exception type changes:** Extract all `throw new XxxException` patterns from original and output. If any exception types differ, flag it.

---

## 5. Test Data Sources

### `demo_scenario.txt`
1 case — OrderProcessor with 6-level nested ifs. Used for FLATTEN_CONDITIONAL Planner test + Generator test.

### `java_polish_full.json`
279 LeetCode problems in Java. Selection criteria for 14 cases:
- Valid Java syntax (220 of 279 pass)
- No import statements (imports confuse template wrapper in isolated mode)
- Code length 200-1200 chars (fits 6144 token context with prompts)
- Coverage across Easy/Medium/Hard
- Coverage across intent types

Cases from java_polish_full.json used across the 3 roles:
- Planner: 14 java_polish + 1 demo = 15
- Judge: refactored outputs from session tests (not directly from java_polish)
- Generator: code+plan pairs where plans are hand-crafted (code from java_polish, plan from human)

---

## 6. Output

Each test script produces:
1. `test_results/{role}_isolated_results.json` — Full structured results
2. `test_results/{role}_isolated_report.md` — Report following the results template

The report MUST follow the structure defined in `docs/superpowers/specs/2025-05-25-model-reasoning-tests-results-template.md`. Each test case MUST include a "What happened" and "Why this likely happened" diagnosis section.

---

## 7. Constraints

- Single model loaded at a time (VRAM limit)
- No orchestrator dependency — scripts call `AgentService` directly
- No WebSocket — local inference only
- Temperature fixed at 0.1 for all calls (consistent with orchestrator)
- Context cleared between every test case
- Reports saved per-role (not combined)
- All test data comes from `demo_scenario.txt` or `java_polish_full.json`

---

## 8. Time Budget

| Role | Cases | Calls | Est. per call | Total |
|------|-------|-------|---------------|-------|
| Planner | 15 | 45 | ~10s | ~8 min |
| Judge | 10 | 50 | ~8s | ~7 min |
| Generator | 15 | 15 | ~15s | ~4 min |
| **Total** | | | | **~20 min** |

---

## 9. Scoring (not part of the 4-level report, for test script internal use)

When writing the test scripts, each case should be scored as PASS/FAIL based on:

**Planner:**
- PASS: Intent correct AND scope anchor valid AND plan executable AND 0 hallucinations
- FAIL: Any of the above false

**Judge:**
- PASS: verdict == expected_verdict
- FAIL: verdict != expected_verdict
- Per run, not per case — accuracy measured across all 50 runs

**Generator:**
- PASS: Syntax valid AND all planned elements present AND 0 anti-pattern violations
- FAIL: Any of the above false
- Bad-plan stress cases scored separately — PASS if valid Java output produced, FAIL if crash or empty
