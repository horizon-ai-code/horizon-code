# Detailed Design: Validator Module Overhaul

This document details the low-level logic and library utilization for the new `Validator` module as required by the 6-phase orchestration pipeline.

## 1. Library Utilization Strategy

### 1.1. javalang (AST Processing)
*   **Purpose:** Syntax verification, structural classification, AST serialization, and node-level comparison.
*   **Key Utilization:**
    *   `javalang.parse.parse()`: Primary entry point for syntax checks.
    *   `javalang.ast.Node`: The base class for all AST nodes. We will implement a custom `ASTWalker` (visitor pattern) to serialize these nodes into a deterministic JSON format for comparison.
    *   `javalang.tokenizer.tokenize()`: Used for low-level checks like brace parity before parsing.

### 1.2. lizard (Cyclomatic Complexity)
*   **Purpose:** Quantitative measurement of code complexity.
*   **Key Utilization:**
    *   `lizard.analyze_source_code()`: Analyzes snippets (after wrapping in Class/Method templates if necessary).
    *   We will specifically extract `cyclomatic_complexity` from the `function_list` to ensure the "Complexity Check" (Tier 2-A) is grounded in standard metrics.

---

## 2. Phase 1: Ingestion & Baseline Logic

### 2.1. Unit Identification (`identify_unit`)
*   **Logic:** Attempt parsing through 3 tiered templates (Compilation Unit -> Class Member -> Statement Block).
*   **Outcome:** Assign a `StructureUnit` enum (`CLASS_UNIT`, `METHOD_UNIT`, `STATEMENT_UNIT`). This dictates how future snippets are "wrapped" before parsing.

### 2.2. AST Snapshotting (`get_ast_snapshot`)
*   **Logic:**
    1.  Parse the original code.
    2.  Walk the tree and generate a JSON representation containing:
        *   `node_type`: e.g., "MethodDeclaration", "IfStatement".
        *   `content_hash`: A hash of the node's properties (excluding line/column numbers to allow for formatting changes).
        *   `children`: Recursive list of child nodes.
*   **Storage:** This snapshot is held in the `Orchestrator` session state for comparison in Phase 4.

---

## 3. Tier 1: Syntax Heal (Inner Loop)

*   **Logic:**
    1.  `Validator.check_syntax(candidate_code)` returns a list of error objects (line, column, message).
    2.  If errors exist, the `Validator` formats a "Correction Prompt" for the Generator.
    3.  **Circuit Breaker:** The `Orchestrator` maintains a counter. On the 4th consecutive failure, it returns a `SyntaxUnrecoverable` signal to trigger the Outer Loop.

---

## 4. Tier 2: Structural Routing Engine (The Routing Engine)

This is the core of the deterministic validation.

### 4.1. Check A: Complexity Check
*   **Formula:** `Refactored_CC <= Original_CC`.
*   **Exception:** If the Intent is `EXTRACT_METHOD`, the *total* CC across the class may increase slightly, but the CC of the *source method* must decrease.
*   **Implementation:** Use `lizard` to compare the max CC of the affected unit.

### 4.2. Check B: Global Boundary Verification
*   **Goal:** Ensure the model didn't "hallucinate" changes in code it wasn't supposed to touch.
*   **Logic:**
    1.  The `IntentPacket` defines a `target_scope` (e.g., a method name or a block range).
    2.  `Validator` compares the `AST_Snapshot` of nodes *outside* this scope.
    3.  **Failure Condition:** Any node mismatch (type or structural content) in the "protected zone".

### 4.3. Check C: Intent-Specific Math
*   **Logic:** Python-based verification of the `RefactorIntent`.
*   **Examples:**
    *   **`EXTRACT_METHOD`**:
        *   `MethodDeclaration` count in `Refactored_AST` == `Original_AST` count + 1.
        *   The new method must be invoked within the target scope of the original.
    *   **`FLATTEN_CONDITIONAL`**:
        *   Maximum nesting depth of `IfStatement` nodes must decrease.
    *   **`EXTRACT_VARIABLE`**:
        *   `VariableDeclarator` count in target scope == `Original_AST` count + 1.
    *   **`RENAME_SYMBOL`**:
        *   The count of the old symbol name must be 0 in the target scope.
        *   The count of the new symbol name must match the previous count of the old one.

---

## 5. Tier 3: Heuristic Adjudication (Judge Evaluation)

*   **Logic:** The Judge is passed the `Original Code`, `Refactored Code`, and the `Intent Packet`.
*   **Constraint:** The Judge *must* output a `<thought>` block showing variable mapping (e.g., "Variable `x` in Line 5 maps to `result` in Line 12").
*   **Failure Condition:** If the Judge identifies a logic change (e.g., "The condition `a > b` was changed to `a >= b`"), it triggers the Outer Loop with a `SemanticAlteration` status.

---

## 6. Implementation Prerequisites
*   **`ASTWalker` class**: A utility in `validator.py` that extends `javalang.ast.Node` processing to create the serializable JSON.
*   **`IntentVerifier` class**: A registry of functions mapped to the `RefactorIntent` Enum that performs the "Intent Math".
