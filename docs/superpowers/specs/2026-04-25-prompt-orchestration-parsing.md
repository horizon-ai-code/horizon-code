# Specification: Prompt Orchestration & Response Parsing

This document bridges the gap between agent inputs (User Messages) and agent outputs (Robust Parsing).

## 1. Response Parsing Strategy

Since SLMs often add conversational noise, the `ResponseParser` will follow a "Search & Extract" strategy instead of a "Strict String" strategy.

### 1.1. JSON Extraction Logic
1.  **Search:** Find the first `{` and the last `}` in the response.
2.  **Clean:** Remove any Markdown wrapper (e.g., ` ```json ` or ` ``` `).
3.  **Validate:** Pass the cleaned string to `Pydantic.model_validate_json()`.
4.  **Fallback:** If parsing fails, trigger a "Format Fix" prompt (limited to 1 retry).

### 1.2. Code Extraction Logic
1.  **Search:** Use Regex `<code>(.*?)</code>` (DOTALL).
2.  **Clean:** Strip leading/trailing whitespace.
3.  **Validate:** Check for basic Java syntax presence (e.g., presence of `{` or `;`).

---

## 2. User Message Templates (The Input Contract)

### 2.1. Architect User Message (Step 5)
```text
### INTENT PACKET
{intent_packet_json}

### PREVIOUS FEEDBACK (IF ANY)
{cumulative_feedback_string}

### SOURCE CODE
<code>
{base_code}
</code>

Based on the intent and feedback above, generate the AST Modification Plan.
```

### 2.2. Coder User Message (Step 6)
```text
### AST MODIFICATION PLAN
{modification_plan_json}

### SOURCE CODE
<code>
{base_code}
</code>

Implement the plan exactly. Output only the code.
```

### 2.3. Auditor User Message (Step 9)
```text
### INTENT
{intent_packet_json}

### MODIFICATION PLAN
{modification_plan_json}

### ORIGINAL CODE
<code>{base_code}</code>

### REFACTORED CODE
<code>{working_code}</code>

Perform the semantic audit.
```

---

## 3. Node Identification Protocol

To ensure the Planner, Generator, and Validator all talk about the same node:

*   **Identifier:** `Node_Type::Member_Name::Occurrence_Index`
*   **Example:** `IfStatement::validateUser::2` (The second if-statement in the validateUser method).
*   **Logic:** The `Validator` will use this same string to anchor its "Check B" identity mask.
