# Specification: Orchestrator State Machine

This document defines the Python logic and state management for the `Orchestrator` to execute the 6-phase deterministic pipeline.

## 1. Orchestration State Model

We will use a central state container to track the session lifecycle and loop metrics.

```python
class OrchestrationState(BaseModel):
    session_id: str
    base_code: str
    working_code: str
    
    # Structural Artifacts
    intent_packet: Optional[Dict] = None
    active_plan: Optional[Dict] = None
    
    # Loop Counters
    strategy_iter: int = 1  # Outer Loop (Max 3)
    syntax_iter: int = 0    # Inner Loop (Max 3)
    
    # Diagnostic Memory
    cumulative_feedback: List[Dict] = []
    
    # Lifecycle
    current_phase: int = 1
    exit_status: str = "PROCESSING"
```

---

## 2. Phase Transition Logic

### Phase 1: Ingestion & Baseline
*   Execute `Validator.identify_unit()` and `Validator.get_ast_snapshot()`.
*   Initialize `OrchestrationState`.
*   Transition to Phase 2.

### Phase 2: The Strategy Block
*   **Step 3 (Classifier):** Call Planner to generate `intent_packet`.
*   **Step 4 (Cognitive Reset):** Force `agent_service.unload()` for the Generator.
*   **Step 5 (Architect):** Call Planner to generate `ast_modification_plan`.
    *   *Input:* `intent_packet` + `cumulative_feedback`.
*   Transition to Phase 3.

### Phase 3: Plan Execution
*   **Step 6 (Coder):** Call Generator to produce `working_code`.
    *   *Input:* `active_plan` + `base_code`.
*   Transition to Phase 4.

### Phase 4: Deterministic Validation
*   **Step 7 (Tier 1 - Syntax):**
    *   If FAIL: `syntax_iter += 1`.
        *   If `syntax_iter <= 3`: Stay in Phase 4; Send error to Generator (Step 6).
        *   If `syntax_iter > 3`: `strategy_iter += 1`; Add "Syntax Unrecoverable" to `cumulative_feedback`; Reset `syntax_iter`; Transition to Phase 2 (Step 5).
    *   If PASS: Proceed to Step 8.
*   **Step 8 (Tier 2 - Structural):** Execute Checks A, B, and C in parallel.
    *   If ANY FAIL: `strategy_iter += 1`.
        *   If `strategy_iter <= 3`: Collect all findings into `cumulative_feedback`; Reset `syntax_iter`; Transition to Phase 2 (Step 5).
        *   If `strategy_iter > 3`: `exit_status = ABORT_STRATEGY`; Transition to Phase 6.
    *   If ALL PASS: Transition to Phase 5.

### Phase 5: Heuristic Adjudication
*   **Step 9 (Tier 3 - Audit):** Call Judge for semantic verification.
    *   If REVISE: `strategy_iter += 1`.
        *   If `strategy_iter <= 3`: Add Judge's issues to `cumulative_feedback`; Transition to Phase 2 (Step 5).
        *   If `strategy_iter > 3`: `exit_status = ABORT_SEMANTIC`; Transition to Phase 6.
    *   If ACCEPT: `exit_status = SUCCESS`; Transition to Phase 6.

---

## 3. Cognitive Reset & Memory Logic

### 3.1. The "Reset" (Step 4)
Before the Architect (Step 5) or Generator (Step 6) is called, the Orchestrator must ensure the model's KV cache is purged.
*   **Action:** Call `AgentService.clear_context()` followed by `gc.collect()`.
*   **Purpose:** Ensures the Generator doesn't "hallucinate" code based on the Planner's internal reasoning.

### 3.2. Cumulative Feedback (Step 8)
Findings from the Validator are converted into structured instructions for the Planner.
*   **Format:** `"Tier 2-B Failure: Nodes outside the method 'X' were modified. Your next plan must strictly preserve the class structure outside of 'X'."`

---

## 4. Finalization (Phase 6)

1.  **Metric Aggregation:** Calculate total loops and inference time.
2.  **Trace Compilation:** Fetch all `OrchestrationLog` entries and format into the final Reasoning Trace.
3.  **Output Determination:**
    *   If `SUCCESS`: Return `working_code` + `metrics` + `trace`.
    *   If `ABORT`: Return `base_code` + `intent_packet` + `error_log` explaining the circuit breaker trip.
