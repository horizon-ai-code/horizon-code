"""Script 2: Analysis validation — 8 cases with dynamic guidance injection."""
import asyncio
import json
import sys
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.utils.response_parser import ResponseParser
from app.utils.schemas import ArchitectAnalysisResponse
from tests.model.harness import ModelTestHarness


TEST_CASES: List[Dict[str, Any]] = [
    {
        "name": "analysis_const_two_methods",
        "intent": "EXTRACT_CONSTANT",
        "code": "public class Circle { public double calculateArea(double radius) { return 3.14159 * radius * radius; } public double calculateCircumference(double radius) { return 2 * 3.14159 * radius; } }",
        "instruction": "Extract the magic number 3.14159 into a named constant PI.",
        "expected_primary": ["calculateArea", "calculateCircumference"],
        "expected_new": ["PI"],
        "expected_preserve": [],
    },
    {
        "name": "analysis_const_single_method",
        "intent": "EXTRACT_CONSTANT",
        "code": "public int compute(int n) { int mod = 1000000007; int res = 1; for (int i = 1; i <= n; i++) { res = (res * i) % mod; } return res; }",
        "instruction": "Extract the magic number 1000000007 into a constant MOD.",
        "expected_primary": ["compute"],
        "expected_new": ["MOD"],
        "expected_preserve": [],
    },
    {
        "name": "analysis_rename_field_accessors",
        "intent": "RENAME_SYMBOL",
        "code": "public class UserManager { private String n; public String getN() { return n; } public void setN(String n) { this.n = n; } }",
        "instruction": "Rename the field n to username and update all references.",
        "expected_primary": ["n", "getN", "setN"],
        "expected_new": [],
        "expected_preserve": [],
    },
    {
        "name": "analysis_rename_variables",
        "intent": "RENAME_SYMBOL",
        "code": "public class Solution { public ListNode removeNthFromEnd(ListNode head, int n) { ListNode dummy = new ListNode(0, head); ListNode first = head; ListNode second = dummy; for (int i = 0; i < n; i++) first = first.next; while (first != null) { first = first.next; second = second.next; } second.next = second.next.next; return dummy.next; } }",
        "instruction": "Rename first->fast, second->slow, head->startNode everywhere.",
        "expected_primary": ["first", "second", "head"],
        "expected_new": [],
        "expected_preserve": [],
    },
    {
        "name": "analysis_extract_method_tax",
        "intent": "EXTRACT_METHOD",
        "code": "public class Calculator { public double calculateTotal(double price, int quantity, double taxRate) { double subtotal = price * quantity; double tax = subtotal * taxRate; double total = subtotal + tax; double rounded = Math.round(total * 100.0) / 100.0; return rounded; } }",
        "instruction": "Extract the tax calculation logic into a separate private method called computeTaxWithRounding.",
        "expected_primary": ["calculateTotal"],
        "expected_new": ["computeTaxWithRounding"],
        "expected_preserve": [],
    },
    {
        "name": "analysis_decompose_isEligible",
        "intent": "DECOMPOSE_CONDITIONAL",
        "code": "public class LoanApprover { public boolean isEligible(int age, double income, int creditScore, boolean hasCollateral) { if (age >= 18 && age <= 65 && income > 30000 && creditScore > 650 && hasCollateral) { return true; } return false; } }",
        "instruction": "Decompose the complex conditional in isEligible into well-named boolean variables for each condition.",
        "expected_primary": ["isEligible"],
        "expected_new": True,  # any non-empty list — don't hardcode exact names
        "expected_preserve": [],
    },
    {
        "name": "analysis_flatten_preserve_exceptions",
        "intent": "FLATTEN_CONDITIONAL",
        "code": "public class Processor { void process(String s) { if (s != null) { if (!s.isEmpty()) { doWork(s); } else { throw new IllegalArgumentException(\"input empty\"); } } else { throw new IllegalArgumentException(\"input null\"); } } }",
        "instruction": "Flatten the nested ifs using guard clauses. Preserve exception messages.",
        "expected_primary": ["process"],
        "expected_new": [],
        "expected_preserve": True,  # should contain both exception messages
    },
    {
        "name": "analysis_consolidate_wordPattern",
        "intent": "CONSOLIDATE_CONDITIONAL",
        "code": "public class Solution { public boolean wordPatternMatch(String pattern, String s) { if (pattern.isEmpty()) { return s.isEmpty(); } if (s.isEmpty()) { return false; } return match(pattern, 0, s, 0); } private boolean match(String p, int i, String s, int j) { return false; } }",
        "instruction": "Consolidate the duplicate empty-string checks into a single condition.",
        "expected_primary": ["wordPatternMatch"],
        "expected_new": [],
        "expected_preserve": [],
    },
]


def inject_guidance(prompts: dict, intent: str) -> str:
    base = prompts["planner"]["architect_analysis"]
    guidance = prompts["planner"].get("analysis_guidance", {}).get(intent, "")
    return base + "\n" + guidance if guidance else base


async def run_analysis_case(harness: ModelTestHarness, case: Dict[str, Any]) -> Dict[str, Any]:
    system_content = inject_guidance(harness.prompts, case["intent"])

    user_prompt = (
        f"Intent Packet: {{\"specific_intent\": \"{case['intent']}\"}}\n"
        f"User Instruction: {case['instruction']}\n"
        f"Code: <code>{case['code']}</code>"
    )

    result = await harness.generate(
        system_content,
        user_prompt,
        temp=0.1,
        max_tokens=1024,
        response_model=ArchitectAnalysisResponse,
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
            parsed = ResponseParser.extract_json(result["content"], ArchitectAnalysisResponse)
            r["primary_targets"] = parsed.primary_targets or []
            r["secondary_targets"] = parsed.secondary_targets or []
            r["new_structures_needed"] = parsed.new_structures_needed or []
            r["must_preserve"] = parsed.must_preserve or []
            r["scratchpad_len"] = len(parsed.analysis_scratchpad or "")

            # Completeness checks
            exp_p = case["expected_primary"]
            if isinstance(exp_p, list):
                missing = [t for t in exp_p if t not in r["primary_targets"]]
                r["primary_complete"] = len(missing) == 0
                r["primary_missing"] = missing
            else:
                r["primary_complete"] = None

            exp_n = case["expected_new"]
            if isinstance(exp_n, list):
                r["new_complete"] = sorted(r["new_structures_needed"]) == sorted(exp_n)
            elif exp_n is True:
                r["new_complete"] = len(r["new_structures_needed"]) > 0
            else:
                r["new_complete"] = None

            exp_mp = case["expected_preserve"]
            if exp_mp is True:
                r["preserve_complete"] = len(r["must_preserve"]) > 0
            elif isinstance(exp_mp, list):
                r["preserve_complete"] = None
            else:
                r["preserve_complete"] = None

            # Format check: no dicts in lists
            all_strings = (
                all(isinstance(x, str) for x in r["primary_targets"])
                and all(isinstance(x, str) for x in r["new_structures_needed"])
                and all(isinstance(x, str) for x in r["must_preserve"])
            )
            r["format_strings_only"] = all_strings

        except Exception as e:
            r["parse_error"] = str(e)[:200]

    return r


async def main():
    print("=" * 60)
    print("SCRIPT 2: ANALYSIS VALIDATION (with dynamic guidance)")
    print(f"Cases: {len(TEST_CASES)}")
    print("=" * 60)

    harness = ModelTestHarness("planner")
    await harness.load_model()

    results = []
    for i, case in enumerate(TEST_CASES):
        print(f"\n[{i+1}/{len(TEST_CASES)}] {case['name']} (intent={case['intent']})")
        r = await run_analysis_case(harness, case)
        results.append(r)
        print(f"  primary={r.get('primary_targets')}")
        print(f"  new={r.get('new_structures_needed')}")
        print(f"  preserve={r.get('must_preserve')[:3] if r.get('must_preserve') else '[]'}")
        print(f"  primary_ok={r.get('primary_complete')} new_ok={r.get('new_complete')} strings_only={r.get('format_strings_only')} | {r['duration']}s")

    await harness.unload_model()

    complete = sum(1 for r in results if r.get("primary_complete") is not False)
    format_ok = sum(1 for r in results if r.get("format_strings_only"))
    print(f"\nRESULT: {complete}/{len(results)} analysis complete | {format_ok}/{len(results)} format valid")

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = f"tests/results/analysis_new_{ts}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
