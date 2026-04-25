# Specification: Database & Logging Overhaul

This document defines the changes required to the persistence layer to support "Complete Reasoning Traces" and multi-loop orchestration tracking.

## 1. Database Schema Extensions (`history.db`)

We will update the `Session` table to include structured state tracking and loop metrics.

## 1. Schema Modifications

### 1.1. RefactorHistory (Session Summary)
| Field | Type | Change | Description |
| :--- | :--- | :--- | :--- |
| `exit_status` | TEXT | NEW | `SUCCESS`, `ABORT_STRATEGY`, `ABORT_SYNTAX`. |
| `final_intent` | JSON | NEW | The approved Intent Packet from Inference 1. |
| `final_plan` | JSON | NEW | The approved Modification Plan from Inference 2. |
| `total_outer_loops` | INT | NEW | Total strategy iterations (max 3). |
| `total_inner_loops` | INT | NEW | Total syntax heal iterations. |

### 1.2. OrchestrationLog (Iterative Trace)
| Field | Type | Change | Description |
| :--- | :--- | :--- | :--- |
| `phase` | INT | NEW | Phase number (1-6). |
| `outer_loop` | INT | NEW | Current Strategy iteration count. |
| `inner_loop` | INT | NEW | Current Syntax Heal iteration count. |
| `content` | TEXT | KEEP | Standardized to hold Structured JSON payloads. |

---

## 2. Iterative Recording Logic

Every time an agent is called or a validation check is performed, a new `OrchestrationLog` entry is created. 

**Example Trace Sequence:**
| Phase | Role | Status | Content |
| :--- | :--- | :--- | :--- |
| 2 | Planner | Intent Classified | `{ "intent": "FLATTEN_CONDITIONAL" }` |
| 2 | Planner | Plan Generated | `{ "plan": "..." }` |
| 4 | Validator | Tier 2 Failed | `{ "findings": ["Complexity Check Failed"] }` |
| 2 | Planner | Plan Regenerated | `{ "plan": "..." }` (Outer Loop 2) |
| 5 | Judge | Audit Passed | `{ "thought": "...", "verdict": "ACCEPT" }` |


---

## 3. Structured Logging (`LogEntry`)

Currently, `LogEntry` only stores `role`, `status`, and `content`. We will standardize the `content` field to hold the JSON responses from agents.

*   **Role: Planner (Step 3)** -> `content` stores the `intent_packet` JSON.
*   **Role: Planner (Step 5)** -> `content` stores the `ast_modification_plan` JSON.
*   **Role: Validator (Step 8)** -> `content` stores the `ValidationFeedback` JSON (Cumulative Findings).
*   **Role: Judge (Step 9)** -> `content` stores the `audit_scratchpad` JSON.

---

## 4. Reasoning Trace Generation (Phase 6)

When the session terminates, the `Orchestrator` will compile a `ReasoningTrace` object.

**Logic:**
1.  **Successful Refactor:** The trace shows the sequence of plans and why previous ones failed.
2.  **Aborted Refactor:** The trace shows exactly which validation tier caused the process to time out (e.g., "Aborted at Phase 4, Step 8 due to 3 failed CC checks").

---

## 5. Implementation Tasks

1.  **Migration Script**: Add new columns to the SQLite `Session` table.
2.  **`DatabaseManager` Updates**:
    *   `update_session_metrics(session_id, inner_count, outer_count, status)`
    *   `store_intent_packet(session_id, packet)`
    *   `append_validation_feedback(session_id, feedback_list)`
3.  **`Orchestrator` Integration**: Call these DB methods at every transition point in the 6-phase loop.
