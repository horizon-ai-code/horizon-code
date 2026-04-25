# Specification: Intent-Specific AST Math

This document defines the deterministic mathematical and structural checks for each refactoring category. These checks are executed in **Phase 4, Tier 2-C** of the orchestration pipeline.

## 1. Tier 2: Deterministic Routing Engine (Routing Logic)

This table defines the three-checkpoint routing logic for **Phase 4, Step 8**.

### 1.1. Control Flow Complexity Reduction

| Refactoring Type | Check A: CC Rule | Check B: Boundary Anchor | Check C: Structural Delta (Intent Math) |
| :--- | :--- | :--- | :--- |
| **FLATTEN_CONDITIONAL** | **Strict:** $\le CC_{init}$ | Target Method Body | `Max Nesting Depth` of `IfStatement` must decrease. |
| **DECOMPOSE_CONDITIONAL** | **Strict:** $\le CC_{init}$ | Target Method Body | `BinaryExpression` operator count per `If` node must decrease. |
| **CONSOLIDATE_CONDITIONAL**| **Strict:** $\le CC_{init}$ | Target Method Body | Total `IfStatement` + `SwitchCase` nodes in method must decrease. |
| **REMOVE_CONTROL_FLAG** | **Strict:** $\le CC_{init}$ | Target Loop Block | Target flag variable must be removed from AST; `Break`/`Return` count must increase. |
| **REPLACE_LOOP_WITH_PIPELINE**| **Strict:** $\le CC_{init}$ | Target Method Body | `For`/`While` node count must decrease; `MethodInvocation` to `.stream()` must exist. |
| **SPLIT_LOOP** | **Exception:** Max +1 | Target Method Body | `For`/`While` node count must increase by 1; `Statement` count per loop must decrease. |

### 1.2. Method-Level Movements

| Refactoring Type | Check A: CC Rule | Check B: Boundary Anchor | Check C: Structural Delta (Intent Math) |
| :--- | :--- | :--- | :--- |
| **EXTRACT_METHOD** | **Strict:** $\le CC_{init}$ | Target Class | `MethodDeclaration` count == $+1$; `MethodInvocation` in source site must exist. |
| **INLINE_METHOD** | **Exception:** Permitted | Target Class | `MethodDeclaration` count == $-1$; Deletion of helper method; Inlining of body to caller. |

### 1.3. Variable State Management & Semantics

| Refactoring Type | Check A: CC Rule | Check B: Boundary Anchor | Check C: Structural Delta (Intent Math) |
| :--- | :--- | :--- | :--- |
| **EXTRACT_VARIABLE** | **Strict:** $\le CC_{init}$ | Target Method Body | `LocalVariableDeclaration` count == $+1$; New initializer must match old inlined expr. |
| **INLINE_VARIABLE** | **Strict:** $\le CC_{init}$ | Target Method Body | `LocalVariableDeclaration` count == $-1$; Old expr must replace all references. |
| **EXTRACT_CONSTANT** | **Strict:** $\le CC_{init}$ | Target Class | `FieldDeclaration` (static final) count == $+1$; Literal value must match initializer. |
| **RENAME_SYMBOL** | **Strict:** $\le CC_{init}$ | Target Scope (Method/Class) | Symbol name string change ONLY; Structural hash of surrounding nodes must be 100% identical. |

---

## 2. Logic Implementation Detail

### Check B: Boundary Verification Logic
1.  **Extract Anchor**: Identify the parent node of the `Target Scope` (e.g., the parent Class or Method).
2.  **Generate Mask**: Create an AST mask that identifies all nodes *not* children of the anchor.
3.  **Hash Comparison**: `AST_Hash(Refactored_Masked_Nodes) == AST_Hash(Original_Masked_Nodes)`.
4.  **Verdict**: If hashes differ, a "Global Boundary Violation" is raised, triggering the **Outer Loop**.

### Check C: Intent Math Logic
The `Validator` will implement a `RefactorVerifier` registry. Each entry in the table above corresponds to a Python function that:
1.  Counts specific node types in the `Original` and `Refactored` ASTs.
2.  Applies the delta formula (e.g., `count_new == count_old + 1`).
3.  Verifies specific structural presence (e.g., a `.stream()` invocation).

---

## 4. Global Invariant (The "Do No Harm" Rule)

Regardless of the intent, the following must always be true for **Phase 4, Tier 2-B**:
1.  **Identity Check:** `AST_Hash(Nodes_Outside_Scope)` must be identical.
2.  **Signature Preservation:** If refactoring a method body, the `MethodDeclaration` signature (Return Type, Name, Parameters) must not change unless the intent is specifically `CHANGE_METHOD_SIGNATURE` (not currently in scope).
