"""
Two-Step Generator Test — ONE-STEP vs TWO-STEP (analysis → generate).
Extracts plans from latest orchestrator integration log.
Runs both modes, compares Phase 4 pass rates.
"""
import asyncio
import json
import re
import sys
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.modules.validator import Validator
from app.utils.formatters import format_plan_for_generator
from app.utils.types import RefactorIntent
from tests.model_tests.harness import ModelTestHarness


# ============================================================
# HARDCODED PROMPTS
# ============================================================

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


# ============================================================
# PLAN EXTRACTION
# ============================================================

def extract_plans_from_log(log_path: str) -> List[Dict[str, Any]]:
    """
    Extract code + plan from orchestrator log.
    Returns list of {name, code, plan} for each viable session.
    """
    with open(log_path) as f:
        content = f.read()

    sessions = content.split("Ph1: Baselining")

    # Test case mapping — in order from test_polish_integration.py
    case_names = [
        "polish_flatten_short_mindist",
        "polish_flatten_long_quads",
        "polish_decompose_med_nim",
        "polish_decompose_long_palindrome",
        "polish_consolidate_short_fixed",
        "polish_consolidate_long_lhs",
        "polish_const_short_box",
        "polish_const_long_derangement",
        "polish_extract_short_palindrome",
        "polish_extract_long_reformat",
        "polish_rename_short_judge",
        "polish_rename_long_paths",
        "polish_split_med_distinct",
        "polish_split_long_gray",
        "polish_extvar_med_seconds",
        "polish_extvar_long_binary",
        "polish_inlinevar_dp",
        "polish_remflag_search",
        "polish_pipeline_gray",
        "polish_inline_nim",
    ]

    plans = []
    seen = set()
    
    for sid, session_text in enumerate(sessions[1:], 1):
        gen_runs = len(re.findall(r'Code refactored', session_text))
        if gen_runs == 0:
            continue  # Skip dead sessions

        # Get intent
        intent_match = re.search(r'Intent Classified: (\w+)', session_text)
        intent = intent_match.group(1) if intent_match else "?"
        
        # Get target method from scope anchor
        member_match = re.search(r'"member":\s*"([^"]+)"', session_text)
        member = member_match.group(1) if member_match else ""
        
        # Get plan actions
        actions = re.findall(r'"action":\s*"(\w+)"', session_text)
        targets = re.findall(r'"target":\s*"([^"]+)"', session_text)
        
        # Get body_abstract for mutations
        body_abstracts = re.findall(r'"body_abstract":\s*"([^"]+)"', session_text)
        
        # Build key for dedup
        key = (intent, tuple(actions[:3]), member)
        if key in seen:
            continue
        seen.add(key)

        # Match to case name by intent + member
        case_name = f"s{sid}_{intent}_{member}"[:60]
        
        # Extract code from the session - look for Base Code or the original
        code = ""
        # The code was printed in the orchestrator — extract from first generate call
        # Look for the class definition in the session
        class_match = re.search(r'(public\s+(class|boolean|int|void|String|List)\s[^{]+\{[^}]+\})', session_text)
        if class_match:
            code = class_match.group(1)
        
        # Get full plan with body_abstracts
        plan_mutations = []
        for i in range(min(len(actions), len(targets))):
            mut = {
                "action": actions[i],
                "target": targets[i],
                "details": {
                    "modifiers": [],
                    "type": "",
                    "parameters": [],
                    "logic_changes": [],
                    "body_abstract": body_abstracts[i] if i < len(body_abstracts) else ""
                }
            }
            plan_mutations.append(mut)
        
        plan = {
            "target_class": "",
            "ast_mutations": plan_mutations
        }
        
        plans.append({
            "name": case_name,
            "session": sid,
            "intent": intent,
            "plan": plan,
            "gen_runs": gen_runs,
        })

    # Map to case names by intent match
    mapped = []
    used_names = set()
    for p in plans:
        # Find first unused case name matching this intent
        assigned = None
        for cn in case_names:
            intent_part = p["intent"].split("_")[0] if "_" in p["intent"] else p["intent"]
            if intent_part in cn.upper() and cn not in used_names:
                assigned = cn
                used_names.add(cn)
                break
        p["name"] = assigned or p["name"]
        mapped.append(p)

    return mapped


# ============================================================
# PHASE 4 CHECK
# ============================================================

def run_phase4(original_code: str, refactored_code: str, intent: str, plan: dict) -> Dict[str, Any]:
    validator = Validator()
    findings: List[str] = []
    
    try:
        orig_cc = validator.get_complexity(original_code)
        refac_cc = validator.get_complexity(refactored_code)
    except Exception:
        orig_cc = 1
        refac_cc = 1

    skip_cc = intent in ("INLINE_METHOD",)
    loosen_cc = intent in ("SPLIT_LOOP",)
    extract_cc = intent in ("EXTRACT_METHOD",)

    if not skip_cc and not extract_cc:
        threshold = orig_cc + (1 if loosen_cc else 0)
        if refac_cc > threshold:
            findings.append(f"CC: {orig_cc}→{refac_cc} (limit ≤{threshold})")

    # Boundary
    target_scopes = []
    for m in plan.get("ast_mutations", []):
        t = m.get("target", "")
        if t and t not in target_scopes:
            target_scopes.append(t)
    try:
        bf = validator.verify_boundary(original_code, refactored_code, target_scopes)
        if bf:
            findings.append(f"Boundary: {bf.error_report.message[:80]}")
    except Exception:
        pass

    # Intent math
    try:
        ri = RefactorIntent(intent)
        intf = validator.verify_intent(ri, original_code, refactored_code)
        if intf:
            findings.append(f"Intent: {intf.error_report.message[:80]}")
    except Exception:
        pass

    # Methods preserved
    orig_methods = set(re.findall(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(', original_code))
    refac_methods = set(re.findall(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(', refactored_code))
    dropped = orig_methods - refac_methods
    if dropped:
        findings.append(f"Dropped: {dropped}")

    return {
        "pass": len(findings) == 0,
        "findings": findings,
        "orig_cc": orig_cc,
        "refac_cc": refac_cc,
    }


# ============================================================
# MAIN
# ============================================================

async def main():
    log_path = "/tmp/horizon_polish.log"
    
    print("=" * 70)
    print("TWO-STEP GENERATOR COMPARISON")
    print("ONE-STEP (single call) vs TWO-STEP (analysis → generate)")
    print(f"Plans from: {log_path}")
    print("=" * 70)

    # Extract plans
    plans_data = extract_plans_from_log(log_path)
    print(f"\nExtracted {len(plans_data)} unique sessions:")
    for p in plans_data:
        actions = [m["action"] for m in p["plan"]["ast_mutations"]]
        print(f"  {p['name'][:45]:45} intent={p['intent'][:25]:25} plan={actions}")

    # Get code from test cases for each plan
    from tests.validation.polish.test_polish_pipeline import TEST_CASES as POLISH_CASES
    code_map = {c["name"]: c["code"] for c in POLISH_CASES}

    # Enrich plans with code
    for p in plans_data:
        p["code"] = code_map.get(p["name"], "")
        if not p["code"]:
            # Fallback: search for code by intent
            for c in POLISH_CASES:
                if c["expected_intent"] == p["intent"] and c["name"] not in [pp.get("_used_code") for pp in plans_data]:
                    p["code"] = c["code"]
                    p["name"] = c["name"]
                    c["_used_code"] = True
                    break

    plans_data = [p for p in plans_data if p.get("code")]

    if not plans_data:
        print("\nERROR: No plans could be fully extracted.")
        return

    print(f"\nRunning Generator comparison on {len(plans_data)} cases with code...")

    h_gen = ModelTestHarness("generator")
    await h_gen.load_model()

    comparison = []

    for mode_label, two_step in [("ONE-STEP", False), ("TWO-STEP", True)]:
        print(f"\n--- {mode_label} ---")
        for pd in plans_data:
            name = pd["name"]
            intent = pd["intent"]
            code = pd["code"]
            plan = pd["plan"]

            user_prompt = format_plan_for_generator(plan, code)

            if two_step:
                # Step 1: Analyze
                await h_gen.clear_context()
                analysis_res = await h_gen.generate(
                    ANALYSIS_PROMPT, user_prompt,
                    temp=0.1, max_tokens=512,
                )
                analysis_text = analysis_res["content"][:800]

                # Step 2: Generate (NO clear_context — KV cache persists)
                gen_user = user_prompt + "\n\nYOUR ANALYSIS:\n" + analysis_text
                code_res = await h_gen.generate(
                    GENERATION_PROMPT, gen_user,
                    temp=0.1, max_tokens=3072,
                )
            else:
                await h_gen.clear_context()
                code_res = await h_gen.generate(
                    GENERATION_PROMPT, user_prompt,
                    temp=0.1, max_tokens=3072,
                )

            output_code = ""
            cm = re.search(r'<code>(.*?)</code>', code_res["content"], re.DOTALL)
            if cm:
                output_code = cm.group(1).strip()

            syntax_ok = False
            if output_code:
                try:
                    import javalang
                    wrapped = f"class __W__ {{ {output_code} }}" if "class" not in output_code else output_code
                    javalang.parse.parse(wrapped)
                    syntax_ok = True
                except Exception:
                    pass

            p4 = {"pass": False, "findings": [], "orig_cc": 0, "refac_cc": 0}
            if syntax_ok and code:
                p4 = run_phase4(code, output_code, intent, plan)

            comparison.append({
                "name": name, "intent": intent, "mode": mode_label,
                "syntax_ok": syntax_ok,
                "phase4_pass": p4["pass"],
                "phase4_findings": p4["findings"],
                "orig_cc": p4["orig_cc"],
                "refac_cc": p4["refac_cc"],
                "output_len": len(output_code),
                "duration": code_res["duration"],
            })

            print(f"  {name[:45]:45} syntax={'✓' if syntax_ok else '✗'} phase4={'✓' if p4['pass'] else '✗'} CC={p4['orig_cc']}→{p4['refac_cc']}")

    await h_gen.unload_model()

    # Compare
    print(f"\n{'='*70}")
    print("COMPARISON")
    print(f"{'='*70}")

    for mode in ["ONE-STEP", "TWO-STEP"]:
        mr = [r for r in comparison if r["mode"] == mode]
        s = sum(1 for r in mr if r["syntax_ok"])
        p = sum(1 for r in mr if r["phase4_pass"])
        total = len(mr)
        avg_cc_delta = sum(r.get("refac_cc", 0) - r.get("orig_cc", 0) for r in mr) / max(total, 1)
        print(f"\n  {mode}:")
        print(f"    Syntax: {s}/{total} | Phase4: {p}/{total} | Avg CC Delta: {avg_cc_delta:+.1f}")

    # Per-case diff
    print(f"\n  PER-CASE DIFF (TWO-STEP minus ONE-STEP):")
    for pd in plans_data:
        name = pd["name"]
        one = next((r for r in comparison if r["name"] == name and r["mode"] == "ONE-STEP"), None)
        two = next((r for r in comparison if r["name"] == name and r["mode"] == "TWO-STEP"), None)
        if one and two:
            o_pass = one["phase4_pass"]
            t_pass = two["phase4_pass"]
            o_cc = one["refac_cc"] - one["orig_cc"]
            t_cc = two["refac_cc"] - two["orig_cc"]
            if o_pass != t_pass or o_cc != t_cc:
                better = "BETTER" if (not o_pass and t_pass) or (o_cc > t_cc) else ""
                print(f"    {name[:45]:45} CC: +{o_cc}→+{t_cc}  Phase4: {o_pass}→{t_pass}  {better}")

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = f"test_results/twostep_compare_{ts}.json"
    with open(path, "w") as f:
        json.dump(comparison, f, indent=2, default=str)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
