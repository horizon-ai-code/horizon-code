# Specification: Orchestration JSON Schemas (Multi-Inference)

This document defines the data contracts for each of the four specialized inference calls in the 6-phase orchestration pipeline.

## 1. Inference Call 1: Intent Classifier (Planner)
**Role:** Maps natural language to a structured intent.
**Schema:**
```json
{
  "classification_scratchpad": "string",
  "intent_packet": {
    "refactor_category": "ENUM (CONTROL_FLOW | METHOD_MOVEMENT | STATE_MANAGEMENT)",
    "specific_intent": "ENUM (e.g., FLATTEN_CONDITIONAL)",
    "scope_anchor": {
      "class": "string",
      "member": "string (optional)",
      "unit_type": "CLASS_UNIT | METHOD_UNIT | STATEMENT_UNIT"
    }
  }
}
```

---

## 2. Inference Call 2: AST Architect (Planner)
**Role:** Generates a logical mutation plan based on the Intent Packet.
**Schema:**
```json
{
  "architect_scratchpad": "string",
  "ast_modification_plan": {
    "target_class": "string",
    "ast_mutations": [
      {
        "action": "ADD_METHOD | REMOVE_METHOD | MODIFY_METHOD | ADD_FIELD | REMOVE_FIELD | MODIFY_FIELD | CHANGE_CLASS_TYPE | ADD_IMPLEMENTS | ADD_EXTENDS",
        "target": "string",
        "details": {
          "modifiers": ["string"],
          "type": "string",
          "parameters": [{"name": "string", "type": "string"}],
          "refactor_strategy": "ENUM (matches specific_intent)",
          "logic_changes": ["string"],
          "body_abstract": "string"
        }
      }
    ]
  }
}
```

---

## 3. Inference Call 3: The Coder (Generator)
**Role:** Implements the AST modification plan.
**Output Format:** Strictly Java code wrapped in XML tags.
**Format:**
```xml
<code>
[Refactored Java Code]
</code>
```

---

## 4. Inference Call 4: Structural Auditor (Judge)
**Role:** Final semantic and logical verification.
**Schema:**
```json
{
  "audit_scratchpad": {
    "variable_trace": [
      { "original": "string", "refactored": "string", "mapping": "string" }
    ],
    "logic_comparison": "string"
  },
  "verdict": "ACCEPT | REVISE",
  "issues": ["string"]
}
```

---

## 5. Validation Feedback (The Loop Glue)
**Role:** Consolidated diagnostics for Tier 2 and Tier 3 failures.
**Schema:**
```json
{
  "total_faults": "integer",
  "is_recoverable": "boolean",
  "findings": [
    {
      "failure_tier": "TIER_1_SYNTAX | TIER_2_A_COMPLEXITY | TIER_2_B_BOUNDARY | TIER_2_C_INTENT_MATH | TIER_3_JUDGE",
      "error_report": {
        "message": "string",
        "faulty_node": "string (optional)",
        "actual_value": "any",
        "required_value": "any"
      },
      "recovery_hint": "string"
    }
  ]
}
```
