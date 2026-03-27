# Horizon Code — Frontend API Documentation

> **Base URL:** `ws://localhost:8000/ws`
>
> The backend exposes a single **WebSocket** endpoint. All communication happens over this persistent connection — there are no REST endpoints.

---

## Table of Contents

- [Connection](#connection)
- [Client → Server Messages](#client--server-messages)
  - [RefactorRequest](#refactorrequest)
- [Server → Client Messages](#server--client-messages)
  - [Status Update](#status-update)
  - [Result](#result)
  - [Error](#error)
- [Orchestration Flow](#orchestration-flow)
- [Enums & Constants](#enums--constants)
- [Data Structures Reference](#data-structures-reference)

---

## Connection

1. Open a WebSocket connection to `ws://<host>:8000/ws`.
2. The server accepts the connection immediately — no authentication or handshake payload is required.
3. The connection stays alive until either side disconnects.
4. You can send multiple requests over the same connection; each one triggers a full orchestration cycle.

### CORS

The following origins are allowed:

| Origin                   |
| ------------------------ |
| `http://localhost:3000`   |
| `http://127.0.0.1:3000`  |

---

## Client → Server Messages

### `RefactorRequest`

Every message the client sends **must** be a JSON object with this exact shape:

```jsonc
{
  "code": "<string>",              // The Java source code to refactor
  "user_instruction": "<string>"   // Natural-language instruction describing the desired changes
}
```

| Field              | Type     | Required | Description                                              |
| ------------------ | -------- | -------- | -------------------------------------------------------- |
| `code`             | `string` | ✅        | The raw Java code snippet the user wants to refactor.    |
| `user_instruction` | `string` | ✅        | A natural-language description of the desired refactoring.|

> **Both fields are required.** If either is missing or the payload is not valid JSON, the server responds with an [Error](#error) message.

#### Example

```json
{
  "code": "public class Foo {\n  public void bar() {\n    System.out.println(\"Hello\");\n  }\n}",
  "user_instruction": "Rename the class to Baz and extract the print into a separate method."
}
```

---

## Server → Client Messages

The server sends three types of messages, distinguished by the `"type"` field.

---

### Status Update

Sent **multiple times** during orchestration to report progress from each agent.

```jsonc
{
  "type": "status",
  "role": "<Role>",      // Which agent is reporting — see Role enum below
  "content": "<string>"  // Human-readable status message
}
```

| Field     | Type     | Description                                                                 |
| --------- | -------- | --------------------------------------------------------------------------- |
| `type`    | `string` | Always `"status"`.                                                          |
| `role`    | `Role`   | The agent currently active. One of: `"Planner"`, `"Generator"`, `"Judge"`, `"Validator"`. |
| `content` | `string` | A short, human-readable progress description.                               |

#### Status messages you can expect (in typical order)

| #  | `role`        | `content` (typical)                                        |
| -- | ------------- | ---------------------------------------------------------- |
| 1  | `Planner`     | `"Generating plan & instructions..."`                      |
| 2  | `Planner`     | _The generated plan text_                                  |
| 3  | `Generator`   | `"Refactoring code..."`                                    |
| 4  | `Generator`   | `"Refactor draft finished."`                               |
| 5  | `Validator`   | `"Checking syntax..."`                                     |
| 6a | `Validator`   | `"Syntax passed."` _(happy path — skip to step 9)_        |
| 6b | `Validator`   | `"Errors detected."` _(enters fix loop)_                   |
| 7  | `Judge`       | `"Interpreting errors & generating fix instructions..."`   |
| 8  | `Judge`       | _The error interpretation text_                            |
|    |               | _(loops back to step 1 with corrected instructions)_       |
| 9  | `Validator`   | `"Checking complexity..."`                                 |
| 10 | `Validator`   | `"Complexity measured."`                                   |
| 11 | `Judge`       | `"Generating insights..."`                                 |

> After step 11, the next message will be a [`result`](#result).

---

### Result

Sent **once** at the end of a successful orchestration cycle.

```jsonc
{
  "type": "result",
  "code": "<string>",          // The final refactored Java code
  "complexity": {              // Complexity analysis of the final code
    "complexity_score": <int | null>,
    "structure_tier": "<string>",
    "is_fallback": <bool | null>
  },
  "insights": "<string>"      // AI-generated analysis of the refactoring
}
```

| Field                          | Type           | Description                                                                                        |
| ------------------------------ | -------------- | -------------------------------------------------------------------------------------------------- |
| `type`                         | `string`       | Always `"result"`.                                                                                 |
| `code`                         | `string`       | The final, syntax-validated, refactored Java code.                                                 |
| `complexity`                   | `object`       | Complexity analysis result (see below).                                                            |
| `complexity.complexity_score`  | `int \| null`  | Cyclomatic complexity score. `null` if the snippet was empty.                                      |
| `complexity.structure_tier`    | `string`       | Detected structure tier — see [Structure Tiers](#structure-tiers).                                 |
| `complexity.is_fallback`       | `bool \| null` | `true` if no functions were detected and complexity defaults to `1`. `null` if snippet was empty.  |
| `insights`                     | `string`       | A detailed AI-generated analysis comparing the original and refactored code.                       |

#### Example

```json
{
  "type": "result",
  "code": "public class Baz {\n  public void bar() {\n    printHello();\n  }\n  private void printHello() {\n    System.out.println(\"Hello\");\n  }\n}",
  "complexity": {
    "complexity_score": 1,
    "structure_tier": "Compilation Unit (Full Class)",
    "is_fallback": false
  },
  "insights": "The refactoring successfully extracted the print logic into a dedicated method..."
}
```

---

### Error

Sent when the client sends invalid data. The connection **stays open** — the client can retry.

#### Validation Error (wrong/missing fields)

```jsonc
{
  "type": "error",
  "message": "Invalid data format",
  "details": [                          // Pydantic validation error list
    {
      "type": "<string>",
      "loc": ["<field_name>"],
      "msg": "<string>",
      "input": "<value>"
    }
  ]
}
```

#### Malformed JSON

```jsonc
{
  "type": "error",
  "message": "Malformed JSON payload",
  "details": "<string>"                 // Description of the JSON parsing error
}
```

| Field     | Type               | Description                                                      |
| --------- | ------------------ | ---------------------------------------------------------------- |
| `type`    | `string`           | Always `"error"`.                                                |
| `message` | `string`           | Either `"Invalid data format"` or `"Malformed JSON payload"`.    |
| `details` | `array \| string`  | Pydantic error array (validation) or error string (malformed).   |

---

## Orchestration Flow

The backend runs a multi-agent pipeline to refactor code. Here is the visual flow:

```
Client sends RefactorRequest
        │
        ▼
┌──────────────┐
│   Planner    │  Generates a plan + technical instructions
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Generator   │  Applies instructions, outputs refactored code
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Validator   │  Checks Java syntax using AST parsing
└──────┬───────┘
       │
   ┌───┴───┐
   │       │
  PASS    FAIL
   │       │
   │       ▼
   │  ┌─────────┐
   │  │  Judge   │  Interprets errors, generates fix instructions
   │  └────┬────┘
   │       │
   │       └──────► Loop back to Planner with new instructions
   │
   ▼
┌──────────────┐
│  Validator   │  Measures cyclomatic complexity
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Judge     │  Generates insights comparing original vs refactored
└──────┬───────┘
       │
       ▼
  Server sends Result
```

> **Key point:** If syntax validation fails, the pipeline loops — the Judge generates fix instructions that feed back into the Planner. This can happen multiple times until the code passes.

---

## Enums & Constants

### `Role`

Identifies which agent is active. Used in `status` messages.

| Value         | Description                                          |
| ------------- | ---------------------------------------------------- |
| `"Planner"`   | Analyzes code and generates a refactoring plan.       |
| `"Generator"` | Writes the refactored code from instructions.         |
| `"Judge"`     | Interprets errors or generates post-refactor insights.|
| `"Validator"` | Validates syntax and measures complexity.             |

### `Message Types`

| `type` value | Direction         | Description                          |
| ------------ | ----------------- | ------------------------------------ |
| `"status"`   | Server → Client   | Progress update from an agent.       |
| `"result"`   | Server → Client   | Final refactored code + insights.    |
| `"error"`    | Server → Client   | Validation/parse error response.     |

### Structure Tiers

Returned in the `complexity.structure_tier` field. Indicates how the validator classified the code snippet:

| Tier | Label                              | Description                                      |
| ---- | ---------------------------------- | ------------------------------------------------ |
| 0    | `"Compilation Unit (Full Class)"`  | The snippet is a complete Java compilation unit.  |
| 1    | `"Class Members (Method/Field)"`   | Methods or fields, but not a full class.          |
| 2    | `"Statements/Block"`               | Individual statements or a code block.            |
| -1   | `"Unknown / Empty"`                | Empty or unrecognizable snippet.                  |

---

## Data Structures Reference

### Request (Client → Server)

```typescript
interface RefactorRequest {
  code: string;
  user_instruction: string;
}
```

### Status Message (Server → Client)

```typescript
interface StatusMessage {
  type: "status";
  role: "Planner" | "Generator" | "Judge" | "Validator";
  content: string;
}
```

### Result Message (Server → Client)

```typescript
interface ResultMessage {
  type: "result";
  code: string;
  complexity: ComplexityResult;
  insights: string;
}

interface ComplexityResult {
  complexity_score: number | null;
  structure_tier: string;
  is_fallback: boolean | null;
}
```

### Error Message (Server → Client)

```typescript
// Validation error (wrong/missing fields)
interface ValidationErrorMessage {
  type: "error";
  message: "Invalid data format";
  details: PydanticError[];
}

interface PydanticError {
  type: string;
  loc: string[];
  msg: string;
  input: any;
}

// Malformed JSON
interface MalformedJsonErrorMessage {
  type: "error";
  message: "Malformed JSON payload";
  details: string;
}

// Union type for all error messages
type ErrorMessage = ValidationErrorMessage | MalformedJsonErrorMessage;
```

### Union of All Server Messages

```typescript
type ServerMessage = StatusMessage | ResultMessage | ErrorMessage;
```

---

## Quick Start Example (JavaScript)

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onopen = () => {
  ws.send(JSON.stringify({
    code: 'public class Foo { public void bar() { System.out.println("Hello"); } }',
    user_instruction: "Rename the class to Baz"
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.type) {
    case "status":
      console.log(`[${msg.role}] ${msg.content}`);
      break;
    case "result":
      console.log("Refactored code:", msg.code);
      console.log("Complexity:", msg.complexity);
      console.log("Insights:", msg.insights);
      break;
    case "error":
      console.error("Error:", msg.message, msg.details);
      break;
  }
};
```
