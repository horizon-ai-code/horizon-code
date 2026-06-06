"""Generator validation — linear plan format + dynamic coder_guidance."""
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.utils.formatters import format_plan_for_generator
from tests.model.harness import ModelTestHarness


TEST_CASES: List[Dict[str, Any]] = [
    # ---- FLATTEN_CONDITIONAL (2) ----
    {
        "name": "gen_flatten_orderprocessor",
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
        "plan": {
            "target_class": "OrderProcessor",
            "ast_mutations": [{
                "action": "MODIFY_METHOD", "target": "processOrder",
                "details": {
                    "modifiers": ["public"], "type": "void", "parameters": [],
                    "logic_changes": ["Flatten nested ifs to guard clauses"],
                    "body_abstract": "Move each invalid condition to the method top as a guard clause with immediate throw. All exception types and messages must match exactly.",
                }
            }],
        },
        "intent": "FLATTEN_CONDITIONAL",
        "check_syntax": True,
        "check_anti_merge": True,
        "check_anti_exception": True,
    },
    {
        "name": "gen_flatten_simple_ifs",
        "code": "void process(Object x, Object y) { if (x != null) { if (y != null) { doWork(x, y); } else { throw new IllegalArgumentException(\"y is null\"); } } else { throw new IllegalArgumentException(\"x is null\"); } }",
        "plan": {
            "target_class": "",
            "ast_mutations": [{
                "action": "MODIFY_METHOD", "target": "process",
                "details": {
                    "modifiers": [], "type": "void",
                    "parameters": [{"type": "Object", "name": "x"}, {"type": "Object", "name": "y"}],
                    "logic_changes": ["Flatten nested ifs to guard clauses"],
                    "body_abstract": "Check x==null throw, check y==null throw, then doWork",
                }
            }],
        },
        "intent": "FLATTEN_CONDITIONAL",
        "check_syntax": True,
        "check_anti_merge": True,
    },
    # ---- EXTRACT_METHOD (3) ----
    {
        "name": "gen_extract_tax_helper",
        "code": """public class Calculator {
    public double calculateTotal(double price, int quantity, double taxRate) {
        double subtotal = price * quantity;
        double tax = subtotal * taxRate;
        return Math.round((subtotal + tax) * 100.0) / 100.0;
    }
}""",
        "plan": {
            "target_class": "Calculator",
            "ast_mutations": [
                {
                    "action": "ADD_METHOD", "target": "computeTaxWithRounding",
                    "details": {
                        "modifiers": ["private"], "type": "double",
                        "parameters": [{"type": "double", "name": "subtotal"}, {"type": "double", "name": "taxRate"}],
                        "logic_changes": ["Extract tax calculation and rounding"],
                        "body_abstract": "Compute tax, add to subtotal, round to 2 decimal places, return result",
                    }
                },
                {
                    "action": "MODIFY_METHOD", "target": "calculateTotal",
                    "details": {
                        "modifiers": ["public"], "type": "double",
                        "parameters": [{"type": "double", "name": "price"}, {"type": "int", "name": "quantity"}, {"type": "double", "name": "taxRate"}],
                        "logic_changes": ["Replace tax logic with call to computeTaxWithRounding"],
                        "body_abstract": "Compute subtotal from price*quantity, call computeTaxWithRounding, return result",
                    }
                },
            ],
        },
        "intent": "EXTRACT_METHOD",
        "check_syntax": True,
        "check_has_new_method": "computeTaxWithRounding",
    },
    {
        "name": "gen_extract_prime_count",
        "code": """public class Solution {
    public int numPrimeArrangements(int n) {
        boolean[] isPrime = new boolean[n + 1];
        java.util.Arrays.fill(isPrime, true);
        isPrime[0] = false; isPrime[1] = false;
        for (int i = 2; i * i <= n; i++) if (isPrime[i]) {
            for (int j = i * i; j <= n; j += i) isPrime[j] = false;
        }
        int pc = 0;
        for (int i = 2; i <= n; i++) if (isPrime[i]) pc++;
        long res = 1, mod = 1000000007;
        for (int i = 1; i <= pc; i++) res = (res * i) % mod;
        for (int i = 1; i <= n - pc; i++) res = (res * i) % mod;
        return (int) res;
    }
}""",
        "plan": {
            "target_class": "Solution",
            "ast_mutations": [
                {
                    "action": "ADD_METHOD", "target": "countPrimes",
                    "details": {
                        "modifiers": ["private"], "type": "int",
                        "parameters": [{"type": "int", "name": "n"}],
                        "logic_changes": ["Move Sieve of Eratosthenes into helper"],
                        "body_abstract": "Sieve of Eratosthenes up to n, return prime count",
                    }
                },
                {
                    "action": "MODIFY_METHOD", "target": "numPrimeArrangements",
                    "details": {
                        "modifiers": ["public"], "type": "int",
                        "parameters": [{"type": "int", "name": "n"}],
                        "logic_changes": ["Replace prime counting logic with call to countPrimes"],
                        "body_abstract": "Call countPrimes(n), compute factorial permutations, return result",
                    }
                },
            ],
        },
        "intent": "EXTRACT_METHOD",
        "check_syntax": True,
        "check_has_new_method": "countPrimes",
    },
    {
        "name": "gen_extract_set_zeroes_helpers",
        "code": "public class Solution { public void setZeroes(int[][] matrix) { boolean fr = false, fc = false; for (int i = 0; i < matrix.length; i++) { for (int j = 0; j < matrix[0].length; j++) { if (matrix[i][j] == 0) { if (i == 0) fr = true; if (j == 0) fc = true; matrix[0][j] = 0; matrix[i][0] = 0; } } } for (int i = 1; i < matrix.length; i++) { for (int j = 1; j < matrix[0].length; j++) { if (matrix[i][0] == 0 || matrix[0][j] == 0) matrix[i][j] = 0; } } if (fr) { for (int j = 0; j < matrix[0].length; j++) matrix[0][j] = 0; } if (fc) { for (int i = 0; i < matrix.length; i++) matrix[i][0] = 0; } } }",
        "plan": {
            "target_class": "Solution",
            "ast_mutations": [
                {
                    "action": "ADD_METHOD", "target": "setFirstRowColZeros",
                    "details": {"modifiers": ["private"], "type": "void",
                        "parameters": [{"type": "int[][]", "name": "matrix"}],
                        "logic_changes": ["Extract first row/column marking logic"],
                        "body_abstract": "Mark first row and column based on zero cells",
                    }
                },
                {
                    "action": "MODIFY_METHOD", "target": "setZeroes",
                    "details": {"modifiers": ["public"], "type": "void",
                        "parameters": [{"type": "int[][]", "name": "matrix"}],
                        "logic_changes": ["Replace marking logic with call to setFirstRowColZeros"],
                        "body_abstract": "Call setFirstRowColZeros, then set zeros based on markers",
                    }
                },
            ],
        },
        "intent": "EXTRACT_METHOD",
        "check_syntax": True,
        "check_has_new_method": "setFirstRowColZeros",
    },
    # ---- RENAME_SYMBOL (2) ----
    {
        "name": "gen_rename_field",
        "code": "public class UserManager { private String n; public String getN() { return n; } public void setN(String n) { this.n = n; } }",
        "plan": {
            "target_class": "UserManager",
            "ast_mutations": [{
                "action": "RENAME_SYMBOL", "target": "n",
                "details": {
                    "logic_changes": ["Rename n to username everywhere"],
                    "body_abstract": "Rename field n to username. Update getN to getUsername, setN to setUsername.",
                }
            }],
        },
        "intent": "RENAME_SYMBOL",
        "check_syntax": True,
        "check_old_name_absent": "getN()",
    },
    {
        "name": "gen_rename_variables",
        "code": "public class Solution { public ListNode removeNthFromEnd(ListNode head, int n) { ListNode dummy = new ListNode(0, head); ListNode first = head; ListNode second = dummy; for (int i = 0; i < n; i++) first = first.next; while (first != null) { first = first.next; second = second.next; } second.next = second.next.next; return dummy.next; } }",
        "plan": {
            "target_class": "Solution",
            "ast_mutations": [
                {
                    "action": "RENAME_SYMBOL", "target": "first",
                    "details": {"logic_changes": ["Rename first to fast"], "body_abstract": "Rename first to fast everywhere", "modifiers": [], "type": "", "parameters": []}
                },
                {
                    "action": "RENAME_SYMBOL", "target": "second",
                    "details": {"logic_changes": ["Rename second to slow"], "body_abstract": "Rename second to slow everywhere", "modifiers": [], "type": "", "parameters": []}
                },
            ],
        },
        "intent": "RENAME_SYMBOL",
        "check_syntax": True,
        "check_old_name_absent": "first;",
    },
    # ---- EXTRACT_CONSTANT (2) ----
    {
        "name": "gen_extract_pi_constant",
        "code": "public class Circle { public double calculateArea(double radius) { return 3.14159 * radius * radius; } public double calculateCircumference(double radius) { return 2 * 3.14159 * radius; } }",
        "plan": {
            "target_class": "Circle",
            "ast_mutations": [
                {
                    "action": "ADD_CONSTANT", "target": "PI",
                    "details": {"modifiers": ["static", "final"], "type": "double", "parameters": [],
                        "logic_changes": ["Extract 3.14159 into constant PI"],
                        "body_abstract": "Declare PI = 3.14159 as a class-level constant",
                    }
                },
                {
                    "action": "MODIFY_METHOD", "target": "calculateArea",
                    "details": {"modifiers": ["public"], "type": "", "parameters": [],
                        "logic_changes": ["Replace 3.14159 with PI"],
                        "body_abstract": "Replace 3.14159 with PI in area calculation",
                    }
                },
                {
                    "action": "MODIFY_METHOD", "target": "calculateCircumference",
                    "details": {"modifiers": ["public"], "type": "", "parameters": [],
                        "logic_changes": ["Replace 3.14159 with PI"],
                        "body_abstract": "Replace 3.14159 with PI in circumference calculation",
                    }
                },
            ],
        },
        "intent": "EXTRACT_CONSTANT",
        "check_syntax": True,
        "check_has_constant": "PI",
    },
    {
        "name": "gen_extract_mod_constant",
        "code": "public class Solution { public int compute(int n) { int result = 1; for (int i = 1; i <= n; i++) { result = result * i % 1000000007; } return result; } }",
        "plan": {
            "target_class": "Solution",
            "ast_mutations": [
                {
                    "action": "ADD_CONSTANT", "target": "MOD",
                    "details": {"modifiers": ["static", "final"], "type": "int", "parameters": [],
                        "logic_changes": ["Extract 1000000007 into constant MOD"],
                        "body_abstract": "Declare MOD = 1000000007",
                    }
                },
                {
                    "action": "MODIFY_METHOD", "target": "compute",
                    "details": {"modifiers": ["public"], "type": "", "parameters": [{"type": "int", "name": "n"}],
                        "logic_changes": ["Replace 1000000007 with MOD"],
                        "body_abstract": "Replace 1000000007 with MOD in computation",
                    }
                },
            ],
        },
        "intent": "EXTRACT_CONSTANT",
        "check_syntax": True,
        "check_has_constant": "MOD",
    },
    # ---- DECOMPOSE + SPLIT (2) ----
    {
        "name": "gen_decompose_simple",
        "code": "public class A { boolean m(int x) { if (x > 0 && x < 10) return true; return false; } }",
        "plan": {
            "target_class": "A",
            "ast_mutations": [{
                "action": "MODIFY_METHOD", "target": "m",
                "details": {"modifiers": [], "type": "boolean", "parameters": [{"type": "int", "name": "x"}],
                    "logic_changes": ["Decompose compound condition into named booleans"],
                    "body_abstract": "Create boolean isPositive = x > 0 and isSmall = x < 10. Return isPositive && isSmall.",
                }
            }],
        },
        "intent": "DECOMPOSE_CONDITIONAL",
        "check_syntax": True,
    },
    {
        "name": "gen_split_simple_loop",
        "code": "void process(int[] arr) { for (int i = 0; i < arr.length; i++) { arr[i] *= 2; System.out.println(arr[i]); } }",
        "plan": {
            "target_class": "",
            "ast_mutations": [{
                "action": "MODIFY_METHOD", "target": "process",
                "details": {"modifiers": [], "type": "void", "parameters": [{"type": "int[]", "name": "arr"}],
                    "logic_changes": ["Split loop into two: doubling and printing"],
                    "body_abstract": "First loop: arr[i] *= 2. Second loop: System.out.println(arr[i])",
                }
            }],
        },
        "intent": "SPLIT_LOOP",
        "check_syntax": True,
    },
]


def inject_generator_guidance(prompts: dict, intent: str) -> str:
    base = prompts["generator"]["coder"]
    guidance = prompts["generator"].get("coder_guidance", {}).get(intent, "")
    return base + "\n" + guidance if guidance else base


def check_syntax(code: str) -> bool:
    """Basic Java syntax check."""
    if not code or len(code) < 5:
        return False
    try:
        import javalang
        wrapped = f"class __Wrap__ {{ {code} }}" if "class" not in code else code
        javalang.parse.parse(wrapped)
        return True
    except Exception:
        return False


def check_anti_merge(code: str) -> List[str]:
    """Check if guard clauses were merged with || or &&."""
    issues = []
    # Count distinct throw statements
    throws = re.findall(r'throw\s+new\s+\w+Exception', code)
    # Check for combined null checks in guard clauses
    null_checks = re.findall(r'if\s*\([^)]*\|\|[^)]*\)\s*\{?\s*throw', code)
    if null_checks and len(throws) < 3:
        issues.append(f"Merged guard clause detected: {null_checks[0][:60]}")
    return issues


def check_anti_exception(code: str, original: str) -> List[str]:
    """Check if exception types changed."""
    orig_exc = set(re.findall(r'throw\s+new\s+(\w+Exception)', original))
    new_exc = set(re.findall(r'throw\s+new\s+(\w+Exception)', code))
    missing = orig_exc - new_exc
    added = new_exc - orig_exc
    issues = []
    if missing and added:
        issues.append(f"Exception types changed: missing={missing}, added={added}")
    return issues


async def run_generator_case(harness: ModelTestHarness, case: Dict[str, Any]) -> Dict[str, Any]:
    intent = case["intent"]
    code = case["code"]
    plan = case["plan"]

    system_content = inject_generator_guidance(harness.prompts, intent)
    user_prompt = format_plan_for_generator(plan, code)

    result = await harness.generate(
        system_content, user_prompt,
        temp=0.1, max_tokens=2048,
    )

    raw = result["content"]
    output_code = ""
    code_match = re.search(r'<code>(.*?)</code>', raw, re.DOTALL)
    if code_match:
        output_code = code_match.group(1).strip()

    r: Dict[str, Any] = {
        "name": case["name"],
        "intent": intent,
        "code_len": len(code),
        "output_len": len(output_code),
        "syntax_valid": check_syntax(output_code) if output_code else False,
        "duration": result["duration"],
        "output_code": output_code[:1000],
        "raw_content": raw[:300],
        "issues": [],
    }

    if not output_code:
        r["issues"].append("No <code> block found in output")
        r["verdict"] = "FAIL"
    elif not r["syntax_valid"]:
        r["issues"].append("Invalid Java syntax")
        r["verdict"] = "FAIL"
    else:
        # Check anti-patterns
        anti_merge = check_anti_merge(output_code) if case.get("check_anti_merge") else []
        anti_exc = check_anti_exception(output_code, code) if case.get("check_anti_exception") else []
        r["issues"].extend(anti_merge)
        r["issues"].extend(anti_exc)

        # Check for renamed symbols
        if case.get("check_old_name_absent"):
            old_name = case["check_old_name_absent"]
            if old_name in output_code:
                r["issues"].append(f"Old name '{old_name}' still present")

        # Check for new methods/constants
        if case.get("check_has_new_method") and case["check_has_new_method"] not in output_code:
            r["issues"].append(f"New method '{case['check_has_new_method']}' not created")
        if case.get("check_has_constant") and case["check_has_constant"] not in output_code:
            r["issues"].append(f"Constant '{case['check_has_constant']}' not declared")

        # Check method count preservation for extract_constant
        if intent == "EXTRACT_CONSTANT":
            orig_methods = len(re.findall(r'(?:public|private|protected)\s+\w+\s+\w+\s*\(', code))
            new_methods = len(re.findall(r'(?:public|private|protected)\s+\w+\s+\w+\s*\(', output_code))
            if new_methods < orig_methods:
                r["issues"].append(f"Methods dropped: {orig_methods} → {new_methods}")

        r["verdict"] = "PASS" if not r["issues"] else "FAIL"

    return r


async def main():
    print("=" * 60)
    print("GENERATOR VALIDATION (linear plan + dynamic guidance)")
    print(f"Cases: {len(TEST_CASES)}")
    print("=" * 60)

    harness = ModelTestHarness("generator")
    await harness.load_model()

    results = []
    for i, case in enumerate(TEST_CASES):
        print(f"\n[{i+1}/{len(TEST_CASES)}] {case['name']} (intent={case['intent']})")
        r = await run_generator_case(harness, case)
        results.append(r)
        print(f"  verdict={r['verdict']} | syntax={r['syntax_valid']} | issues={len(r['issues'])} | {r['duration']}s")
        if r["issues"]:
            for issue in r["issues"]:
                print(f"    - {issue}")
        if r["syntax_valid"] and r.get("output_code"):
            out = r["output_code"].replace("\n", "\\n")
            print(f"  output: {out[:200]}...")

    await harness.unload_model()

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"\nRESULT: {passed}/{len(results)} PASS")

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = f"tests/results/generator_new_{ts}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
