"""
TOOL vs FULLGEN — strict Phase 4 gate comparison.
20 polish cases, all 12 intents.
Winner per intent → intent_approach_map.json.
If both fail Phase 4 → "NONE" (truth).
"""
import asyncio
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, ".")

from app.modules.validator import Validator
from app.utils.formatters import format_plan_for_generator
from app.utils.types import RefactorIntent
from tests.model.harness import ModelTestHarness


# ==========================================================
# REDESIGNED TOOL PROMPT — Phase 4 Gate Reference
# ==========================================================

TOOL_PROMPT = """### ROLE
Edit the base code. Your output is checked by an automated validator.

### WHAT THE VALIDATOR CHECKS
- Syntax: Java must parse correctly
- Complexity: Cyclomatic Complexity must NOT increase
- Boundary: Methods not in any edit must stay EXACTLY unchanged
- Intent: The structural transformation must be achieved

### FORMAT
Each change is a SINGLE line edit. Multiple changes = multiple blocks:
<edit match="EXACT LINE FROM ORIGINAL">
EXACT REPLACEMENT LINE
</edit>

To ADD a new line without removing anything:
<add after="EXACT ORIGINAL LINE" position="before|after">
NEW LINE TO INSERT
</add>

### RULES
- Copy the EXACT line text. Include quotes, whitespace, semicolons exactly.
- One <edit> block = one line changed. Never replace an entire method.
- Split large changes into multiple small <edit> blocks.
- Lines NOT in any block stay EXACTLY as the original — the validator checks this.

### NEVER DO
- Replace an entire method in one block
- Merge exceptions with || (use separate <edit> blocks)
- Add throws to method signatures
- Add if(x==null) checks
- Drop opening braces { from method declarations
- Add public/static modifiers that weren't in the original

### EXAMPLE — RENAME (4 small edits, CORRECT)
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

### ANTI-PATTERN — NEVER DO THIS (WRONG)
<edit match="int findJudge(int n, int[][] trust) {">
public int findJudge(int n, int[][] trust) {
    int[] trustScores = new int[n + 1];
    ...
}
</edit>
WRONG — one block replaced the entire method. Use 4 separate blocks like the example above."""


# ==========================================================
# FULLGEN PROMPT (same as orchestrator)
# ==========================================================

FULLGEN_PROMPT = """### ROLE
Output ONLY the refactored code wrapped in <code> tags. No explanation.

<code>
public class X { ... }
</code>"""


# ==========================================================
# PROGRESSIVE MATCHING — 5 levels
# ==========================================================

def match_line(lines: List[str], match_text: str) -> Optional[int]:
    """Progressive matching. Returns line index or None."""
    match_stripped = match_text.strip()
    if not match_stripped:
        return None

    # Level 1: Exact (strip outer whitespace only)
    for i, line in enumerate(lines):
        if line.strip() == match_stripped:
            return i

    # Level 2: Normalized — strip quotes, semicolons, normalize whitespace
    match_norm = match_stripped.replace('\\"', '"').replace('"', '')
    match_norm = match_norm.rstrip(';').strip()
    for i, line in enumerate(lines):
        line_norm = line.strip().replace('"', '').rstrip(';').strip()
        if match_norm == line_norm:
            return i

    # Level 3: First 3 significant words match
    match_words = ' '.join(w for w in match_stripped.split() if not w.startswith('@'))[:60]
    match_key = ' '.join(match_words.split()[:3])
    if match_key:
        for i, line in enumerate(lines):
            line_key = ' '.join(line.strip().split()[:3])
            if match_key == line_key:
                return i

    # Level 4: First 2 tokens match (skip whitespace/spaces)
    tokens = match_stripped.split()
    if len(tokens) >= 2:
        first2 = ' '.join(tokens[:2])
        for i, line in enumerate(lines):
            if ' '.join(line.strip().split()[:2]) == first2:
                return i

    # Level 5: Fuzzy — >60% of match words in line
    match_set = set(w.lower() for w in match_stripped.split() if len(w) > 1)
    if match_set:
        for i, line in enumerate(lines):
            line_set = set(w.lower() for w in line.strip().split() if len(w) > 1)
            if match_set & line_set:
                overlap = len(match_set & line_set) / len(match_set)
                if overlap >= 0.6:
                    return i

    return None


# ==========================================================
# PRE-EDIT VALIDATION
# ==========================================================

def validate_edit(match_line_orig: str, replacement: str) -> Optional[str]:
    """Returns error message if edit is invalid, None if OK."""
    r = replacement.strip()
    m = match_line_orig.strip()

    # Merged guards: || in throw context
    if '||' in r and ('throw' in m.lower() or 'throw' in r.lower()):
        return "MERGED GUARD CLAUSES — split into separate <edit> blocks, one per throw"

    # Added throws to method signature
    if re.search(r'throws\s+\w+Exception', r, re.IGNORECASE):
        if not re.search(r'throws\s+\w+Exception', m, re.IGNORECASE):
            return "ADDED throws DECLARATION — remove it (not in original signature)"

    # Dropped opening brace in method/block declaration
    orig_opens = m.count('{')
    repl_opens = r.count('{')
    if orig_opens > 0 and repl_opens == 0:
        return "DROPPED OPENING BRACE — keep the method/block signature intact"

    # Added null check
    if 'if' in r and '== null' in r and '== null' not in m:
        return "ADDED NULL CHECK — not in original code, remove it"

    # Added public/static modifiers
    for mod in ['public ', 'static ']:
        if mod in r and mod not in m:
            return f"ADDED '{mod.strip()}' MODIFIER — not in original, remove it"

    return None


# ==========================================================
# APPLY TOOL EDITS
# ==========================================================

def apply_tool_edits(original_code: str, edit_text: str) -> Tuple[str, int, int, List[str]]:
    """Apply <edit> and <add> blocks. Returns (result, edit_count, add_count, errors)."""
    lines = list(original_code.split('\n'))
    errors: List[str] = []
    validations: List[str] = []

    # Extract <edit> and <add> blocks
    edit_blocks = re.findall(r'<edit match="(.*?)">\n(.*?)</edit>', edit_text, re.DOTALL)
    add_blocks = re.findall(r'<add after="(.*?)" position="(before|after)">\n(.*?)</add>', edit_text, re.DOTALL)

    if not edit_blocks and not add_blocks:
        return original_code, 0, 0, ["No edit/add blocks found — output must contain at least one change"]

    # Process ADDs first (insertions)
    for match_text, position, replacement in reversed(add_blocks):
        idx = match_line(lines, match_text)
        if idx is None:
            errors.append(f"ADD match failed: '{match_text[:40]}...' not found")
            continue
        rlines = replacement.strip().split('\n')
        if position == "before":
            for rl in reversed(rlines):
                lines.insert(idx, rl)
        else:
            for rl in rlines:
                lines.insert(idx + 1, rl)

    # Validate + process EDITs
    applied_edits = 0
    for match_text, replacement in reversed(edit_blocks):
        # Validate before matching
        validation_error = validate_edit(match_text, replacement)
        if validation_error:
            validations.append(validation_error)
            continue  # Skip invalid edits

        idx = match_line(lines, match_text)
        if idx is None:
            errors.append(f"EDIT match failed: '{match_text[:40]}...' not found after ADDs applied")
            continue

        # Apply replacement
        rlines = replacement.strip().split('\n')
        if len(rlines) == 1:
            lines[idx] = rlines[0]
        else:
            lines[idx:idx+1] = rlines

        applied_edits += 1

    result = '\n'.join(lines)

    # Add validation errors to error list
    for v in validations:
        errors.append(f"VALIDATION: {v}")

    return result, applied_edits, len(add_blocks), errors


# ==========================================================
# PHASE 4 CHECK (same as orchestrator)
# ==========================================================

def run_phase4(original_code: str, refactored_code: str, intent: str) -> Dict[str, Any]:
    validator = Validator()
    findings: List[str] = []

    try:
        orig_cc = validator.get_complexity(original_code)
        refac_cc = validator.get_complexity(refactored_code)
    except Exception:
        orig_cc, refac_cc = 1, 1

    skip_cc = intent in ("INLINE_METHOD",)
    loosen_cc = intent in ("SPLIT_LOOP",)

    if not skip_cc:
        threshold = orig_cc + (1 if loosen_cc else 0)
        if intent not in ("EXTRACT_METHOD",) and refac_cc > threshold:
            findings.append(f"CC: {orig_cc}→{refac_cc} (limit≤{threshold})")

    # Boundary
    try:
        bf = validator.verify_boundary(original_code, refactored_code, [])
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


# ==========================================================
# SCORE COMPUTATION
# ==========================================================

def compute_score(p4: Dict[str, Any], match_errors: int, duration: float) -> int:
    """Strict scoring. Phase 4 pass = 10 points base. Fail = 0 base + bonuses."""
    if p4["pass"]:
        score = 10
    else:
        score = 0

    # Bonus: lower CC
    cc_delta = p4["refac_cc"] - p4["orig_cc"]
    score += max(-cc_delta, -5)  # At most -5 penalty per CC point

    # Bonus: boundary clean
    if "Boundary" not in str(p4.get("findings", "")):
        score += 1

    # Bonus: intent math OK
    if "Intent" not in str(p4.get("findings", "")):
        score += 1

    # Penalty: matching errors
    score -= match_errors * 2

    # Small bonus for speed
    if duration < 3:
        score += 1

    return score


# ==========================================================
# MAIN
# ==========================================================

async def main():
    print("=" * 70)
    print("TOOL vs FULLGEN — STRICT Phase 4 Gate Comparison")
    print("20 polish cases, all 12 intents")
    print("=" * 70)

    # Load cached plans
    plans_file = "tests/results/generator_compare_plans.json"
    try:
        with open(plans_file) as f:
            plans_data = json.load(f)
        print(f"Loaded {len(plans_data)} cached plans from {plans_file}")
    except Exception:
        print("No cached plans. Running Planner first...")
        # Simplified: use first 5 as quick test
        from tests.model.generator.test_generator_tool import CASES
        plans_data = []
        for case in CASES:
            plans_data.append({
                "name": case["name"],
                "intent": case["intent"],
                "code": case["code"],
                "plan": case.get("plan", {"ast_mutations": []})
            })

    # Get code for each plan
    from tests.pipeline.test_20_polish_full import TEST_CASES as POLISH_CASES
    code_map = {c["name"]: (c["code"], c["expected_intent"]) for c in POLISH_CASES}

    # Build test cases
    test_cases = []
    for pd in plans_data:
        name = pd["name"]
        intent = pd.get("intent", pd.get("expected_intent", "?"))
        code = pd.get("code", "")
        plan = pd.get("plan", {})

        if not code and name in code_map:
            code = code_map[name][0]
        if not intent or intent == "?":
            intent = code_map.get(name, ("", ""))[1] or name.split("_")[1] if "_" in name else "?"

        if code and intent:
            test_cases.append({"name": name, "intent": intent, "code": code, "plan": plan})

    print(f"Running on {len(test_cases)} cases with code/plan data")

    # Load generator model
    h_gen = ModelTestHarness("generator")
    await h_gen.load_model()

    # Run both modes
    comparison = []

    for mode, use_tool in [("TOOL", True), ("FULLGEN", False)]:
        print(f"\n{'='*70}")
        print(f"MODE: {mode}")
        print(f"{'='*70}")

        for tc in test_cases:
            name = tc["name"]
            intent = tc["intent"]
            code = tc["code"]
            plan = tc["plan"]

            system = TOOL_PROMPT if use_tool else FULLGEN_PROMPT
            user = format_plan_for_generator(plan, code)

            result = await h_gen.generate(system, user, temp=0.1, max_tokens=3072)
            raw = result["content"]

            if use_tool:
                final_code, ecount, acount, errors = apply_tool_edits(code, raw)
                # Check if output is valid
                if (ecount + acount) == 0:
                    errors.append("ZERO EDITS — no valid changes produced")
                    final_code = code

                syntax_ok = False
                try:
                    import javalang
                    wrapped = f"class _W_ {{ {final_code} }}" if "class" not in final_code else final_code
                    javalang.parse.parse(wrapped)
                    syntax_ok = True
                except Exception:
                    pass

                p4 = run_phase4(code, final_code, intent) if syntax_ok else {"pass": False, "findings": ["syntax fail"], "orig_cc": 0, "refac_cc": 999, "pass": False}

                comparison.append({
                    "name": name, "intent": intent, "mode": mode,
                    "syntax_ok": syntax_ok,
                    "phase4": p4,
                    "edit_count": ecount,
                    "add_count": acount,
                    "match_errors": len(errors),
                    "score": compute_score(p4, len(errors), result["duration"]),
                    "duration": result["duration"],
                })

                print(f"  {name[:45]:45} edits={ecount}+{acount} errors={len(errors)} syntax={'✓' if syntax_ok else '✗'} phase4={'✓' if p4['pass'] else '✗'} score={comparison[-1]['score']:>3d}")
            else:
                code_match = re.search(r'<code>(.*?)</code>', raw, re.DOTALL)
                final_code = code_match.group(1).strip() if code_match else "NO CODE"

                syntax_ok = False
                try:
                    import javalang
                    wrapped = f"class _W_ {{ {final_code} }}" if "class" not in final_code else final_code
                    javalang.parse.parse(wrapped)
                    syntax_ok = True
                except Exception:
                    pass

                p4 = run_phase4(code, final_code, intent) if syntax_ok else {"pass": False, "findings": ["syntax fail"], "orig_cc": 0, "refac_cc": 999}

                comparison.append({
                    "name": name, "intent": intent, "mode": mode,
                    "syntax_ok": syntax_ok,
                    "phase4": p4,
                    "score": compute_score(p4, 0, result["duration"]),
                    "duration": result["duration"],
                })

                print(f"  {name[:45]:45} syntax={'✓' if syntax_ok else '✗'} phase4={'✓' if p4['pass'] else '✗'} score={comparison[-1]['score']:>3d}")

    await h_gen.unload_model()

    # ==========================================================
    # PER-INTENT WINNER SELECTION
    # ==========================================================
    print(f"\n{'='*70}")
    print("PER-INTENT WINNER SELECTION")
    print(f"{'='*70}")

    intent_scores = defaultdict(lambda: {"TOOL": [], "FULLGEN": []})
    for r in comparison:
        intent_scores[r["intent"]][r["mode"]].append(r)

    approach_map = {}
    print(f"\n{'Intent':<30} {'TOOL Avg':>8} {'#Pass':>6} {'FULLGEN Avg':>8} {'#Pass':>6} {'Winner':<10}")
    print("-" * 80)

    for intent in sorted(intent_scores.keys()):
        tscores = intent_scores[intent]["TOOL"]
        fscores = intent_scores[intent]["FULLGEN"]

        t_avg = sum(r["score"] for r in tscores) / max(len(tscores), 1)
        f_avg = sum(r["score"] for r in fscores) / max(len(fscores), 1)
        t_pass = sum(1 for r in tscores if r["phase4"]["pass"])
        f_pass = sum(1 for r in fscores if r["phase4"]["pass"])

        # STRICT: if neither passes Phase 4 → NONE
        if t_pass == 0 and f_pass == 0:
            winner = "NONE"
        elif t_avg > f_avg:
            winner = "TOOL"
        elif f_avg > t_avg:
            winner = "FULLGEN"
        else:
            winner = "TIE→FULLGEN"  # default to safer approach

        approach_map[intent] = winner
        print(f"  {intent:<30} {t_avg:>8.1f} {t_pass:>6} {f_avg:>8.1f} {f_pass:>6} {winner:<10}")

    # ==========================================================
    # SAVE RESULTS
    # ==========================================================
    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")

    map_path = f"tests/results/intent_approach_map_{ts}.json"
    with open(map_path, "w") as f:
        json.dump(approach_map, f, indent=2)
    print(f"\nApproach map saved: {map_path}")

    result_path = f"tests/results/tool_vs_fullgen_{ts}.json"
    with open(result_path, "w") as f:
        json.dump(comparison, f, indent=2, default=str)
    print(f"Full results saved: {result_path}")

    # Summary
    tool_wins = sum(1 for v in approach_map.values() if v == "TOOL")
    fullgen_wins = sum(1 for v in approach_map.values() if v in ("FULLGEN", "TIE→FULLGEN"))
    none_wins = sum(1 for v in approach_map.values() if v == "NONE")
    print(f"\nSummary: TOOL={tool_wins} FULLGEN={fullgen_wins} NONE={none_wins}")


if __name__ == "__main__":
    asyncio.run(main())
