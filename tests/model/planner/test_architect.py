"""Script 3: Architect validation — 8 cases with synthesis guidance injection."""
import asyncio
import json
import sys
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.utils.response_parser import ResponseParser
from app.utils.schemas import ASTArchitectResponse
from tests.model.harness import ModelTestHarness


TEST_CASES: List[Dict[str, Any]] = [
    {
        "name": "arch_extract_constant_two_methods",
        "intent": "EXTRACT_CONSTANT",
        "code": "public class Circle { public double calculateArea(double radius) { return 3.14159 * radius * radius; } public double calculateCircumference(double radius) { return 2 * 3.14159 * radius; } }",
        "analysis": {
            "primary_targets": ["calculateArea", "calculateCircumference"],
            "secondary_targets": [],
            "new_structures_needed": ["PI"],
            "must_preserve": [],
        },
        "expected_mutation_count": 3,
        "expected_actions": ["ADD_CONSTANT", "MODIFY_METHOD", "MODIFY_METHOD"],
    },
    {
        "name": "arch_extract_constant_single_method",
        "intent": "EXTRACT_CONSTANT",
        "code": "public class Solution { public int compute(int n) { int res = 1; int mod = 1000000007; for (int i = 1; i <= n; i++) { res = (res * i) % mod; } return res; } }",
        "analysis": {
            "primary_targets": ["compute"],
            "secondary_targets": [],
            "new_structures_needed": ["MOD"],
            "must_preserve": [],
        },
        "expected_mutation_count": 2,
        "expected_actions": ["ADD_CONSTANT", "MODIFY_METHOD"],
    },
    {
        "name": "arch_rename_field_with_accessors",
        "intent": "RENAME_SYMBOL",
        "code": "public class UserManager { private String n; public String getN() { return n; } public void setN(String n) { this.n = n; } }",
        "analysis": {
            "primary_targets": ["n", "getN", "setN"],
            "secondary_targets": [],
            "new_structures_needed": [],
            "must_preserve": [],
        },
        "expected_mutation_count": 3,
        "expected_actions": ["RENAME_SYMBOL", "MODIFY_METHOD", "MODIFY_METHOD"],
    },
    {
        "name": "arch_extract_method_tax",
        "intent": "EXTRACT_METHOD",
        "code": "public class Calculator { public double calculateTotal(double price, int quantity, double taxRate) { double subtotal = price * quantity; double tax = subtotal * taxRate; double total = subtotal + tax; double rounded = Math.round(total * 100.0) / 100.0; return rounded; } }",
        "analysis": {
            "primary_targets": ["calculateTotal"],
            "secondary_targets": [],
            "new_structures_needed": ["computeTaxWithRounding"],
            "must_preserve": [],
        },
        "expected_mutation_count": 2,
        "expected_actions": ["ADD_METHOD", "MODIFY_METHOD"],
    },
    {
        "name": "arch_decompose_boolean_fields",
        "intent": "DECOMPOSE_CONDITIONAL",
        "code": "public class LoanApprover { public boolean isEligible(int age, double income, int creditScore, boolean hasCollateral) { if (age >= 18 && age <= 65 && income > 30000 && creditScore > 650 && hasCollateral) { return true; } return false; } }",
        "analysis": {
            "primary_targets": ["isEligible"],
            "secondary_targets": [],
            "new_structures_needed": ["isAdult", "hasSufficientIncome", "hasGoodCredit"],
            "must_preserve": [],
        },
        "expected_mutation_count": 4,
        "expected_actions": ["ADD_FIELD", "ADD_FIELD", "ADD_FIELD", "MODIFY_METHOD"],
    },
    {
        "name": "arch_flatten_guard_clauses",
        "intent": "FLATTEN_CONDITIONAL",
        "code": "public class Processor { void process(String s) { if (s != null) { if (!s.isEmpty()) { doWork(s); } else { throw new IllegalArgumentException(\"input empty\"); } } else { throw new IllegalArgumentException(\"input null\"); } } }",
        "analysis": {
            "primary_targets": ["process"],
            "secondary_targets": [],
            "new_structures_needed": [],
            "must_preserve": ["Exception: IllegalArgumentException", "String: 'input empty'", "String: 'input null'"],
        },
        "expected_mutation_count": 1,
        "expected_actions": ["MODIFY_METHOD"],
    },
    {
        "name": "arch_split_loop",
        "intent": "SPLIT_LOOP",
        "code": "public void process(int[] arr) { for (int i = 0; i < arr.length; i++) { arr[i] *= 2; System.out.println(arr[i]); } }",
        "analysis": {
            "primary_targets": ["process"],
            "secondary_targets": [],
            "new_structures_needed": [],
            "must_preserve": [],
        },
        "expected_mutation_count": 1,
        "expected_actions": ["MODIFY_METHOD"],
    },
    {
        "name": "arch_consolidate_condition",
        "intent": "CONSOLIDATE_CONDITIONAL",
        "code": "public class Solution { public boolean wordPatternMatch(String pattern, String s) { if (pattern.isEmpty()) return s.isEmpty(); if (s.isEmpty()) return false; return match(pattern, 0, s, 0); } private boolean match(String p, int i, String s, int j) { return false; } } }",
        "analysis": {
            "primary_targets": ["wordPatternMatch"],
            "secondary_targets": [],
            "new_structures_needed": [],
            "must_preserve": [],
        },
        "expected_mutation_count": 1,
        "expected_actions": ["MODIFY_METHOD"],
    },
]


def inject_synthesis_guidance(prompts: dict, intent: str) -> str:
    base = prompts["planner"]["architect"]
    guidance = prompts["planner"].get("synthesis_guidance", {}).get(intent, "")
    return base + "\n" + guidance if guidance else base


async def run_architect_case(harness: ModelTestHarness, case: Dict[str, Any]) -> Dict[str, Any]:
    system_content = inject_synthesis_guidance(harness.prompts, case["intent"])

    user_prompt = (
        f"Analysis: {json.dumps(case['analysis'])}\n"
        f"Intent: {{\"specific_intent\": \"{case['intent']}\"}}\n"
        f"Instruction: example instruction for {case['intent']}\n"
        f"Code: <code>{case['code']}</code>"
    )

    result = await harness.generate(
        system_content,
        user_prompt,
        temp=0.1,
        max_tokens=2048,
        response_model=ASTArchitectResponse,
    )

    r: Dict[str, Any] = {
        "name": case["name"],
        "intent": case["intent"],
        "success": result["success"],
        "content": result["content"][:500],
        "duration": result["duration"],
    }

    if result["success"]:
        try:
            parsed = ResponseParser.extract_json(result["content"], ASTArchitectResponse)
            plan = parsed.ast_modification_plan
            r["target_class"] = plan.target_class
            r["mutation_count"] = len(plan.ast_mutations)
            r["mutations"] = [
                {"action": m.action.value, "target": m.target, "body": (m.details.body_abstract or "")[:100]}
                for m in plan.ast_mutations
            ]
            r["actions"] = [m.action.value for m in plan.ast_mutations]
            r["scratchpad_len"] = len(parsed.architect_scratchpad or "")

            # Checks
            exp_count = case["expected_mutation_count"]
            r["count_match"] = r["mutation_count"] == exp_count
            r["count_diff"] = r["mutation_count"] - exp_count

            exp_actions = case["expected_actions"]
            r["actions_match"] = sorted(r["actions"]) == sorted(exp_actions)

            # Target format: no slashes, no parentheses, no signatures
            targets = [m.target for m in plan.ast_mutations]
            bad_targets = [t for t in targets if "/" in t or "(" in t or t == "ClassName" or t == ""]
            r["targets_clean"] = len(bad_targets) == 0
            r["bad_targets"] = bad_targets

            # Template bleed: no FLATTEN body_abstract in non-FLATTEN plans
            if case["intent"] != "FLATTEN_CONDITIONAL":
                bleed = [
                    m.details.body_abstract or ""
                    for m in plan.ast_mutations
                    if "invert all conditional" in (m.details.body_abstract or "").lower()
                ]
                r["no_template_bleed"] = len(bleed) == 0
                r["bleed_count"] = len(bleed)

            # target_class check
            r["target_class_empty"] = plan.target_class == ""
            r["target_class_placeholder"] = plan.target_class == "ClassName"

        except Exception as e:
            r["parse_error"] = str(e)[:200]

    return r


async def main():
    print("=" * 60)
    print("SCRIPT 3: ARCHITECT VALIDATION (with synthesis guidance)")
    print(f"Cases: {len(TEST_CASES)}")
    print("=" * 60)

    harness = ModelTestHarness("planner")
    await harness.load_model()

    results = []
    for i, case in enumerate(TEST_CASES):
        print(f"\n[{i+1}/{len(TEST_CASES)}] {case['name']} (intent={case['intent']})")
        r = await run_architect_case(harness, case)
        results.append(r)
        print(f"  mutations={r.get('mutation_count')} (expected {case['expected_mutation_count']}) | count_ok={r.get('count_match')}")
        print(f"  actions={r.get('actions')} | actions_ok={r.get('actions_match')}")
        print(f"  targets_clean={r.get('targets_clean')} | bleed={r.get('bleed_count', 'N/A')} | {r['duration']}s")
        if r.get("bad_targets"):
            print(f"  BAD TARGETS: {r['bad_targets']}")

    await harness.unload_model()

    count_ok = sum(1 for r in results if r.get("count_match"))
    actions_ok = sum(1 for r in results if r.get("actions_match"))
    targets_ok = sum(1 for r in results if r.get("targets_clean"))
    print(f"\nRESULT: {count_ok}/{len(results)} count correct | {actions_ok}/{len(results)} actions correct | {targets_ok}/{len(results)} targets clean")

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = f"tests/results/architect_new_{ts}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
