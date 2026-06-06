"""
Surgical analysis — does TWO-STEP Generator follow its own analysis?
Full logging of analysis text + generated code for 3 representative cases.
"""
import asyncio, json, re, sys
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.utils.formatters import format_plan_for_generator
from tests.model.harness import ModelTestHarness


ANALYSIS_PROMPT = """### ROLE
Read the instructions below. Before writing any code, describe your execution plan.

### TASK
For each instruction, state clearly:
1. What you will CREATE — exact names, whether method/field/constant
2. What you will MODIFY — existing method names, what changes you will make
3. What stays the SAME — return types, parameter names, method signatures
4. What you must ABSOLUTELY NOT DO — do not add validation, null checks,
   new exceptions, throws declarations, try/catch, extra methods

Be specific. Use exact names from the instructions.
Output only your analysis. No code, no <code> tags."""

GENERATION_PROMPT = """### ROLE
Execute your analysis EXACTLY. You already described what to do and what NOT to do.
Output ONLY the refactored code wrapped in <code> tags. No explanation, no preamble.

<code>
public class X { ... }
</code>"""

# 3 test cases — one easy, one medium, one hard
CASES = [
    {
        "name": "rename_short_judge",
        "intent": "RENAME_SYMBOL",
        "code": "public int findJudge(int n, int[][] trust) { int[] trustCounts = new int[n + 1]; for (int[] t : trust) { trustCounts[t[0]]--; trustCounts[t[1]]++; } for (int i = 1; i <= n; i++) if (trustCounts[i] == n - 1) return i; return -1; }",
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
        "name": "const_long_derangement",
        "intent": "EXTRACT_CONSTANT",
        "code": "public int findDerangement(int n) { long[] dp = new long[n + 1]; dp[2] = 1; for (int i = 3; i <= n; i++) dp[i] = (i - 1) * (dp[i - 1] + dp[i - 2]) % 1000000007; return (int) dp[n]; }",
        "plan": {
            "target_class": "",
            "ast_mutations": [{
                "action": "ADD_CONSTANT", "target": "MOD",
                "details": {"body_abstract": "Declare MOD = 1000000007", "modifiers": ["static", "final"], "type": "long", "parameters": [],
                    "logic_changes": ["Extract 1000000007 into constant MOD"]}
            }, {
                "action": "MODIFY_METHOD", "target": "findDerangement",
                "details": {"body_abstract": "Replace 1000000007 with MOD", "modifiers": [], "type": "", "parameters": [],
                    "logic_changes": ["Replace 1000000007 with MOD"]}
            }]
        }
    },
    {
        "name": "flatten_short_mindist",
        "intent": "FLATTEN_CONDITIONAL",
        "code": "public int minDistance(String word1, String word2) { int m = word1.length(), n = word2.length(); int[][] dp = new int[m+1][n+1]; for(int i = 0; i <= m; i++) { for(int j = 0; j <= n; j++) { if(i == 0 || j == 0) dp[i][j] = i + j; else if(word1.charAt(i-1) == word2.charAt(j-1)) dp[i][j] = dp[i-1][j-1]; else dp[i][j] = 1 + Math.min(dp[i-1][j], dp[i][j-1]); } } return dp[m][n]; }",
        "plan": {
            "target_class": "",
            "ast_mutations": [{
                "action": "MODIFY_METHOD", "target": "minDistance",
                "details": {"body_abstract": "Invert each nested condition into a guard clause at the method top", "modifiers": [], "type": "int", "parameters": [{"type": "String", "name": "word1"}, {"type": "String", "name": "word2"}],
                    "logic_changes": ["Flatten nested for-loops and if-statements"]}
            }]
        }
    },
]


async def surgical_case(harness: ModelTestHarness, case: Dict[str, Any]):
    name = case["name"]
    code = case["code"]
    plan = case["plan"]
    user_prompt = format_plan_for_generator(plan, code)

    print(f"\n{'='*70}")
    print(f"CASE: {name} ({case['intent']})")
    print(f"{'='*70}")

    # ========== STEP 1: ANALYSIS ==========
    print(f"\n--- STEP 1: ANALYSIS ---")
    print(f"System prompt ({len(ANALYSIS_PROMPT)} chars):")
    print(f"  {ANALYSIS_PROMPT[:200]}...")
    print(f"\nUser prompt ({len(user_prompt)} chars):")
    for line in user_prompt.split("\n")[:10]:
        print(f"  {line[:120]}")
    print(f"  ... ({len(user_prompt.split(chr(10)))} lines total)")

    await harness.clear_context()
    analysis_res = await harness.generate(
        ANALYSIS_PROMPT, user_prompt,
        temp=0.1, max_tokens=512,
    )
    analysis_text = analysis_res["content"].strip()
    
    print(f"\nMODEL'S ANALYSIS ({len(analysis_text)} chars):")
    print("-" * 60)
    for line in analysis_text.split("\n")[:25]:
        print(f"  {line}")
    if len(analysis_text.split("\n")) > 25:
        print(f"  ... ({len(analysis_text.split(chr(10)))} lines total)")

    # ========== ANALYZE ANALYSIS QUALITY ==========
    print(f"\n--- ANALYSIS QUALITY CHECK ---")
    
    # Check if analysis mentions NOT doing things
    has_not = any(w in analysis_text.lower() for w in ["must not", "do not", "should not", "cannot", "won't", "will not"])
    print(f"  Contains 'NOT' constraints: {has_not}")
    
    # Check if analysis mentions the correct targets
    targets = [m["target"] for m in plan["ast_mutations"]]
    mentions_targets = [t for t in targets if t.lower() in analysis_text.lower()]
    print(f"  Mentions plan targets: {mentions_targets} (expected {targets})")
    
    # Check if analysis mentions validation/throws
    mentions_validation = any(w in analysis_text.lower() for w in ["null", "throw", "throws", "validation", "exception", "try", "catch"])
    print(f"  Mentions validation/throws: {mentions_validation} {'⚠' if mentions_validation else '✓'}")

    # ========== STEP 2: GENERATION (NO clear_context) ==========
    print(f"\n--- STEP 2: GENERATION (KV cache preserved) ---")
    
    gen_user = user_prompt + "\n\nYOUR ANALYSIS:\n" + analysis_text
    print(f"Generation user prompt ({len(gen_user)} chars — includes analysis above)")
    
    code_res = await harness.generate(
        GENERATION_PROMPT, gen_user,
        temp=0.1, max_tokens=3072,
    )
    
    output_code = ""
    cm = re.search(r'<code>(.*?)</code>', code_res["content"], re.DOTALL)
    if cm:
        output_code = cm.group(1).strip()

    print(f"\nGENERATED CODE ({len(output_code)} chars):")
    print("-" * 60)
    for line in output_code.split("\n")[:20]:
        print(f"  {line}")
    if len(output_code.split("\n")) > 20:
        print(f"  ... ({len(output_code.split(chr(10)))} lines total)")

    # ========== CHECK: DOES MODEL FOLLOW ITS ANALYSIS? ==========
    print(f"\n--- FOLLOW-THROUGH CHECK ---")
    
    code_lower = output_code.lower()
    
    # If analysis says NOT to add validation, check if code added it
    if has_not and "must not" in analysis_text.lower():
        added_throws = re.findall(r'throws\s+\w+Exception', output_code)
        added_nulls = re.findall(r'if\s*\(\s*\w+\s*==\s*null\s*\)', output_code)
        orig_throws = re.findall(r'throws\s+\w+Exception', case["code"])
        orig_nulls = re.findall(r'if\s*\(\s*\w+\s*==\s*null\s*\)', case["code"])
        new_throws = set(added_throws) - set(orig_throws)
        new_nulls = len(added_nulls) - len(orig_nulls)
        if new_throws:
            print(f"  ✗ ADDED throws: {new_throws} (analysis said NOT to)")
        if new_nulls > 0:
            print(f"  ✗ ADDED {new_nulls} null checks (analysis said NOT to)")
        if not new_throws and new_nulls <= 0:
            print(f"  ✓ No violation of NOT constraints")

    # Check if all plan targets appear in output code
    for t in targets:
        present = t.lower() in code_lower
        print(f"  {'✓' if present else '✗'} Target '{t}' in output: {present}")

    # Check methods preserved
    orig_methods = set(re.findall(r'(?:public|private|protected)?\s*\w+\s+(\w+)\s*\(', case["code"]))
    refac_methods = set(re.findall(r'(?:public|private|protected)?\s*\w+\s+(\w+)\s*\(', output_code))
    dropped = orig_methods - refac_methods
    if dropped:
        print(f"  ✗ Methods dropped: {dropped}")
    else:
        print(f"  ✓ All methods preserved")

    print(f"\n  Duration: analysis={analysis_res['duration']:.1f}s + generation={code_res['duration']:.1f}s = {(analysis_res['duration']+code_res['duration']):.1f}s total")


async def main():
    print("SURGICAL ANALYSIS — TWO-STEP GENERATOR")
    print("=" * 70)
    
    h_gen = ModelTestHarness("generator")
    await h_gen.load_model()
    
    for case in CASES:
        await surgical_case(h_gen, case)
    
    await h_gen.unload_model()
    
    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    print(f"\n\nAnalysis complete. Log timestamp: {ts}")


if __name__ == "__main__":
    asyncio.run(main())
