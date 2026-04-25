# Code Conventions & Engineering Standards

This document defines the quality, security, and architectural standards for the orchestration overhaul.

## 1. Implementation Sequence (Module Order)

To minimize regressions and maximize testability, we will follow this order:

1.  **`app/utils/types.py` & `schemas.py` (Data Contracts)**: Define the types and Pydantic models first. This ensures all other modules have a shared language.
2.  **`app/utils/response_parser.py` (New Utility)**: Implement the robust parsing logic (JSON/XML extraction) to support the new agent communication protocol.
3.  **`app/modules/validator.py` (Validation Engine)**: Build the AST snapshots, boundary masking, and intent math. This is the most complex logic and needs early unit testing.
4.  **`app/modules/agent_service.py` (Context Reset)**: Add the `clear_context()` method.
5.  **`app/modules/context_manager.py` (Persistence)**: Update the database schema and add the migration script.
6.  **`app/modules/orchestrator.py` (State Machine)**: The final step. Overhaul the `execute_orchestration` loop to tie all previous components together.

---

## 2. Clean Code Principles

### Meaningful Names
- Use intention-revealing names for variables and functions (e.g., `is_syntax_recoverable` instead of `flag`).
- Avoid encodings and mental mappings. Use clear, searchable terms.

### Functions
- **Small & Focused**: Functions should do one thing and do it well (Single Responsibility Principle).
- **Descriptive Names**: The name should clearly state what the function does (e.g., `verify_method_count_delta`).
- **Minimal Arguments**: Favor 0-2 arguments. Use Pydantic objects if more are needed to maintain clean signatures.
- **No Side Effects**: Functions should not unexpectedly modify global state or input objects unless explicitly designed to (e.g., state transitions via return values).

### DRY (Don't Repeat Yourself)
- Consolidate common AST traversal or JSON cleaning logic into shared utility methods within `validator.py` or `response_parser.py`.

---

## 3. Object-Oriented Programming (OOP) Principles

### Encapsulation
- Use private members (prefixed with `_`) for internal module state and helper methods.
- Expose only necessary methods as public APIs to define a clear boundary for each module.

### Composition over Inheritance
- Favor composing specialized classes (e.g., `Orchestrator` uses `Validator` and `AgentService`) rather than creating deep inheritance hierarchies. This keeps the codebase flexible and easy to test.

### Polymorphism & Strategy Pattern
- The `RefactorVerifier` will use a strategy-like pattern, dispatching specific validation logic based on the `RefactorIntent` enum. This allows the core `Validator` to remain generic.

### SOLID Compliance
- **SRP (Single Responsibility)**: Each module has one reason to change (e.g., `Validator` only changes if Java analysis rules change).
- **OCP (Open/Closed)**: The validation registry allows adding new refactoring types without changing the core `Validator` logic.
- **LSP/ISP**: Interfaces (Pydantic models) ensure that components can be swapped or extended without breaking dependencies.
- **DIP (Dependency Inversion)**: High-level orchestration depends on abstractions (Interfaces/Schemas), not low-level parsing details.

---

## 4. Security & Safety

- **Static Analysis Only**: Never execute or compile generated Java code within the Python environment. All validation is via static AST analysis and CC metrics.
- **Strict Sanitization**: All agent outputs must be sanitized and stripped of noise before JSON parsing to prevent injection or parser crashes.
- **Defensive Pydantic**: Every inter-agent data packet must pass Pydantic validation before being processed. Fail fast if a schema is violated.

---

## 5. Implementation Workflow

- **Type Hinting**: Mandatory for all signatures. Ensures clarity and enables robust IDE/Linter support.
- **Immutable State**: Transition `OrchestrationState` using `.model_copy(update=...)` to maintain a clear history of state changes if needed.
- **Atomic Operations**: Use database transactions (`db.atomic()`) for all persistence calls to ensure data integrity during multi-step log writes.
