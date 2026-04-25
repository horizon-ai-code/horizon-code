# Implementation Roadmap: Orchestration Overhaul

This document defines the 4-phase execution strategy to migrate from the current linear orchestration to the 6-phase deterministic pipeline.

## Phase 1: Foundations & Schemas
**Goal:** Build the type-safe foundations for the new pipeline.

1.  **Schema Implementation (`app/utils/schemas.py`)**: 
    *   Implement Pydantic models for `IntentPacket`, `ASTModificationPlan`, `ValidationFeedback`, and `OrchestrationState`.
2.  **Type Registry (`app/utils/types.py`)**:
    *   Register all Enums (RefactorIntent, RefactorCategory, ExitStatus, FailureTier).
3.  **Database Migration**:
    *   Update `context_manager.py` with new fields for `RefactorHistory` and `OrchestrationLog`.
    *   Create a standalone migration script to update `history.db`.

## Phase 2: Structural Validation Engine
**Goal:** Implement the deterministic routing logic in the Validator.

1.  **AST Walker (`app/modules/validator.py`)**:
    *   Implement `get_ast_snapshot()` for deterministic JSON serialization.
    *   Implement `identify_unit()` for automated classification.
2.  **Boundary Masking**:
    *   Implement Check B logic for protecting nodes outside the anchor.
3.  **Intent Math Registry**:
    *   Implement the `RefactorVerifier` class to handle Check C for all 12 refactoring types.
4.  **Cumulative Diagnostic Engine**:
    *   Implement logic to execute A, B, and C in parallel and return a `ValidationFeedback` collection.

## Phase 3: Agent Intelligence & Context
**Goal:** Prepare the agents and the memory reset logic.

1.  **System Prompt Templates**:
    *   Create a dedicated prompt management utility to handle the Classifier, Architect, Coder, and Auditor prompts.
2.  **Context Purge (`app/modules/agent_service.py`)**:
    *   Implement `clear_context()` using the `llama_cpp.reset()` method.
3.  **Feedback Injection Logic**:
    *   Implement the `MemoryManager` to format cumulative feedback into the Architect's next prompt.

## Phase 4: The 6-Phase State Machine
**Goal:** Overhaul the main orchestrator loop.

1.  **Phase 1-6 Controller (`app/modules/orchestrator.py`)**:
    *   Rewrite `execute_orchestration` to follow the state machine defined in `orchestrator-state-machine.md`.
    *   Implement the nested `strategy_iter` and `syntax_iter` loops.
2.  **Finalization & Trace Compilation**:
    *   Implement the `ReasoningTrace` compiler to synthesize logs into a final report.
3.  **Integration Testing**:
    *   Verify the full flow with a "Complex Refactor" (e.g., Flattening nested ifs that trigger a syntax fix and then a structural fix).

---

## Migration Safety
*   **Parallel Path**: We will implement the new logic in `orchestrator_v2.py` (or a similar isolated file) first, allowing the current system to remain functional during development.
*   **Verification**: Every Phase must pass unit tests before proceeding to the next.
