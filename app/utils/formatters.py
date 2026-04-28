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