"""
Tool-Based Generator Test — <edit> blocks vs full generation.
Model outputs targeted line edits. Orchester applies deterministically.
Full logging of ALL intermediate outputs.
"""
import asyncio
import json
import re
import sys
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.utils.formatters import format_plan_for_generator
from tests.model.harness import ModelTestHarness


# ============================================================
# TOOL-BASED PROMPT
# ============================================================

TOOL_PROMPT = """### ROLE
Edit the base code by replacing ONLY the lines that must change.
Every line you don't touch stays exactly as-is.

### FORMAT
For EACH individual change:

<edit match="EXACT ORIGINAL LINE">
EXACT REPLACEMENT LINE
</edit>

To add a NEW line without removing anything:
<add after="EXACT ORIGINAL LINE" position="before|after">
NEW LINE TO INSERT
</add>

### RULES
- One <edit> block = ONE line changed. Multiple changes = multiple blocks.
- Each "match" must be a SINGLE line — never match a method signature.
- The replacement must be close to the original — change only what differs.
- Lines NOT in any block stay EXACTLY as the original.
- Do NOT add validation, null checks, or throws unless instructed.

### EXAMPLE — RENAME (4 small edits)
Original:
  1: public int findJudge(int n, int[][] trust) {
  2:     int[] trustCounts = new int[n + 1];
  3:     for (int[] t : trust) {
  4:         trustCounts[t[0]]--;
  5:         trustCounts[t[1]]++;
  6:     }
  7:     for (int i = 1; i <= n; i++) if (trustCounts[i] == n - 1) return i;
  8:     return -1;
  9: }

Instruction: Rename trustCounts to trustScores

<edit match="int[] trustCounts = new int[n + 1];">
int[] trustScores = new int[n + 1];
</edit>
<edit match="        trustCounts[t[0]]--;">
        trustScores[t[0]]--;
</edit>
<edit match="        trustCounts[t[1]]++;">
        trustScores[t[1]]++;
</edit>
<edit match="    for (int i = 1; i <= n; i++) if (trustCounts[i] == n - 1) return i;">
    for (int i = 1; i <= n; i++) if (trustScores[i] == n - 1) return i;
</edit>

### EXAMPLE — EXTRACT CONSTANT (add + edit)
Original:
  1: public double calculateArea(double r) { return 3.14159 * r * r; }

Instruction: Extract 3.14159 into PI constant

<add after="public double calculateArea(double r) { return 3.14159 * r * r; }" position="before">
private static final double PI = 3.14159;
</add>
<edit match="public double calculateArea(double r) { return 3.14159 * r * r; }">
public double calculateArea(double r) { return PI * r * r; }
</edit>

### ANTI-PATTERN — NEVER DO THIS
Replacing the entire method in one big block:
<edit match="void process(String s) {">
void process(String s) {
    if (s == null) throw...;
    doWork(s);
}
</edit>
This is WRONG. Use multiple small <edit> blocks, one per changed line.

### NEVER ADD THESE
- if (* == null) checks
- throws Exception on methods
- public / static modifiers that weren't in the original
- Extra methods, fields, or variables not in the instructions"""

# Generate with Line Numbers Added

FORMATTED_CODE_TEMPLATE = """Original code with line numbers for reference:
{numbered}

Instructions:
{plan_text}

Output <edit> blocks now. Match the EXACT text from the original to replace."""


def format_code_with_numbers(code: str) -> str:
    """Add line numbers to code for model reference."""
    import textwrap
    lines = code.split('\n')
    return '\n'.join(f"{i+1:>3}: {line}" for i, line in enumerate(lines))


def apply_content_edits(original_code: str, edit_text: str) -> tuple:
    """Apply <edit match=\"...\"> and <add> blocks. Returns (result, edit_count, add_count, errors)."""
    lines = original_code.split('\n')
    
    # Extract <edit> blocks
    edits = re.findall(r'<edit match="(.*?)">\n(.*?)</edit>', edit_text, re.DOTALL)
    # Extract <add> blocks
    adds = re.findall(r'<add after="(.*?)" position="(before|after)">\n(.*?)</add>', edit_text, re.DOTALL)
    
    if not edits and not adds:
        return original_code, 0, 0, ["No <edit> or <add> blocks found"]
    
    errors = []
    total_edit_count = len(edits)
    total_add_count = len(adds)
    
    # Apply ADD blocks first (insertions don't change line indices for edits)
    # Process from bottom to top to preserve indices
    for match_text, position, replacement in reversed(adds):
        match_clean = match_text.strip()
        replacement_clean = replacement.strip()
        
        found_idx = None
        for i, line in enumerate(lines):
            if match_clean == line.strip() or match_clean in line.strip():
                found_idx = i
                break
        
        if found_idx is None:
            errors.append(f"ADD: Could not find match for: '{match_clean[:50]}'")
            continue
        
        replacement_lines = replacement_clean.split('\n')
        if position == "before":
            for rl in reversed(replacement_lines):
                lines.insert(found_idx, rl)
        else:
            for rl in replacement_lines:
                lines.insert(found_idx + 1, rl)
    
    # Apply EDIT blocks — each replaces ONE line
    for match_text, replacement in reversed(edits):
        match_clean = match_text.strip()
        replacement_clean = replacement.strip()
        
        # Remove trailing semicolons for flexible matching
        match_flex = match_clean.rstrip(';').strip()
        
        found_idx = None
        for i, line in enumerate(lines):
            line_flex = line.strip().rstrip(';').strip()
            if match_clean == line.strip() or match_flex == line_flex:
                found_idx = i
                break
        
        if found_idx is None:
            # Fuzzy: match by key words ignoring whitespace differences
            match_key = ' '.join(match_flex.split()[:3])
            for i, line in enumerate(lines):
                line_key = ' '.join(line.strip().split()[:3])
                if match_key == line_key:
                    found_idx = i
                    break
        
        if found_idx is None:
            errors.append(f"EDIT: Could not find: '{match_clean[:50]}'")
            continue
        
        # Replace ONE line with replacement
        replacement_lines = replacement_clean.split('\n')
        if len(replacement_lines) == 1:
            lines[found_idx] = replacement_lines[0]
        else:
            # Multi-line replacement — replace the matched line with all replacement lines
            lines[found_idx:found_idx+1] = replacement_lines
    
    result = '\n'.join(lines)
    return result, total_edit_count, total_add_count, errors


# FULL GENERATION PROMPT (comparison baseline)
FULL_PROMPT = """### ROLE
Output ONLY the refactored code wrapped in <code> tags. No explanation.

<code>
public class X { ... }
</code>"""


# ============================================================
# TEST CASES
# ============================================================

CASES = [
    {
        "name": "tool_flatten_simple",
        "intent": "FLATTEN_CONDITIONAL",
        "code": """void process(String s) {
    if (s != null) {
        if (!s.isEmpty()) {
            doWork(s);
        } else {
            throw new IllegalArgumentException("input empty");
        }
    } else {
        throw new IllegalArgumentException("input null");
    }
}""",
        "plan": {
            "target_class": "",
            "ast_mutations": [{
                "action": "MODIFY_METHOD", "target": "process",
                "details": {
                    "modifiers": [], "type": "void",
                    "parameters": [{"type": "String", "name": "s"}],
                    "logic_changes": ["Flatten nested ifs to guard clauses"],
                    "body_abstract": "Move each invalid condition to method top as guard clause. All exception messages must match exactly."
                }
            }]
        }
    },
    {
        "name": "tool_flatten_dp",
        "intent": "FLATTEN_CONDITIONAL",
        "code": """public int minDistance(String word1, String word2) {
    int m = word1.length(), n = word2.length();
    int[][] dp = new int[m+1][n+1];
    for(int i = 0; i <= m; i++) {
        for(int j = 0; j <= n; j++) {
            if(i == 0 || j == 0) dp[i][j] = i + j;
            else if(word1.charAt(i-1) == word2.charAt(j-1)) dp[i][j] = dp[i-1][j-1];
            else dp[i][j] = 1 + Math.min(dp[i-1][j], dp[i][j-1]);
        }
    }
    return dp[m][n];
}""",
        "plan": {
            "target_class": "",
            "ast_mutations": [{
                "action": "MODIFY_METHOD", "target": "minDistance",
                "details": {
                    "modifiers": [], "type": "int",
                    "parameters": [{"type": "String", "name": "word1"}, {"type": "String", "name": "word2"}],
                    "logic_changes": ["Flatten nested for-loops and if-statements"],
                    "body_abstract": "Invert each nested condition into a guard clause at method top"
                }
            }]
        }
    },
    {
        "name": "tool_rename",
        "intent": "RENAME_SYMBOL",
        "code": """public int findJudge(int n, int[][] trust) {
    int[] trustCounts = new int[n + 1];
    for (int[] t : trust) {
        trustCounts[t[0]]--;
        trustCounts[t[1]]++;
    }
    for (int i = 1; i <= n; i++) if (trustCounts[i] == n - 1) return i;
    return -1;
}""",
        "plan": {
            "target_class": "",
            "ast_mutations": [{
                "action": "RENAME_SYMBOL", "target": "trustCounts",
                "details": {"body_abstract": "Rename trustCounts to trustScores everywhere",
                    "modifiers": [], "type": "", "parameters": [],
                    "logic_changes": ["Rename trustCounts to trustScores"]}
            }, {
                "action": "MODIFY_METHOD", "target": "findJudge",
                "details": {"body_abstract": "Update findJudge to use trustScores",
                    "modifiers": [], "type": "", "parameters": [],
                    "logic_changes": ["Update references to trustScores"]}
            }]
        }
    },
    {
        "name": "tool_decompose",
        "intent": "DECOMPOSE_CONDITIONAL",
        "code": """boolean ok(int a) {
    if (a >= 18 && a <= 65) return true;
    return false;
}""",
        "plan": {
            "target_class": "",
            "ast_mutations": [
                {"action": "ADD_FIELD", "target": "isAdult", "details": {"modifiers": [], "type": "boolean", "parameters": [], "logic_changes": [], "body_abstract": "Declare isAdult = a >= 18"}},
                {"action": "ADD_FIELD", "target": "notRetired", "details": {"modifiers": [], "type": "boolean", "parameters": [], "logic_changes": [], "body_abstract": "Declare notRetired = a <= 65"}},
                {"action": "MODIFY_METHOD", "target": "ok", "details": {"modifiers": [], "type": "", "parameters": [], "logic_changes": ["Use booleans in condition"], "body_abstract": "Declare booleans, assign conditions, use in if"}},
            ]
        }
    },
    {
        "name": "tool_consolidate",
        "intent": "CONSOLIDATE_CONDITIONAL",
        "code": """String f(int x) {
    if (x == 1) return "a";
    if (x == 2) return "a";
    return "b";
}""",
        "plan": {
            "target_class": "",
            "ast_mutations": [{
                "action": "MODIFY_METHOD", "target": "f",
                "details": {"body_abstract": "Combine duplicate branches with ||",
                    "modifiers": [], "type": "", "parameters": [],
                    "logic_changes": ["Merge if(x==1) and if(x==2) into one check"]}
            }]
        }
    },
]


# ============================================================
# APPLY TOOL EDITS
# ============================================================

def apply_tool_edits(original_code: str, edit_text: str) -> tuple:
    """Apply <edit> blocks to original code. Returns (result, edit_count, errors)."""
    lines = original_code.split('\n')
    edits = re.findall(r'<edit start="(\d+)" end="(\d+)">\n(.*?)</edit>', edit_text, re.DOTALL)
    
    if not edits:
        return original_code, 0, ["No <edit> blocks found in output"]
    
    # Sort edits by position (apply from bottom to top so line numbers don't shift)
    edits_sorted = sorted(edits, key=lambda e: int(e[0]), reverse=True)
    errors = []
    result_lines = lines[:]
    
    for start_str, end_str, replacement in edits_sorted:
        start = int(start_str)
        end = int(end_str)
        replacement_clean = replacement.strip()
        
        if start < 1:
            errors.append(f"Invalid start line: {start}")
            continue
        if end > len(lines):
            errors.append(f"End line {end} exceeds file length {len(lines)}")
            continue
        if start > end:
            errors.append(f"Start line {start} > end line {end}")
            continue
        
        replacement_lines = replacement_clean.split('\n')
        result_lines[start-1:end] = replacement_lines
    
    result = '\n'.join(result_lines)
    return result, len(edits), errors


# ============================================================
# SIMPLE CHECKS
# ============================================================

def check_syntax(code: str) -> bool:
    try:
        import javalang
        wrapped = f"class __W__ {{ {code} }}" if "class" not in code else code
        javalang.parse.parse(wrapped)
        return True
    except Exception:
        return False

def check_throws_added(original: str, generated: str) -> List[str]:
    orig_throws = set(re.findall(r'throws\s+(\w+Exception)', original))
    gen_throws = set(re.findall(r'throws\s+(\w+Exception)', generated))
    return list(gen_throws - orig_throws)

def check_null_checks_added(original: str, generated: str) -> List[str]:
    orig_nulls = len(re.findall(r'if\s*\(\s*\w+\s*==\s*null\s*\)', original))
    gen_nulls = len(re.findall(r'if\s*\(\s*\w+\s*==\s*null\s*\)', generated))
    return [f"+{gen_nulls-orig_nulls} null checks"] if gen_nulls > orig_nulls else []

def get_methods(code: str) -> set:
    return set(re.findall(r'(?:public|private|protected)?\s*\w+\s+(\w+)\s*\(', code))


# ============================================================
# RUN CASE
# ============================================================

async def run_case(harness, case, use_tool):
    label = "TOOL" if use_tool else "FULLGEN"
    name = case["name"]
    code = case["code"]
    plan = case["plan"]
    plan_text = format_plan_for_generator(plan, code)
    
    if use_tool:
        numbered_code = format_code_with_numbers(code)
        user_prompt = FORMATTED_CODE_TEMPLATE.format(
            numbered=numbered_code,
            plan_text=plan_text
        )
        system = TOOL_PROMPT
    else:
        user_prompt = plan_text
        system = FULL_PROMPT
    
    result = await harness.generate(system, user_prompt, temp=0.1, max_tokens=3072)
    raw_output = result["content"]
    
    if use_tool:
        final_code, edit_count, add_count, edit_errors = apply_content_edits(code, raw_output)
        return {
            "case": name, "mode": label, "intent": case["intent"],
            "raw_output": raw_output,
            "final_code": final_code,
            "edit_count": edit_count,
            "add_count": add_count,
            "edit_errors": edit_errors,
            "syntax_ok": check_syntax(final_code),
            "new_throws": check_throws_added(code, final_code),
            "new_nulls": check_null_checks_added(code, final_code),
            "orig_methods": get_methods(code),
            "refac_methods": get_methods(final_code),
            "dropped_methods": get_methods(code) - get_methods(final_code),
            "duration": result["duration"],
        }
    else:
        # Full generation
        code_match = re.search(r'<code>(.*?)</code>', raw_output, re.DOTALL)
        final_code = code_match.group(1).strip() if code_match else "NO CODE"
        return {
            "case": name, "mode": label, "intent": case["intent"],
            "raw_output": raw_output[:500],
            "final_code": final_code,
            "syntax_ok": check_syntax(final_code),
            "new_throws": check_throws_added(code, final_code),
            "new_nulls": check_null_checks_added(code, final_code),
            "orig_methods": get_methods(code),
            "refac_methods": get_methods(final_code),
            "dropped_methods": get_methods(code) - get_methods(final_code),
            "duration": result["duration"],
        }


# ============================================================
# MAIN
# ============================================================

async def main():
    print("=" * 70)
    print("TOOL-BASED GENERATOR TEST — <edit> blocks vs full generation")
    print(f"{len(CASES)} cases × 2 modes = {len(CASES)*2} runs")
    print("=" * 70)

    h_gen = ModelTestHarness("generator")
    await h_gen.load_model()
    
    all_results = []
    
    for mode, use_tool in [("TOOL", True), ("FULLGEN", False)]:
        print(f"\n{'='*70}")
        print(f"MODE: {mode}")
        print(f"{'='*70}")
        
        for case in CASES:
            r = await run_case(h_gen, case, use_tool)
            all_results.append(r)
            
            if use_tool:
                print(f"\n--- {r['case']} ({r['intent']}) ---")
                print(f"  RAW OUTPUT ({len(r['raw_output'])} chars):")
                for line in r['raw_output'].split('\n')[:20]:
                    print(f"    {line}")
            else:
                print(f"\n--- {r['case']} ({r['intent']}) ---")
                print(f"  FINAL CODE ({len(r['final_code'])} chars):")
                for line in r['final_code'].split('\n')[:15]:
                    print(f"    {line}")
            
            print(f"\n  SYNTAX: {'✓' if r['syntax_ok'] else '✗'} | NEW THROWS: {r['new_throws']} | NEW NULLS: {r['new_nulls']}")
            print(f"  DROPPED METHODS: {r['dropped_methods']} | DURATION: {r['duration']:.1f}s")
            
            if use_tool:
                print(f"  EDITS: {r['edit_count']} edits + {r['add_count']} adds | ERRORS: {r.get('edit_errors', [])}")
    
    await h_gen.unload_model()
    
    # COMPARISON
    print(f"\n{'='*70}")
    print("COMPARISON")
    print(f"{'='*70}")
    print(f"{'Case':<30} {'Mode':<8} {'Syntax':<7} {'NewThrows':<12} {'Dropped':<10} {'Duration':<8}")
    print("-" * 80)
    
    for r in all_results:
        throws_str = str(r['new_throws'][:30]) if r['new_throws'] else "none"
        dropped_str = str(r['dropped_methods']) if r['dropped_methods'] else "none"
        print(f"{r['case']:<30} {r['mode']:<8} {'✓' if r['syntax_ok'] else '✗':<7} {throws_str:<12} {dropped_str:<10} {r['duration']:.1f}s")

    # Per-case winner
    print(f"\n{'Case':<30} {'TOOL':<25} {'FULLGEN':<25} {'Winner'}")
    print("-" * 90)
    for case in CASES:
        name = case["name"]
        t = next((r for r in all_results if r["case"] == name and r["mode"] == "TOOL"), None)
        f = next((r for r in all_results if r["case"] == name and r["mode"] == "FULLGEN"), None)
        if t and f:
            t_score = (1 if t["syntax_ok"] else 0) + (1 if not t["new_throws"] else 0) + (1 if not t["dropped_methods"] else 0)
            f_score = (1 if f["syntax_ok"] else 0) + (1 if not f["new_throws"] else 0) + (1 if not f["dropped_methods"] else 0)
            winner = "TOOL" if t_score > f_score else ("FULLGEN" if f_score > t_score else "TIE")
            print(f"{name:<30} score={t_score} (syntax:{'✓' if t['syntax_ok'] else '✗'} throws={'✓' if not t['new_throws'] else '✗'} methods={'✓' if not t['dropped_methods'] else '✗'}) | score={f_score} ({'✓' if f['syntax_ok'] else '✗'} {'✓' if not f['new_throws'] else '✗'} {'✓' if not f['dropped_methods'] else '✗'}) | {winner}")

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = f"tests/results/tool_compare_{ts}.json"
    with open(path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
