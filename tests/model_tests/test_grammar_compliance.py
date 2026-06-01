"""
Grammar enforcement compliance test — samples from java_polish_full.json.
Tests Classifier, Analysis, Synthesis, Judge with GBNF constraint.
Measures: format compliance, Pydantic validation, reasoning quality.
"""
import asyncio
import json
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.utils.response_parser import ResponseParser
from app.utils.schemas import (
    ArchitectAnalysisResponse,
    ASTArchitectResponse,
    IntentClassifierResponse,
    StructuralAuditorResponse,
)
from tests.model_tests.harness import ModelTestHarness


TEST_CASES = [
    {
        "name": "short_easy_nim",
        "instruction": "Flatten the single if-return into a guard clause with early return.",
        "code": "public boolean canWinNim(int n) {\n    return n % 4 != 0;\n}",
    },
    {
        "name": "medium_rotate",
        "instruction": "Extract the binary search logic into a helper method called findPivotIndex.",
        "code": (
            "public int findMin(int[] nums) {\n"
            "    int left = 0, right = nums.length - 1;\n"
            "    while (left < right) {\n"
            "        int mid = left + (right - left) / 2;\n"
            "        if (nums[mid] > nums[right]) left = mid + 1;\n"
            "        else right = mid;\n"
            "    }\n"
            "    return nums[left];\n"
            "}"
        ),
    },
    {
        "name": "medium_operations",
        "instruction": "Extract the magic number 3 into a constant named MIN_OPS.",
        "code": (
            "public int minOperations(int[] nums) {\n"
            "    int n = nums.length, ops = 0;\n"
            "    for (int i = 0; i <= n - 3; i++) {\n"
            "        if (nums[i] == 0) {\n"
            "            nums[i] ^= 1; nums[i+1] ^= 1; nums[i+2] ^= 1;\n"
            "            ops++;\n"
            "        }\n"
            "    }\n"
            "    if (nums[n-1] == 0 || nums[n-2] == 0) return -1;\n"
            "    return ops;\n"
            "}"
        ),
    },
    {
        "name": "hard_palindrome",
        "instruction": "Decompose the compound condition into named booleans: isSameChar and isInnerPalindrome.",
        "code": (
            "public class Solution {\n"
            "    private boolean isPalindrome(String s, int start, int end) {\n"
            "        while (start < end) {\n"
            "            if (s.charAt(start) != s.charAt(end)) return false;\n"
            "            start++; end--;\n"
            "        }\n"
            "        return true;\n"
            "    }\n"
            "    public boolean check(String s) {\n"
            "        return isPalindrome(s, 0, s.length() - 1);\n"
            "    }\n"
            "}"
        ),
    },
    {
        "name": "hard_large",
        "instruction": "Rename the variable 'i' to 'row' and 'j' to 'col' everywhere in the method.",
        "code": (
            "public int uniquePaths(int m, int n) {\n"
            "    int[][] dp = new int[m][n];\n"
            "    for (int i = 0; i < m; i++) dp[i][0] = 1;\n"
            "    for (int j = 0; j < n; j++) dp[0][j] = 1;\n"
            "    for (int i = 1; i < m; i++) {\n"
            "        for (int j = 1; j < n; j++) {\n"
            "            dp[i][j] = dp[i-1][j] + dp[i][j-1];\n"
            "        }\n"
            "    }\n"
            "    return dp[m-1][n-1];\n"
            "}"
        ),
    },
]


async def test_planner_grammar(harness: ModelTestHarness):
    """Run classifier → analysis → synthesis with grammar enforcement."""
    results = []
    for case in TEST_CASES:
        r: Dict[str, Any] = {"name": case["name"]}
        code = case["code"]
        instruction = case["instruction"]

        # 1. Classifier
        cprompt = f"<code>{code}</code>\n<instruction>{instruction}</instruction>"
        cres = await harness.generate(
            harness.prompts["planner"]["classifier"], cprompt,
            temp=0.1, max_tokens=500, response_model=IntentClassifierResponse
        )
        r["classifier_content"] = cres["content"][:500]
        r["classifier_valid"] = cres["success"]
        try:
            ci = ResponseParser.extract_json(cres["content"], IntentClassifierResponse)
            r["intent"] = ci.intent_packet.specific_intent.value
            r["classifier_pydantic"] = True
            r["classifier_scratchpad_len"] = len(ci.classification_scratchpad or "")
        except Exception:
            r["classifier_pydantic"] = False

        # 2. Analysis
        aprompt = (
            f"Intent Packet: {json.dumps(ci.intent_packet.model_dump()) if r.get('classifier_pydantic') else '{}'}\n"
            f"User Instruction: {instruction}\n"
            f"Code: <code>{code}</code>"
        )
        await harness.clear_context()
        ares = await harness.generate(
            harness.prompts["planner"]["architect_analysis"], aprompt,
            temp=0.1, max_tokens=1024, response_model=ArchitectAnalysisResponse
        )
        r["analysis_content"] = ares["content"][:500]
        r["analysis_valid"] = ares["success"]
        try:
            ai = ResponseParser.extract_json(ares["content"], ArchitectAnalysisResponse)
            r["analysis_pydantic"] = True
            r["primary_targets"] = len(ai.primary_targets or [])
            r["secondary_targets"] = len(ai.secondary_targets or [])
            r["new_structures"] = len(ai.new_structures_needed or [])
            r["analysis_scratchpad_len"] = len(ai.analysis_scratchpad or "")
            analysis_dict = ai.model_dump()
        except Exception:
            r["analysis_pydantic"] = False
            analysis_dict = {}

        # 3. Synthesis
        sprompt = (
            f"Analysis: {json.dumps(analysis_dict)}\n"
            f"Intent: {json.dumps(ci.intent_packet.model_dump()) if r.get('classifier_pydantic') else '{}'}\n"
            f"Instruction: {instruction}\n"
            f"Code: <code>{code}</code>"
        )
        await harness.clear_context()
        sres = await harness.generate(
            harness.prompts["planner"]["architect"], sprompt,
            temp=0.1, max_tokens=2048, response_model=ASTArchitectResponse
        )
        r["synthesis_content"] = sres["content"][:500]
        r["synthesis_valid"] = sres["success"]
        try:
            si = ResponseParser.extract_json(sres["content"], ASTArchitectResponse)
            r["synthesis_pydantic"] = True
            plan = si.ast_modification_plan
            r["target_class"] = plan.target_class
            r["mutation_count"] = len(plan.ast_mutations)
            r["mutation_actions"] = [m.action.value for m in plan.ast_mutations]
            r["synthesis_scratchpad_len"] = len(si.architect_scratchpad or "")
        except Exception as e:
            r["synthesis_pydantic"] = False
            r["synthesis_error"] = str(e)[:200]

        results.append(r)
        print(f"  {case['name']}: cls={r.get('classifier_pydantic')} "
              f"ana={r.get('analysis_pydantic')} "
              f"syn={r.get('synthesis_pydantic')} "
              f"| intent={r.get('intent','?')} | "
              f"mutations={r.get('mutation_count','?')} "
              f"| cls_scratchpad={r.get('classifier_scratchpad_len',0)}ch "
              f"ana_scratchpad={r.get('analysis_scratchpad_len',0)}ch "
              f"syn_scratchpad={r.get('synthesis_scratchpad_len',0)}ch")
    return results


async def test_judge_grammar(harness: ModelTestHarness):
    """Test judge format compliance with grammar enforcement."""
    results = []
    # Use 3 test pairs: accept-worthy, revise-worthy, identical no-op
    test_pairs = [
        {
            "name": "judge_accept_rename",
            "original": "void count(int x) { int n = x; }",
            "refactored": "void count(int input) { int count = input; }",
            "plan": "Intent: RENAME_SYMBOL. Mutations: RENAME_SYMBOL(x->input), RENAME_SYMBOL(n->count)",
            "expected_issues": 0,
        },
        {
            "name": "judge_revise_broken",
            "original": "int calc() { return 5; }",
            "refactored": "void calc() { System.out.println(5); }",
            "plan": "Intent: EXTRACT_CONSTANT. Mutations: ADD_CONSTANT(VALUE)",
            "expected_issues": False,  # should have issues
        },
        {
            "name": "judge_noop",
            "original": "boolean ok(int x) { return x > 0; }",
            "refactored": "boolean ok(int x) { return x > 0; }",
            "plan": "Intent: DECOMPOSE_CONDITIONAL. Mutations: ADD_FIELD(isPositive), MODIFY_METHOD(ok)",
            "expected_issues": True,  # must reject no-op
        },
    ]

    for pair in test_pairs:
        r = {"name": pair["name"]}
        prompt = (
            f"## Plan Context\n{pair['plan']}\n\n"
            f"## Code\n"
            f"Original: <code>{pair['original']}</code>\n"
            f"Refactored: <code>{pair['refactored']}</code>"
        )
        jres = await harness.generate(
            harness.prompts["judge"]["auditor"], prompt,
            temp=0.1, max_tokens=1000, response_model=StructuralAuditorResponse
        )
        r["judge_content"] = jres["content"][:500]
        r["judge_valid"] = jres["success"]
        try:
            ji = ResponseParser.extract_json(jres["content"], StructuralAuditorResponse)
            r["judge_pydantic"] = True
            r["verdict"] = ji.verdict
            r["issue_count"] = len(ji.issues or [])
            r["scratchpad_str"] = str(ji.audit_scratchpad)[:300]
            # Reasoning: check if scratchpad has actual content vs empty/template
            sp = ji.audit_scratchpad
            has_vt = bool(sp.variable_trace) if hasattr(sp, 'variable_trace') else False
            lc = sp.logic_comparison or ""
            r["reasoning_meaningful"] = len(lc) > 20
            r["scratchpad_len"] = len(str(sp))
        except Exception as e:
            r["judge_pydantic"] = False
            r["judge_error"] = str(e)[:200]

        results.append(r)
        print(f"  {pair['name']}: pydantic={r.get('judge_pydantic')} "
              f"verdict={r.get('verdict','?')} "
              f"issues={r.get('issue_count','?')} "
              f"reasoning={'OK' if r.get('reasoning_meaningful') else 'THIN'} "
              f"scratchpad={r.get('scratchpad_len',0)}ch")

    return results


async def main():
    print("=" * 60)
    print("GRAMMAR COMPLIANCE TEST")
    print(f"Samples: {len(TEST_CASES)} planner + 3 judge")
    print("=" * 60)

    # Planner
    print("\n--- PLANNER (Classifier → Analysis → Synthesis) ---")
    harness = ModelTestHarness("planner")
    await harness.load_model()
    planner_results = await test_planner_grammar(harness)
    await harness.unload_model()

    # Judge
    print("\n--- JUDGE ---")
    harness = ModelTestHarness("judge")
    await harness.load_model()
    judge_results = await test_judge_grammar(harness)
    await harness.unload_model()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # Planner compliance
    cls_pyd = sum(1 for r in planner_results if r.get("classifier_pydantic"))
    ana_pyd = sum(1 for r in planner_results if r.get("analysis_pydantic"))
    syn_pyd = sum(1 for r in planner_results if r.get("synthesis_pydantic"))
    print(f"Planner Pydantic compliance: Classifier={cls_pyd}/{len(planner_results)} "
          f"Analysis={ana_pyd}/{len(planner_results)} "
          f"Synthesis={syn_pyd}/{len(planner_results)}")

    # Reasoning quality
    cls_avg = sum(r.get("classifier_scratchpad_len", 0) for r in planner_results) / len(planner_results)
    ana_avg = sum(r.get("analysis_scratchpad_len", 0) for r in planner_results) / len(planner_results)
    syn_avg = sum(r.get("synthesis_scratchpad_len", 0) for r in planner_results) / len(planner_results)
    print(f"Scratchpad lengths: Classifier={cls_avg:.0f}ch "
          f"Analysis={ana_avg:.0f}ch "
          f"Synthesis={syn_avg:.0f}ch")

    # Mutation counts
    mut_total = sum(r.get("mutation_count", 0) for r in planner_results)
    print(f"Total mutations across {len(planner_results)} plans: {mut_total}")

    # Judge compliance
    jud_pyd = sum(1 for r in judge_results if r.get("judge_pydantic"))
    jud_reason = sum(1 for r in judge_results if r.get("reasoning_meaningful"))
    print(f"\nJudge Pydantic compliance: {jud_pyd}/{len(judge_results)}")
    print(f"Judge reasoning quality: {jud_reason}/{len(judge_results)} meaningful")

    # Verdicts
    for r in judge_results:
        print(f"  {r['name']}: {r.get('verdict','?')} ({r.get('issue_count','?')} issues)")

    # Format issues
    print(f"\nTotal JSON parse failures: "
          f"{len(planner_results)*3 - cls_pyd - ana_pyd - syn_pyd + len(judge_results) - jud_pyd}")

    # Save
    timestamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    output = {
        "timestamp": timestamp,
        "planner_results": planner_results,
        "judge_results": judge_results,
    }
    path = f"test_results/grammar_compliance_{timestamp}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
