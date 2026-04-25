# Implementation Plan: New Orchestration Pipeline

This plan outlines the transition from the current linear orchestration to the 6-phase deterministic orchestration pipeline as specified in `@new_design.txt`.

## 1. High-Level Architecture Changes

### Phase 1: Ingestion & Baseline
*   **Structural Identification:** Use `javalang` to classify input into `CLASS_UNIT`, `METHOD_UNIT`, or `STATEMENT_UNIT`.
*   **Baseline Snapshot:** Generate and store the initial AST JSON and Cyclomatic Complexity (CC).

### Phase 2: The Strategy Block
*   **Intent Generation (Planner Call 1):** Map NL instructions to a `RefactorIntent` Enum.
*   **Cognitive Reset:** Ensure the Generator starts with a fresh context (handled by `AgentService.unload()` or message history clearing).
*   **Plan Generation (Planner Call 2):** Output `ASTModificationJSON` detailing specific structural changes.

### Phase 3: Plan Execution
*   **Code Generation (Generator Call 3):** Generate code based on the `ASTModificationJSON`.

### Phase 4: Deterministic Validation Routing
*   **Step 7: Tier 1 Validation (Syntax Heal):** javalang attempts to parse. Inner Loop for rapid fixes (Max 3).
*   **Step 8: Tier 2 Validation (Cumulative Diagnostics):** The system executes Checks A, B, and C in parallel. 
    *   **Logic:** Do NOT exit on first failure. Gather all structural, complexity, and boundary violations.
    *   **Routing:** If any check fails, route a consolidated `ValidationFeedback` array back to the Planner (Step 5).
    *   **Benefit:** Prevents "ping-pong" loops where the Planner fixes one tier only to trigger another in the next pass.

### Phase 5: Heuristic Adjudication
*   **Tier 3 (Judge Audit):** Final evaluation using CoT. Triggers Outer Loop if logic is altered.
*   **Circuit Breaker:** Global limit of 3 Outer Loop iterations.

### Phase 6: Finalization
*   **Output Generation:** Success vs. Abort (Graceful Degradation).

---

## 2. Low-Level Implementation Tasks

### 2.1. Schema & Type Definitions (`app/utils/types.py` & `app/utils/schemas.py`)
*   Define `RefactorIntent` Enum: `FLATTEN_CONDITIONAL`, `EXTRACT_METHOD`, `EXTRACT_VARIABLE`, `RENAME_SYMBOL`, `SIMPLIFY_EXPRESSION`, etc.
*   Define `StructureUnit` Enum: `CLASS_UNIT`, `METHOD_UNIT`, `STATEMENT_UNIT`.
*   Define `IntentPacket` Pydantic model: `intent: RefactorIntent`, `target_boundaries: Dict`.
*   Define `ASTModificationJSON` Pydantic model: `action: str`, `target_node: str`, `replacement: str`.
*   Update `LogEntry` to support new roles/phases.

### 2.2. Validator Enhancements (`app/modules/validator.py`)
*   **`get_ast_json(code: str)`**: Implement a method that converts `javalang` AST into a serializable/comparable JSON structure.
*   **`identify_unit(code: str)`**: Determine if the snippet is a Class, Method, or Statement block using existing templates.
*   **`verify_boundaries(original_ast, refactored_ast, intent_packet)`**: Check if nodes outside the target scope remain identical.
*   **`verify_intent_math(original_ast, refactored_ast, intent: RefactorIntent)`**: Implement logic for specific intents (e.g., `EXTRACT_METHOD` must increase method count by 1).

### 2.3. Agent Service Updates (`app/modules/agent_service.py`)
*   Ensure `unload()` or a new `clear_cache()` method effectively performs the "Cognitive Reset" by purging any residual KV cache or internal state for the Generator model.

### 2.4. Orchestrator Overhaul (`app/modules/orchestrator.py`)
*   **New Main Loop**: Replace the current `while` loop with a nested loop structure:
    - **Outer Loop (Strategy/Logic)**: Tracks `strategy_attempts` (max 3).
    - **Inner Loop (Syntax)**: Tracks `syntax_attempts` (max 3).
*   **Phase Logic**:
    - **Step 3 & 5**: Separate calls to Planner with specific system prompts.
    - **Step 7**: Implementation of "Syntax Heal" logic.
    - **Step 8**: Implementation of Tier 2 checks (A, B, C).
    - **Step 9**: Implementation of Tier 3 Audit with CoT requirement.
*   **Prompt Engineering**:
    - Create `sysprompt_intent_classifier` for Planner.
    - Create `sysprompt_plan_generator` for Planner (outputting JSON).
    - Create `sysprompt_code_generator` for Generator (taking JSON plan).
    - Create `sysprompt_judge_audit` for Judge (CoT focus).

### 2.5. Configuration Update (`model_config.yaml`)
*   Add new system prompts for the refined agent roles.
*   Update temperatures and max tokens for specific calls (e.g., higher temp for Intent Generation, lower for Code Generation).

---

## 3. Verification & Testing

### 3.1. Unit Tests
*   Test `Validator.get_ast_json` for consistency.
*   Test `Validator.verify_intent_math` with mock ASTs.
*   Test `identify_unit` across various Java snippets.

### 3.2. Integration Tests
*   **Syntax Heal Verification**: Provide code with a missing semicolon and verify the Inner Loop fixes it without re-planning.
*   **Structural Fix Verification**: Provide an instruction that increases CC and verify the Tier 2 check triggers an Outer Loop.
*   **Circuit Breaker Verification**: Force 3 failures and verify graceful degradation to Phase 6.

### 3.3. Manual Verification
*   Trace the logs in the database to ensure "Intent Packets" and "AST Modifications" are correctly logged and broadcasted via WebSocket.
