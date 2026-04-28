# Frontend Human Readable Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the backend to parse the structured JSON outputs from the LLM agents (Planner, Generator, Judge, Validator) and send them as formatted, human-readable markdown to the frontend, so the UI can display better status updates.

**Architecture:** We will create a new utility module `app/utils/formatters.py` that takes the raw structured JSON strings logged during orchestration and converts them into nice Markdown blocks. Then, we will integrate this into the `Orchestrator._notify` method so that when a status update has structured `content`, the human-readable version is appended to the `message` sent over the WebSocket to the frontend.

**Tech Stack:** Python, FastAPI, Pydantic

---

### Task 1: Create the Formatters Utility

**Files:**
- Create: `app/utils/formatters.py`

- [ ] **Step 1: Write the formatter logic**

```python
import json
from typing import Optional

def format_agent_output(message: str, content: Optional[str]) -> str:
    """
    Parses structured JSON content from agents and formats it into
    human-readable Markdown. Returns the original message if no content
    or if parsing fails.
    """
    if not content:
        return message

    try:
        data = json.loads(content)
    except Exception:
        return message  # Fallback to just the message if not JSON

    formatted_md = ""

    # 1. Intent Packet Formatting
    if isinstance(data, dict) and "specific_intent" in data and "refactor_category" in data:
        formatted_md = f"**Category:** `{data.get('refactor_category')}`\n"
        formatted_md += f"**Intent:** `{data.get('specific_intent')}`\n"
        
        anchor = data.get("scope_anchor", {})
        if anchor:
            formatted_md += f"**Target Unit:** `{anchor.get('unit_type')}`\n"
            if anchor.get('class'):
                formatted_md += f"**Target Class:** `{anchor.get('class')}`\n"
            if anchor.get('member'):
                formatted_md += f"**Target Member:** `{anchor.get('member')}`\n"

    # 2. AST Modification Plan Formatting
    elif isinstance(data, dict) and "ast_mutations" in data:
        target_class = data.get("target_class", "Unknown Class")
        formatted_md = f"**Target Class:** `{target_class}`\n\n**Mutations:**\n"
        for mut in data.get("ast_mutations", []):
            action = mut.get("action", "")
            target = mut.get("target", "")
            formatted_md += f"- **{action}** on `{target}`\n"
            details = mut.get("details", {})
            if details:
                strategy = details.get("refactor_strategy")
                if strategy:
                    formatted_md += f"  - Strategy: `{strategy}`\n"
                logic = details.get("logic_changes", [])
                for change in logic:
                    formatted_md += f"  - *{change}*\n"

    # 3. Validation Feedback Formatting
    elif isinstance(data, dict) and "findings" in data and "total_faults" in data:
        formatted_md = f"**Total Faults:** {data.get('total_faults')} (Recoverable: {'Yes' if data.get('is_recoverable') else 'No'})\n\n"
        for finding in data.get("findings", []):
            tier = finding.get("failure_tier", "")
            formatted_md += f"**[{tier}]**\n"
            error = finding.get("error_report", {})
            if error.get("message"):
                formatted_md += f"> {error.get('message')}\n"
            if error.get("faulty_node"):
                formatted_md += f"- Node: `{error.get('faulty_node')}`\n"
            if finding.get("recovery_hint"):
                formatted_md += f"- *Hint:* {finding.get('recovery_hint')}\n"
            formatted_md += "\n"

    # 4. Structural Auditor Verdict Formatting
    elif isinstance(data, dict) and "verdict" in data and "issues" in data:
        verdict = data.get("verdict")
        icon = "✅" if verdict == "ACCEPT" else "❌"
        formatted_md = f"**Verdict:** {icon} {verdict}\n"
        issues = data.get("issues", [])
        if issues:
            formatted_md += "\n**Issues:**\n"
            for issue in issues:
                formatted_md += f"- {issue}\n"

    # Fallback for generic JSON dict
    elif isinstance(data, dict):
        formatted_md = "```json\n" + json.dumps(data, indent=2) + "\n```"
    elif isinstance(data, list):
        formatted_md = "```json\n" + json.dumps(data, indent=2) + "\n```"

    if formatted_md:
        return f"{message}\n\n{formatted_md}"
    
    return message
```

---

### Task 2: Integrate Formatters into Orchestrator

**Files:**
- Modify: `app/modules/orchestrator.py`

- [ ] **Step 1: Import the formatter**

Add the import at the top of the file:
```python
from app.utils.formatters import format_agent_output
```

- [ ] **Step 2: Update the `_notify` method**

Modify `_notify` to apply the formatting before broadcasting via `send_status`. Do not change the DB persistence which still needs the raw JSON string `content`.

```python
    async def _notify(
        self,
        client: ClientConnection,
        role: Role,
        message: str,
        content: Optional[str] = None,
        phase: Optional[int] = None,
        outer_loop: int = 0,
        inner_loop: int = 0,
    ) -> None:
        """Helper to print to terminal, persist to DB, and notify frontend."""
        print(f"[{role}] {message}")

        # Persist the log entry to the database in real-time
        self.db.log_status(
            session_id=client.id,
            role=role.value,
            status=message,
            content=content,
            phase=phase,
            outer_loop=outer_loop,
            inner_loop=inner_loop,
        )

        formatted_message = format_agent_output(message, content)
        await client.send_status(role=role, content=formatted_message)
```
