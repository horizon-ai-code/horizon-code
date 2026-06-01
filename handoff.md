# Handoff — Current State

## What's Been Implemented (Session 1)

### Issue 1: Syntax Healing Loop
- `_run_phase_3` now checks `state.syntax_error_context` and injects javalang error + broken code into the generator prompt on retry
- `_run_phase_4` captures javalang errors into `syntax_error_context` (added `errors` capture to `check_syntax`)
- `syntax_iter` resets to 0 on successful generation
- **Files:** `app/modules/orchestrator.py`, `app/modules/validator.py`

### Issue 2: Cumulative Feedback Capped
- `OrchestrationState` has `add_feedback()` / `extend_feedback()` methods with hard cap of 3 entries
- All 4 append/extend points use these instead of direct list mutation
- **Files:** `app/modules/orchestrator.py`

### Issue 3: Structural Boundary Check
- `ASTWalker.get_structural_signature()` walks AST capturing: node-type skeleton, operators, method invocations, string literals
- Ignores: variable names, formatting, imports, annotations, numeric literals
- `verify_boundary()` uses structural signatures instead of full SHA-256 hashes
- **Files:** `app/modules/validator.py`

### Issue 4: Per-Intent CC Exceptions
- `Validator.get_method_complexity()` computes CC of a specific named method
- `Orchestrator._get_cc_rule()` maps all 12 intents: STRICT, LOOSENED (+1), SKIP, or EXTRACT_RULE
- Phase 4 Check A dispatches based on the rule table
- **Files:** `app/modules/validator.py`, `app/modules/orchestrator.py`

### Bug Fixes
- `main.py` halt handler now calls `current_task.cancel()` so `CancelledError` propagates properly
- `orchestrator.py` `current_cc` scoping bug fixed (was undefined for SKIP/EXTRACT_RULE)
- `test_connection_manager.py` — removed obsolete `insights` param from `send_result()` call
- Removed broken `verify_*.py` scripts
- Removed obsolete `docs/superpowers/`, `REVISION_BRANCH_CHANGES.md`, `new_design.txt`, `FULL_SYSTEM_SPECIFICATION.md`

## What's Been Implemented (Session 2)

### Issue 16: Strategy_iter Double-Increment Guard
- Added `strategy_iter_incremented: bool` flag to `OrchestrationState`
- All 3 increment sites (phases 3, 4, 5) check flag before incrementing
- Reset at start of phase 2
- **File:** `app/modules/orchestrator.py`

### Issue 5: Proactive JSON Repair
- Trailing comma removal runs BEFORE first `model_validate_json` call
- Single try block — no exception overhead for valid parses
- **File:** `app/utils/response_parser.py`

### Issue 8: Improved Java Syntax Gate
- Now requires `len >= 5` AND at least one of `{` or `;`
- Catches single-character garbage while allowing statements like `int x = 1;`
- **File:** `app/utils/response_parser.py`

### Issue 11: Errors Reach Frontend
- `execute_orchestration` exception handler now calls `client.send_status()` before re-raising
- **File:** `app/modules/orchestrator.py`

### Issue 12: Structured Syntax-Error Formatting
- `Validator.format_syntax_error()` parses javalang errors into `[L{line}:{col}] {description}` format
- Phase 4 syntax context uses structured format instead of raw `str(errors)`
- **Files:** `app/modules/validator.py`, `app/modules/orchestrator.py`

### Issue 6: Accurate Token Counting
- `AgentService._count_tokens()` checks each chunk's `usage.completion_tokens`
- Falls back to `len(content.split())` approximation
- Replaces `len(chunks)` (counted stream packets, not tokens)
- **File:** `app/modules/agent_service.py`

### Issue 9: Prompt Weaknesses
- Relaxed "preserve all strings EXACTLY" → "Preserve string literals and error messages unless the plan explicitly changes them"
- Removed "No talking" rule (post-processing strip handles preamble)
- Added strip-preamble in `extract_xml` — trims text before first `<code>` tag
- **Files:** `prompts.yaml`, `app/utils/response_parser.py`

### Issue 10: Input Validation
- Pydantic `@field_validator` on `RefactorRequest.code`: min 10 chars, max 100KB
- Pydantic `@field_validator` on `RefactorRequest.user_instruction`: min 3 chars, max 10KB
- **File:** `app/utils/types.py`

### Issue 15: DB Migration Versioning
- Added `SchemaVersion` table with single `version` row
- `_initialize_db` checks version — migration runs only when version < target
- Replaces column-existence check on every module load
- **File:** `app/modules/context_manager.py`

### Type Checker Fixes
- `orchestrator.py:364` — added `assert state.intent_packet is not None` before subscript
- `agent_service.py:185` — added `cast()` + explicit `-> Iterator[...]` return type
- `agent_service.py:201` — `.get("content", "")` → `.get("content") or ""` for `"".join()`
- `test_orchestrator_flow.py:79` — `# type: ignore[arg-type]` on MockClient
- **Pyright: 0 errors on all modified files**

## Test Status

**41 tests pass, 1 pre-existing error** (`test_performance` requires pytest — not installed). Pyright: 0 errors on modified files.

## Unresolved Issues

| Issue | Description |
|-------|-------------|
| 14 | No integration tests — all tests mock individual components |

## Key Architecture

```
WebSocket → main.py → Orchestrator (6-phase state machine)
                         ├─ Phase 2: Planner (classifier + architect)
                         ├─ Phase 3: Generator (coder)
                         ├─ Phase 4: Validator (syntax → CC/boundary/intent)
                         ├─ Phase 5: Judge (auditor)
                         └─ Phase 6: Finalization (insights + DB)
```

Three 3B GGUF models via `llama-cpp-python`. Global `asyncio.Lock` serializes all orchestrations.

## Running

```bash
conda activate horizon_env
uvicorn app.main:app --reload
python -m unittest discover -s tests -p "test_*.py"
```
