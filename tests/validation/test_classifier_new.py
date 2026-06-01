"""Script 1: Classifier validation — 10 cases (5 existing + 5 new)."""
import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.utils.response_parser import ResponseParser
from app.utils.schemas import IntentClassifierResponse
from tests.model_tests.harness import ModelTestHarness


TEST_CASES: List[Dict[str, Any]] = [
    # ---- EXISTING (regression) ----
    {
        "name": "regression_flat_orderprocessor",
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
        "name": "regression_extract_set_zeroes",
        "code": "public class Solution { public void setZeroes(int[][] matrix) { boolean fr = false, fc = false; for (int i = 0; i < matrix.length; i++) { for (int j = 0; j < matrix[0].length; j++) { if (matrix[i][j] == 0) { if (i == 0) fr = true; if (j == 0) fc = true; matrix[0][j] = 0; matrix[i][0] = 0; } } } for (int i = 1; i < matrix.length; i++) { for (int j = 1; j < matrix[0].length; j++) { if (matrix[i][0] == 0 || matrix[0][j] == 0) matrix[i][j] = 0; } } if (fr) { for (int j = 0; j < matrix[0].length; j++) matrix[0][j] = 0; } if (fc) { for (int i = 0; i < matrix.length; i++) matrix[i][0] = 0; } } }",
        "instruction": "Extract three private methods from setZeroes: markZeroMarkers, setInnerZeros, and setFirstRowColZeros.",
        "expected_intent": "EXTRACT_METHOD",
    },
    {
        "name": "regression_rename_remove_nth",
        "code": "public class Solution { public ListNode removeNthFromEnd(ListNode head, int n) { ListNode dummy = new ListNode(0, head); ListNode first = head; ListNode second = dummy; for (int i = 0; i < n; i++) first = first.next; while (first != null) { first = first.next; second = second.next; } second.next = second.next.next; return dummy.next; } }",
        "instruction": "Rename first->fast, second->slow, head->startNode everywhere.",
        "expected_intent": "RENAME_SYMBOL",
    },
    {
        "name": "regression_const_circle_pi",
        "code": "public class Circle { public double calculateArea(double radius) { return 3.14159 * radius * radius; } public double calculateCircumference(double radius) { return 2 * 3.14159 * radius; } }",
        "instruction": "Extract the magic number 3.14159 into a named constant PI.",
        "expected_intent": "EXTRACT_CONSTANT",
    },
    {
        "name": "regression_decomp_closed_island",
        "code": "public class Solution { public int closedIsland(int[][] grid) { int n = grid.length, m = grid[0].length, count = 0; for (int i = 0; i < n; i++) { for (int j = 0; j < m; j++) { if (grid[i][j] == 0) { if (dfs(grid, i, j, n, m)) count++; } } } return count; } private boolean dfs(int[][] grid, int x, int y, int n, int m) { if (x < 0 || x >= n || y < 0 || y >= m) return false; if (grid[x][y] == 1 || grid[x][y] == -1) return true; grid[x][y] = -1; boolean a = dfs(grid, x+1, y, n, m); boolean b = dfs(grid, x-1, y, n, m); boolean c = dfs(grid, x, y+1, n, m); boolean d = dfs(grid, x, y-1, n, m); return a && b && c && d; } }",
        "instruction": "Decompose the complex DFS boundary condition into well-named booleans: isInBounds, isOnBorder, isUnvisited.",
        "expected_intent": "DECOMPOSE_CONDITIONAL",
    },
    # ---- NEW (polish file + custom) ----
    {
        "name": "new_inline_method_canWinNim",
        "code": "public boolean canWinNim(int n) { return n % 4 != 0; }",
        "instruction": "Remove the method and inline the return expression n % 4 != 0 at every call site.",
        "expected_intent": "INLINE_METHOD",
    },
    {
        "name": "new_split_loop_minOps",
        "code": "public int minOperations(int[] nums) { int n = nums.length, ops = 0; for (int i = 0; i <= n - 3; i++) { if (nums[i] == 0) { nums[i] ^= 1; nums[i+1] ^= 1; nums[i+2] ^= 1; ops++; } } for (int i = 0; i < n; i++) { if (nums[i] == 0) return -1; } return ops; }",
        "instruction": "Separate the counting loop from the checking loop into two distinct loops.",
        "expected_intent": "SPLIT_LOOP",
    },
    {
        "name": "new_stream_pipeline_findMin",
        "code": "public int findMin(int[] nums) { int left = 0, right = nums.length - 1; while (left < right) { int mid = left + (right - left) / 2; if (nums[mid] > nums[right]) left = mid + 1; else right = mid; } return nums[left]; }",
        "instruction": "Replace the while loop with stream operations using IntStream to find the minimum.",
        "expected_intent": "REPLACE_LOOP_WITH_PIPELINE",
    },
    {
        "name": "new_extract_variable_squared",
        "code": "public int compute(int n) { return n * n + 2 * n * n; }",
        "instruction": "Extract the expression n * n into a local variable called squared.",
        "expected_intent": "EXTRACT_VARIABLE",
    },
    {
        "name": "new_remove_flag_found",
        "code": "public int search(int[] arr, int target) { boolean found = false; int result = -1; for (int i = 0; i < arr.length; i++) { if (arr[i] == target) { found = true; result = i; break; } } if (found) return result; return -1; }",
        "instruction": "Remove the found flag variable and use early return instead.",
        "expected_intent": "REMOVE_CONTROL_FLAG",
    },
]


async def run_classifier_case(harness: ModelTestHarness, case: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"<code>{case['code']}</code>\n<instruction>{case['instruction']}</instruction>"
    result = await harness.generate(
        harness.prompts["planner"]["classifier"],
        prompt,
        temp=0.1,
        max_tokens=500,
        response_model=IntentClassifierResponse,
    )

    r: Dict[str, Any] = {
        "name": case["name"],
        "expected_intent": case["expected_intent"],
        "success": result["success"],
        "content": result["content"][:500],
        "duration": result["duration"],
    }

    if result["success"]:
        try:
            parsed = ResponseParser.extract_json(result["content"], IntentClassifierResponse)
            r["actual_intent"] = parsed.intent_packet.specific_intent.value
            r["intent_match"] = r["actual_intent"] == case["expected_intent"]
            r["scratchpad_len"] = len(parsed.classification_scratchpad or "")
            scope = parsed.intent_packet.scope_anchor
            r["scope_class"] = scope.target_class or ""
            r["scope_member"] = scope.member or ""
            r["scope_unit"] = scope.unit_type.value
        except Exception as e:
            r["parse_error"] = str(e)[:200]
    else:
        r["actual_intent"] = "PARSE_ERROR"

    return r


async def main():
    print("=" * 60)
    print("SCRIPT 1: CLASSIFIER VALIDATION")
    print(f"Cases: {len(TEST_CASES)}")
    print("=" * 60)

    harness = ModelTestHarness("planner")
    await harness.load_model()

    results = []
    for i, case in enumerate(TEST_CASES):
        print(f"\n[{i+1}/{len(TEST_CASES)}] {case['name']}")
        r = await run_classifier_case(harness, case)
        results.append(r)
        match = "✓" if r.get("intent_match") else "✗"
        print(f"  {match} expected={case['expected_intent']} actual={r.get('actual_intent','?')} | scratchpad={r.get('scratchpad_len',0)}ch | {r['duration']}s")

    await harness.unload_model()

    correct = sum(1 for r in results if r.get("intent_match"))
    print(f"\nRESULT: {correct}/{len(results)} correct")

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = f"test_results/classifier_new_{ts}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
