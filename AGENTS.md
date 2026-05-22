# Horizon Code — Agent Guide

## Architecture

FastAPI app at `app/main.py`. Entrypoint is WebSocket `/ws`. REST endpoints at `/api/history`.

Three small (3B) GGUF models via `llama-cpp-python`:
| Role | Model | Config key |
|------|-------|------------|
| Planner (classifier + architect) | Qwen2.5-Coder-3B | `model_config.yaml planner` |
| Generator (coder) | Qwen2.5-Coder-3B | `model_config.yaml generator` |
| Judge (auditor + insights) | Llama-3.2-3B | `model_config.yaml judge` |

Prompts live in `prompts.yaml`, model params in `model_config.yaml`.

## 6-Phase Orchestration

All phases run in `app/modules/orchestrator.py` in `execute_orchestration()`:
1. **Baseline** — CC via lizard
2. **Strategy** — Planner: classifier → architect
3. **Execution** — Generator produces `<code>` block
4. **Validation** — Syntax (javalang) → CC / Boundary / Intent Math
5. **Adjudication** — Judge auditor (ACCEPT/REVISE)
6. **Finalization** — Insights + DB persist

Global `asyncio.Lock` in `main.py` serializes all orchestrations. Only one runs at a time.

## Modules

| Path | Purpose |
|------|---------|
| `app/modules/agent_service.py` | Model lifecycle (load/swap/unload/clear_context), streaming generation with halt support |
| `app/modules/validator.py` | javalang AST parse, lizard CC, `ASTWalker` serialization, `RefactorVerifier` intent checks, boundary verification |
| `app/modules/context_manager.py` | SQLite via peewee, `RefactorHistory` + `OrchestrationLog` tables, automatic column migration |
| `app/modules/connection_manager.py` | WebSocket `ClientConnection` per session, delegates DB calls to `DatabaseManager` |
| `app/utils/response_parser.py` | JSON/XML extraction from noisy LLM output, trailing comma repair, None→null fix |
| `app/utils/formatters.py` | JSON→Markdown formatting for frontend display |
| `app/utils/performance.py` | GPU metrics via pynvml (0.5s polling) |
| `app/utils/schemas.py` | Pydantic models. Key: `IntentClassifierResponse`, `ASTArchitectResponse`, `StructuralAuditorResponse`, `ValidationFeedback` |
| `app/utils/types.py` | Enums: `RefactorIntent` (12 intents), `Role`, `ExitStatus`, `FailureTier`, `StructureUnit` |

## Data flow

```
WebSocket JSON → RefactorRequest → Orchestrator → AgentService.generate()
                  → Validator.check_syntax() / verify_boundary() / verify_intent()
                  → AgentService.generate() (Judge)
                  → ClientConnection.send_result() + send_insights()
```

## Tests

Mix of `unittest` and `pytest`. Async tests use `unittest.IsolatedAsyncioTestCase`.

```bash
# Run all
python -m pytest tests/
# Single file
python -m pytest tests/test_validator_new.py -v
# Single test
python -m pytest tests/test_validator_new.py::TestValidatorNew::test_verify_flatten_conditional_success -v
# Direct unittest
python -m unittest tests.test_validator_new
```

Key test files:
- `test_validator_new.py` — all intent math + boundary checks
- `test_orchestrator_flow.py` — full 6-phase flow with mocked LLM
- `test_orchestrator_halt.py` — cancellation/error handling
- `test_response_parser.py` — XML/JSON extraction edge cases
- `test_formatters.py` — frontend formatting

## Conventions

- **Type hints** mandatory on all function signatures
- **Pydantic** for all inter-agent data (fail-fast validation)
- **Composition over inheritance** (Orchestrator uses Validator + AgentService)
- **Immutable state** — `OrchestrationState` transitions via `model_copy(update=...)`
- **Atomic DB** — all writes in `db.atomic()` context manager
- **No executing generated Java** — static AST analysis only
- **Private methods** prefixed `_` for internal module state
- **Cumulative feedback** capped to last 3 entries (see `docs/plans/robustness-improvements.md`)

## Running

```bash
conda activate horizon_env
uvicorn app.main:app --reload
```

Conda env created from `conda.yaml`. `models/` and `db/` are gitignored — download models via `python setup_env.py` or `./download_models.sh`.

## Known active issues

See `docs/plans/robustness-improvements.md` (issues 1-4) and `docs/plans/additional-issues.md` (issues 5-16).

Key gotchas:
- Syntax healing loop is broken (issue 1) — `_run_phase_3` re-sends same prompt on syntax fail
- No context size management (issue 2) — feedback grows unbounded
- Boundary check too strict (issue 3) — full SHA-256 hash flags noise as violations
- CC check ignores intent type (issue 4) — EXTRACT_METHOD always fails
