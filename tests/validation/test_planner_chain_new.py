"""Script 4: Full Planner chain — Classifier → Analysis → Architect with guidance."""
import asyncio
import json
import sys
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.utils.response_parser import ResponseParser
from app.utils.schemas import (
    ArchitectAnalysisResponse,
    ASTArchitectResponse,
    IntentClassifierResponse,
)
from tests.model_tests.harness import ModelTestHarness


TEST_CASES: List[Dict[str, Any]] = [
    # ---- EXISTING ----
    {
        "name": "chain_flat_orderprocessor",
        "code": """public class OrderProcessor {
    public void processOrder(Order order, User user) {
        if (user != null) {
            if (user.isActive()) {
                if (order != null) {
                    if (!order.getItems().isEmpty()) {
                        double total = order.getTotal();
                        if (total > 1000) {
                            if (user.isPremium()) {
                                order.applyDiscount(0.15);
                            } else {
                                order.applyDiscount(0.05);
                            }
                        }
                        System.out.println("Processing order for: " + user.getName());
                    } else {
                        throw new IllegalArgumentException("Order has no items.");
                    }
                } else {
                    throw new IllegalArgumentException("Order cannot be null.");
                }
            } else {
                throw new IllegalStateException("User account is inactive.");
            }
        } else {
            throw new IllegalArgumentException("User cannot be null.");
        }
    }
}""",
        "instruction": "Refactor the processOrder method to use guard clauses. Invert the nested if-statements to handle invalid states at the top with immediate exceptions. Preserve every original exception type and error message exactly.",
        "expected_intent": "FLATTEN_CONDITIONAL",
    },
    {
        "name": "chain_extract_tax_calculator",
        "code": "public class Calculator { public double calculateTotal(double price, int quantity, double taxRate) { double subtotal = price * quantity; double tax = subtotal * taxRate; double total = subtotal + tax; double rounded = Math.round(total * 100.0) / 100.0; return rounded; } }",
        "instruction": "Extract the tax calculation logic (tax computation and rounding) into a separate private method called computeTaxWithRounding.",
        "expected_intent": "EXTRACT_METHOD",
    },
    {
        "name": "chain_rename_user_manager",
        "code": "public class UserManager { private String n; public String getN() { return n; } public void setN(String n) { this.n = n; } }",
        "instruction": "Rename the field 'n' to 'username' and update all references.",
        "expected_intent": "RENAME_SYMBOL",
    },
    {
        "name": "chain_const_circle_pi",
        "code": "public class Circle { public double calculateArea(double radius) { return 3.14159 * radius * radius; } public double calculateCircumference(double radius) { return 2 * 3.14159 * radius; } }",
        "instruction": "Extract the magic number 3.14159 into a named constant PI.",
        "expected_intent": "EXTRACT_CONSTANT",
    },
    {
        "name": "chain_decomp_closed_island",
        "code": "public class Solution { public int closedIsland(int[][] grid) { int n = grid.length, m = grid[0].length, count = 0; for (int i = 0; i < n; i++) { for (int j = 0; j < m; j++) { if (grid[i][j] == 0) { if (dfs(grid, i, j, n, m)) count++; } } } return count; } private boolean dfs(int[][] grid, int x, int y, int n, int m) { if (x < 0 || x >= n || y < 0 || y >= m) return false; if (grid[x][y] == 1 || grid[x][y] == -1) return true; grid[x][y] = -1; return dfs(grid, x+1, y, n, m) && dfs(grid, x-1, y, n, m) && dfs(grid, x, y+1, n, m) && dfs(grid, x, y-1, n, m); } }",
        "instruction": "Decompose the complex DFS boundary condition into well-named booleans: isInBounds, isOnBorder, isUnvisited.",
        "expected_intent": "DECOMPOSE_CONDITIONAL",
    },
    # ---- NEW (from polish file) ----
    {
        "name": "chain_nim_decompose",
        "code": "public boolean canWinNim(int n) { return n % 4 != 0; }",
        "instruction": "Decompose the condition n % 4 != 0 into a named boolean called isNotMultipleOfFour.",
        "expected_intent": "DECOMPOSE_CONDITIONAL",
    },
    {
        "name": "chain_minops_split",
        "code": "public int minOperations(int[] nums) { int n = nums.length, ops = 0; for (int i = 0; i <= n - 3; i++) { if (nums[i] == 0) { nums[i] ^= 1; nums[i+1] ^= 1; nums[i+2] ^= 1; ops++; } } for (int i = 0; i < n; i++) { if (nums[i] == 0) return -1; } return ops; }",
        "instruction": "Split the counting loop from the result-check loop into two separate loops.",
        "expected_intent": "SPLIT_LOOP",
    },
    {
        "name": "chain_findmin_rename",
        "code": "public int findMin(int[] nums) { int left = 0, right = nums.length - 1; while (left < right) { int mid = left + (right - left) / 2; if (nums[mid] > nums[right]) left = mid + 1; else right = mid; } return nums[left]; }",
        "instruction": "Rename left to lowBound and right to highBound everywhere in the method.",
        "expected_intent": "RENAME_SYMBOL",
    },
    {
        "name": "chain_palindrome_extract",
        "code": "public class Solution { private boolean isPalindrome(String s, int start, int end) { while (start < end) { if (s.charAt(start) != s.charAt(end)) return false; start++; end--; } return true; } public boolean check(String s) { return isPalindrome(s, 0, s.length() - 1); } }",
        "instruction": "Extract the while-loop palindrome checking logic into a private helper method called checkPalindrome.",
        "expected_intent": "EXTRACT_METHOD",
    },
    {
        "name": "chain_uniquepaths_flatten",
        "code": "public class Solution { public int uniquePaths(int m, int n) { int[][] dp = new int[m][n]; for (int i = 0; i < m; i++) { dp[i][0] = 1; } for (int j = 0; j < n; j++) { dp[0][j] = 1; } for (int i = 1; i < m; i++) { for (int j = 1; j < n; j++) { dp[i][j] = dp[i-1][j] + dp[i][j-1]; } } return dp[m-1][n-1]; } }",
        "instruction": "Flatten the nested for-loops using guard clauses with continue for the first row and column initialization.",
        "expected_intent": "FLATTEN_CONDITIONAL",
    },
]


def inject_analysis_guidance(prompts: dict, intent: str) -> str:
    base = prompts["planner"]["architect_analysis"]
    guidance = prompts["planner"].get("analysis_guidance", {}).get(intent, "")
    return base + "\n" + guidance if guidance else base


def inject_synthesis_guidance(prompts: dict, intent: str) -> str:
    base = prompts["planner"]["architect"]
    guidance = prompts["planner"].get("synthesis_guidance", {}).get(intent, "")
    return base + "\n" + guidance if guidance else base


async def run_chain_case(harness: ModelTestHarness, case: Dict[str, Any]) -> Dict[str, Any]:
    code = case["code"]
    instruction = case["instruction"]
    r: Dict[str, Any] = {
        "name": case["name"],
        "expected_intent": case["expected_intent"],
        "classifier_match": False,
        "analysis_primary": [],
        "analysis_new": [],
        "plan_mutations": 0,
        "plan_actions": [],
        "hallucinations": [],
    }

    # Step 1: Classifier
    cprompt = f"<code>{code}</code>\n<instruction>{instruction}</instruction>"
    cres = await harness.generate(
        harness.prompts["planner"]["classifier"],
        cprompt,
        temp=0.1, max_tokens=500,
        response_model=IntentClassifierResponse,
    )
    if cres["success"]:
        try:
            ci = ResponseParser.extract_json(cres["content"], IntentClassifierResponse)
            r["actual_intent"] = ci.intent_packet.specific_intent.value
            r["classifier_match"] = r["actual_intent"] == case["expected_intent"]
            r["classifier_scratchpad"] = (ci.classification_scratchpad or "")[:200]
            intent_packet = ci.intent_packet.model_dump()
        except Exception:
            intent_packet = {"specific_intent": case["expected_intent"]}
            r["actual_intent"] = "PARSE_ERROR"
    else:
        intent_packet = {"specific_intent": case["expected_intent"]}
        r["actual_intent"] = "NO_RESPONSE"

    intent_key = r.get("actual_intent", case["expected_intent"])
    if intent_key in ("PARSE_ERROR", "NO_RESPONSE"):
        intent_key = case["expected_intent"]
    r["intent_used"] = intent_key

    # Step 2: Analysis with guidance
    await harness.clear_context()
    analysis_system = inject_analysis_guidance(harness.prompts, intent_key)
    auser = (
        f"Intent Packet: {json.dumps(intent_packet)}\n"
        f"User Instruction: {instruction}\n"
        f"Code: <code>{code}</code>"
    )
    ares = await harness.generate(
        analysis_system, auser,
        temp=0.1, max_tokens=1024,
        response_model=ArchitectAnalysisResponse,
    )
    analysis_data = {}
    if ares["success"]:
        try:
            ai = ResponseParser.extract_json(ares["content"], ArchitectAnalysisResponse)
            analysis_data = ai.model_dump()
            r["analysis_primary"] = analysis_data.get("primary_targets", [])
            r["analysis_new"] = analysis_data.get("new_structures_needed", [])
            r["analysis_scratchpad"] = (analysis_data.get("analysis_scratchpad", "") or "")[:200]
        except Exception:
            pass
    r["analysis_content"] = ares["content"][:300]

    # Step 3: Architect with guidance
    await harness.clear_context()
    arch_system = inject_synthesis_guidance(harness.prompts, intent_key)
    suser = (
        f"Analysis: {json.dumps(analysis_data)}\n"
        f"Intent: {json.dumps(intent_packet)}\n"
        f"Instruction: {instruction}\n"
        f"Code: <code>{code}</code>"
    )
    sres = await harness.generate(
        arch_system, suser,
        temp=0.1, max_tokens=2048,
        response_model=ASTArchitectResponse,
    )
    if sres["success"]:
        try:
            si = ResponseParser.extract_json(sres["content"], ASTArchitectResponse)
            plan = si.ast_modification_plan
            r["plan_mutations"] = len(plan.ast_mutations)
            r["plan_actions"] = [m.action.value for m in plan.ast_mutations]
            r["plan_targets"] = [m.target for m in plan.ast_mutations]
            r["target_class"] = plan.target_class
            r["arch_scratchpad"] = (si.architect_scratchpad or "")[:200]

            # Target format check
            bad = [t for t in r["plan_targets"] if "/" in t or "(" in t or t == ""]
            r["targets_clean"] = len(bad) == 0

            # Coherence: do plan targets reference analysis?
            all_analysis_names = set(r["analysis_primary"] + r["analysis_new"])
            plan_targets_set = set(r["plan_targets"])
            r["chain_coherent"] = len(plan_targets_set & all_analysis_names) > 0 or len(r["plan_targets"]) == 0
        except Exception:
            pass

    r["synthesis_content"] = sres["content"][:300]

    # Hallucination detection (simple — labels not in code as targets for modify)
    code_lower = code.lower()
    for t in r.get("plan_targets", []):
        if t and t not in code_lower:
            r["hallucinations"].append(t)

    return r


async def main():
    print("=" * 60)
    print("SCRIPT 4: FULL PLANNER CHAIN VALIDATION")
    print(f"Cases: {len(TEST_CASES)} (each runs Classifier → Analysis → Architect)")
    print("=" * 60)

    harness = ModelTestHarness("planner")
    await harness.load_model()

    results = []
    for i, case in enumerate(TEST_CASES):
        print(f"\n[{i+1}/{len(TEST_CASES)}] {case['name']}")
        r = await run_chain_case(harness, case)
        results.append(r)
        print(f"  intent: expected={case['expected_intent']} actual={r['actual_intent']} match={r['classifier_match']}")
        print(f"  analysis: primary={r['analysis_primary']} new={r['analysis_new']}")
        print(f"  plan: mutations={r['plan_mutations']} actions={r['plan_actions']} targets_clean={r.get('targets_clean','?')}")
        print(f"  coherent={r.get('chain_coherent','?')} hallucinations={r['hallucinations']}")

    await harness.unload_model()

    classifier_ok = sum(1 for r in results if r.get("classifier_match"))
    plans_with_mutations = sum(1 for r in results if r.get("plan_mutations", 0) > 0)
    coherent = sum(1 for r in results if r.get("chain_coherent"))
    print(f"\nRESULT: {classifier_ok}/{len(results)} classifier correct | {plans_with_mutations}/{len(results)} plans have mutations | {coherent}/{len(results)} chain coherent")

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = f"test_results/planner_chain_new_{ts}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
