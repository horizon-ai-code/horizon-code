# Horizon Code — Frontend API Documentation

The backend exposes:

- A **WebSocket** endpoint for real-time refactoring (`ws://localhost:8000/ws`)
- A **REST** endpoint for fetching refactoring history (`GET /api/history`)
- A **REST** endpoint for fetching details of a specific refactoring (`GET /api/history/{history_id}`)
- A **REST** endpoint for deleting a specific refactoring history record (`DELETE /api/history/{history_id}`)

---

## 1. Interaction Flow


- [WebSocket API](#websocket-api)
    - [Connection](#connection)
    - [Client → Server Messages](#client--server-messages)
        - [RefactorRequest](#refactorrequest)
    - [Server → Client Messages](#server--client-messages)
        - [Status Update](#status-update)
        - [Result](#result)
        - [Error](#error)
    - [Orchestration Flow](#orchestration-flow)
- [REST API](#rest-api)
    - [GET /api/history](#get-apihistory)
    - [GET /api/history/{history_id}](#get-apihistoryhistory_id)
    - [DELETE /api/history/{history_id}](#delete-apihistoryhistory_id)

- [Enums & Constants](#enums--constants)
- [Data Structures Reference](#data-structures-reference)

---

## WebSocket API

### Connection

1. Open a WebSocket connection to `ws://<host>:8000/ws`.
2. The server accepts the connection immediately — no authentication or handshake payload is required.
3. The connection stays alive until either side disconnects.
4. You can send multiple requests over the same connection; each one triggers a full orchestration cycle.

### CORS

The following origins are allowed:

| Origin                  |
| ----------------------- |
| `http://localhost:3000` |
| `http://127.0.0.1:3000` |

---

## Client → Server Messages

### `RefactorRequest`

Every message the client sends **must** be a JSON object with this exact shape:

```jsonc
{
    "code": "<string>", // The Java source code to refactor
    "user_instruction": "<string>", // Natural-language instruction describing the desired changes
}
```

| Field              | Type     | Required | Description                                                |
| ------------------ | -------- | -------- | ---------------------------------------------------------- |
| `code`             | `string` | ✅       | The raw Java code snippet the user wants to refactor.      |
| `user_instruction` | `string` | ✅       | A natural-language description of the desired refactoring. |

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

The server sends four types of messages, distinguished by the `"type"` field.
1. [`connection_id`](#connection_id) — Sent when the server receives a new orchestration request.
2. [`status`](#status-update) — Sent multiple times during the process.
3. [`result`](#result) — Sent once at the end.
4. [`error`](#error) — Sent if the client's payload is invalid.

---

### connection_id

Sent **once** right after the server validates a new `RefactorRequest` and before orchestration begins. This ID identifies the current session and is used for history tracking.

```jsonc
{
    "type": "connection_id",
    "id": "<string>" // A unique UUID for the current connection
}
```

| Field  | Type     | Description                                      |
| ------ | -------- | ------------------------------------------------ |
| `type` | `string` | Always `"connection_id"`.                        |
| `id`   | `string` | The unique session identifier (UUID v4 string). |

---

### Status Update

Sent **multiple times** during orchestration to report progress from each agent.

```jsonc
{
    "type": "status",
    "role": "<Role>", // Which agent is reporting — see Role enum below
    "content": "<string>", // Human-readable status message
}
```

| Field     | Type     | Description                                                                               |
| --------- | -------- | ----------------------------------------------------------------------------------------- |
| `type`    | `string` | Always `"status"`.                                                                        |
| `role`    | `Role`   | The agent currently active. One of: `"Planner"`, `"Generator"`, `"Judge"`, `"Validator"`. |
| `content` | `string` | A short, human-readable progress description.                                             |

#### Status messages you can expect (in typical order)

| #   | `role`      | `content` (typical)                                      |
| --- | ----------- | -------------------------------------------------------- |
| 1   | `Planner`   | `"Generating plan & instructions..."`                    |
| 2   | `Planner`   | _The generated plan text_                                |
| 3   | `Generator` | `"Refactoring code..."`                                  |
| 4   | `Generator` | `"Refactor draft finished."`                             |
| 5   | `Validator` | `"Checking syntax..."`                                   |
| 6a  | `Validator` | `"Syntax passed."` _(happy path — skip to step 9)_       |
| 6b  | `Validator` | `"Errors detected."` _(enters fix loop)_                 |
| 7   | `Judge`     | `"Interpreting errors & generating fix instructions..."` |
| 8   | `Judge`     | _The error interpretation text_                          |
|     |             | _(loops back to step 1 with corrected instructions)_     |
| 9   | `Validator` | `"Checking complexity..."`                               |
| 10  | `Validator` | `"Complexity measured."`                                 |
| 11  | `Judge`     | `"Generating insights..."`                               |

> After step 11, the next message will be a [`result`](#result).

---

### Result

Sent **once** at the end of a successful orchestration cycle.

```jsonc
{
  "type": "result",
  "id": "<string>",          // The unique session ID for this result
  "code": "<string>",          // The final refactored Java code
  "complexity": <int | null>,  // Cyclomatic complexity score, or null if empty
  "insights": "<string>"       // AI-generated analysis of the refactoring
}
```

| Field        | Type          | Description                                                                          |
| ------------ | ------------- | ------------------------------------------------------------------------------------ |
| `type`       | `string`      | Always `"result"`.                                                                   |
| `id`         | `string`      | The unique session identifier (UUID v4 string).                                     |
| `code`       | `string`      | The final, syntax-validated, refactored Java code.                                   |
| `complexity` | `int \| null` | Cyclomatic complexity score of the refactored code. `null` if the snippet was empty. |
| `insights`   | `string`      | A detailed AI-generated analysis comparing the original and refactored code.         |

#### Example

```json
{
    "type": "result",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "code": "public class Baz {\n  public void bar() {\n    printHello();\n  }\n  private void printHello() {\n    System.out.println(\"Hello\");\n  }\n}",
    "complexity": 1,
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
    "details": [
        // Pydantic validation error list
        {
            "type": "<string>",
            "loc": ["<field_name>"],
            "msg": "<string>",
            "input": "<value>",
        },
    ],
}
```

#### Malformed JSON

```jsonc
{
    "type": "error",
    "message": "Malformed JSON payload",
    "details": "<string>", // Description of the JSON parsing error
}
```

| Field     | Type              | Description                                                    |
| --------- | ----------------- | -------------------------------------------------------------- |
| `type`    | `string`          | Always `"error"`.                                              |
| `message` | `string`          | Either `"Invalid data format"` or `"Malformed JSON payload"`.  |
| `details` | `array \| string` | Pydantic error array (validation) or error string (malformed). |

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

## REST API

### `GET /api/history`

Retrieves a list of unique identifiers for all refactoring sessions in the history.

**Endpoint:** `GET http://localhost:8000/api/history`

**Query Parameters:** None

**Response:** HTTP 200 OK

```jsonc
[
  "550e8400-e29b-41d4-a716-446655440000", // Unique history record UUID
  "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  // ... more IDs
]
```

| Field | Type     | Description                                     |
| ----- | -------- | ----------------------------------------------- |
| `item` | `string` | The unique session identifier (UUID v4 string). |

#### Example Request

```bash
curl http://localhost:8000/api/history
```

#### Example Response

```json
[
    "550e8400-e29b-41d4-a716-446655440000",
    "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
]
```


---

### `GET /api/history/{history_id}`

Retrieves the full details of a specific refactoring session by its unique ID, including all intermediate orchestration logs.

**Endpoint:** `GET http://localhost:8000/api/history/{history_id}`

**Path Parameters:**

| Parameter    | Type     | Description                                           |
| ------------ | -------- | ----------------------------------------------------- |
| `history_id` | `string` | The unique UUID of the refactoring session to fetch. |

**Response:** HTTP 200 OK

```jsonc
{
  "id": "<string>",                 // Unique history record UUID
  "user_instruction": "<string>",   // The user's refactoring instruction
  "original_code": "<string>",      // The original Java code
  "refactored_code": "<string>",    // The refactored Java code (null if in-progress)
  "insights": "<string>",          // The generated insights (null if in-progress)
  "complexity": <integer | null>,  // Cyclomatic complexity score
  "created_at": "<timestamp>",     // When the session started (ISO 8601)
  "logs": [                        // Array of orchestration steps
    {
       "id": <integer>,
       "role": "<Role>",
       "status": "<string>",       // Human-readable status message
       "content": "<string | null>", // The actual generated data (plan, code, etc.)
       "created_at": "<timestamp>"
    }
  ]
}
```

**Errors:**

- **404 Not Found**: If no refactoring session with the given ID exists.

#### Example Request

```bash
curl http://localhost:8000/api/history/550e8400-e29b-41d4-a716-446655440000
```

#### Example Response

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_instruction": "Rename class to Baz.",
    "original_code": "public class Foo {}",
    "refactored_code": "public class Baz {}",
    "insights": "Renamed class successfuly.",
    "complexity": 1,
    "created_at": "2026-04-03T22:30:45Z",
    "logs": [
        {
            "id": 1,
            "role": "Planner",
            "status": "Generating plan...",
            "content": "Rename class to Baz",
            "created_at": "2026-04-03T22:30:46Z"
        }
    ]
}
```

### `DELETE /api/history/{history_id}`

Deletes a specific refactoring session from the history.

**Endpoint:** `DELETE http://localhost:8000/api/history/{history_id}`

**Path Parameters:**

| Parameter    | Type     | Description                                           |
| ------------ | -------- | ----------------------------------------------------- |
| `history_id` | `string` | The unique UUID of the refactoring session to delete. |

**Response:** HTTP 200 OK

```json
{
  "status": "history_deleted",
  "message": "Refactor history 550e8400-e29b-41d4-a716-446655440000 deleted"
}
```

**Errors:**

- **404 Not Found**: If no refactoring session with the given ID exists.

#### Example Request

```bash
curl -X DELETE http://localhost:8000/api/history/550e8400-e29b-41d4-a716-446655440000
```


## Enums & Constants

### `Role`

Identifies which agent is active. Used in `status` messages.

| Value         | Description                                            |
| ------------- | ------------------------------------------------------ |
| `"Planner"`   | Analyzes code and generates a refactoring plan.        |
| `"Generator"` | Writes the refactored code from instructions.          |
| `"Judge"`     | Interprets errors or generates post-refactor insights. |
| `"Validator"` | Validates syntax and measures complexity.              |

### `Message Types`

| `type` value      | Direction       | Description                       |
| ----------------- | --------------- | --------------------------------- |
| `"connection_id"` | Server → Client | Unique session ID notification.   |
| `"status"`         | Server → Client | Progress update from an agent.    |
| `"result"`         | Server → Client | Final refactored code + insights. |
| `"error"`          | Server → Client | Validation/parse error response.  |

---

- [GET /api/history](#get-apihistory) — List of all session IDs.
- [GET /api/history/{history_id}](#get-apihistoryhistory_id) — Full session details with **bundled orchestration logs**.
- [DELETE /api/history/{history_id}](#delete-apihistoryhistory_id) — Permanently removes a session from history.

---

## Data Structures Reference

### Request (Client → Server)

```typescript
interface RefactorRequest {
    code: string;
    user_instruction: string;
}
```

### Connection ID (Server → Client)

```typescript
interface ConnectionIdMessage {
    type: "connection_id";
    id: string;
}
```

### Status Message (Server → Client)

```typescript
interface StatusMessage {
    type: "status";
    role: Role;
    content: string;
}
```

### Result Message (Server → Client)

```typescript
interface ResultMessage {
    type: "result";
    id: string;
    code: string;
    complexity: number | null;
    insights: string;
}
```

### History Detail (Server → Client)

```typescript
interface RefactorHistoryDetail {
    id: string;
    user_instruction: string;
    original_code: string;
    refactored_code: string | null;
    insights: string | null;
    complexity: number | null;
    created_at: string; // ISO 8601
    logs: OrchestrationLog[]; // Bundled logs
}

interface OrchestrationLog {
    id: number;
    session: string; // The parent session UUID (string)
    role: Role;
    status: string;
    content: string | null;
    created_at: string; // ISO 8601
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
type ServerMessage = ConnectionIdMessage | StatusMessage | ResultMessage | ErrorMessage;
```

---

## Quick Start Example (JavaScript)

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onopen = () => {
    ws.send(
        JSON.stringify({
            code: 'public class Foo { public void bar() { System.out.println("Hello"); } }',
            user_instruction: "Rename the class to Baz",
        }),
    );
};

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    switch (msg.type) {
        case "connection_id":
            console.log("Unique Session ID:", msg.id);
            break;
        case "status":
            console.log(`[${msg.role}] ${msg.content}`);
            break;
        case "result":
            console.log("Session ID:", msg.id);
            console.log("Refactored code:", msg.code);
            console.log("Complexity score:", msg.complexity);
            console.log("Insights:", msg.insights);
            break;
        case "error":
            console.error("Error:", msg.message, msg.details);
            break;
    }
};
```

