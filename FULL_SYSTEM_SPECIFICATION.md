# Horizon Code: Exhaustive System Technical Specification

## 1. System Overview
Horizon Code is an enterprise-grade automated refactoring system for Java. It uses a deterministic multi-agent orchestration pipeline (6-Phase State Machine) to manage LLM inference, ensuring that AI-generated code meets strict syntactic and structural invariants.

---

## 2. Core Communication & Resource Management

### 2.1 FastAPI & WebSocket Entry Point (`app/main.py`)
- **Protocol:** Stateful WebSockets via `/ws`.
- **Global Orchestration Lock:** A singleton `asyncio.Lock` ensures only one refactoring session runs at a time, protecting GPU memory from over-subscription.
- **Halt Mechanism:** Allows users to cancel long-running inferences. It calls `agent_service.stop()` which sets a flag to break the LLM's token generation loop.
- **Middleware:** CORS enabled for local development (Ports 3000/127.0.0.1).

### 2.2 Telemetry Tracking (`app/utils/performance.py`)
- **Library:** `pynvml` (NVIDIA Management Library).
- **Sampling:** Polls the GPU every 0.5s during the `execute_orchestration` loop.
- **Metrics:**
    - `avg_gpu_utilization`: Mean percentage of compute cores used.
    - `avg_gpu_memory`: Mean percentage of total VRAM used.
    - `avg_gpu_memory_used`: Mean absolute VRAM in bytes.
    - `inference_time`: Total wall-clock time from baseline to finalization.

---

## 3. Data Contracts & Type Safety

### 3.1 Domain Enums (`app/utils/types.py`)
- **Role:** `Planner`, `Generator`, `Judge`, `Validator`, `System`.
- **RefactorIntent:** Categorized into `CONTROL_FLOW`, `METHOD_MOVEMENT`, and `STATE_MANAGEMENT`.
- **StructureUnit:** `CLASS_UNIT`, `METHOD_UNIT`, `STATEMENT_UNIT`.
- **ExitStatus:** `SUCCESS`, `ABORT_SYNTAX`, `ABORT_STRATEGY`, `ABORT_SEMANTIC`.
- **FailureTier:** `TIER_1_SYNTAX`, `TIER_2_A_COMPLEXITY`, `TIER_2_B_BOUNDARY`, `TIER_2_C_INTENT_MATH`.

### 3.2 Pydantic Schemas (`app/utils/schemas.py`)
- **IntentPacket:** The bridge between instructions and architecture. Contains `specific_intent` and `scope_anchor` (class/member/unit).
- **ASTModificationPlan:** A list of `ASTMutation` objects. Each mutation contains an `action` (e.g., ADD_METHOD) and `details` (modifiers, return type, parameters, logic_changes).
- **ValidationFeedback:** A structured report containing `total_faults`, `is_recoverable`, and a list of `ValidationFinding` objects with `recovery_hint`.
- **StructuralAuditorResponse:** The Judge's verdict (`ACCEPT`/`REVISE`) and the detailed `audit_scratchpad`.

---

## 4. The 6-Phase Orchestration State Machine (`app/modules/orchestrator.py`)

The system manages state through the `OrchestrationState` model, traversing the following phases:

### Phase 1: Baseline
- **Complexity Analysis:** Uses `lizard` to set the `original_complexity` ceiling.
- **Structural Identity:** Uses `Validator.identify_unit` to determine the scope level.

### Phase 2: Strategy (Planner Agent)
- **Step 3 (Classifier):** Maps natural language to `IntentPacket`.
- **Step 4 (Cognitive Reset):** Purges KV cache via `AgentService.clear_context()`.
- **Step 5 (Architect):** Translates intent into a JSON `ASTModificationPlan`.

### Phase 3: Execution (Generator Agent)
- **Implementation:** The "Java Implementer" follows the `ASTModificationPlan` and outputs raw Java code inside `<code>` tags.

### Phase 4: Validation (The Inner Loop - Syntax)
- **Tier 1 (Syntax Check):** If code fails `javalang` parsing, the system loops back to Phase 3 for "Syntax Healing" (Max 3 attempts).
- **Tier 2 (Structural Checks):**
    - **Check A:** CC Ceiling (`current_cc <= original_cc`).
    - **Check B:** Boundary Verification (no drift in non-target methods).
    - **Check C:** Intent Math (mathematical proof of refactor success).

### Phase 5: Adjudication (The Outer Loop - Strategy)
- **Semantic Audit:** The Judge agent performs a Variable Trace to ensure no logic was lost.
- **Revision:** If audit fails or structural checks fail, the system loops back to Phase 2 for "Strategy Revision" (Max 3 attempts).

### Phase 6: Finalization
- **Circuit Breaker:** Aborts if `fault_stall_count >= 2` (faults not decreasing across outer loops).
- **Insights:** LLM generates a narrative summary of improvements.
- **Persistence:** Commits the full Reasoning Trace to SQLite.

---

## 5. Validation Engine Specs (`app/modules/validator.py`)

### 5.1 ASTWalker (The Identity Engine)
- **Serialization:** Recursively visits `javalang.tree.Node` objects.
- **Normalization:** Strips `position` and `documentation` attributes to focus on structural logic.
- **Hashing:** Generates a deterministic SHA-256 hash of the serialized JSON.

### 5.2 RefactorVerifier (The Intent Math Registry)
- **FLATTEN_CONDITIONAL:** Proves `Max_Nesting_Depth` decreased.
- **EXTRACT_METHOD:** Proves `Method_Count` increased by 1 AND a new `MethodInvocation` exists.
- **REMOVE_CONTROL_FLAG:** Proves the target variable was removed from the AST AND `Break/Return` counts increased.
- **RENAME_SYMBOL:** Normalizes AST by stripping all identifier names, then hashes the structure to prove 100% structural identity despite name changes.

---

## 6. Persistence Schema (`app/modules/context_manager.py`)

### 6.1 Table: `RefactorHistory`
- `id` (UUID): Primary Key.
- `original_code` / `refactored_code` (Text).
- `exit_status` (Enum String): Success or Abort reason.
- `total_outer_loops` / `total_inner_loops` (Int): Iteration metrics.
- `avg_gpu_utilization` / `inference_time` (Float).

### 6.2 Table: `OrchestrationLog`
- `session_id` (FK): Links to history.
- `phase` (Int): 1-6.
- `role` (String): Agent role.
- `content` (JSON): The full structured reasoning/output from the agent.

---

## 7. Configuration Management
- **`model_config.yaml`**: Manages model file paths, `n_ctx` (context size), and `n_gpu_layers`.
- **`prompts.yaml`**: Houses the strict System Prompts for each role, using XML delimiters to prevent LLM hallucinations.
