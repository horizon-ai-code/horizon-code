import asyncio
import json
import re
import sys
from typing import Any, Dict, List

sys.path.insert(0, ".")

import javalang

from app.modules.validator import ASTWalker
from app.utils.response_parser import ResponseParser
from tests.model.harness import ModelTestHarness


TEST_CASES: List[Dict[str, Any]] = [
    # ---- EXTRACT_METHOD (3) ----
    {
        "name": "gen_extract_tax_helper",
        "intent": "EXTRACT_METHOD",
        "code": """public class Calculator {
    public double calculateTotal(double price, int quantity, double taxRate) {
        double subtotal = price * quantity;
        double tax = subtotal * taxRate;
        double total = subtotal + tax;
        double rounded = Math.round(total * 100.0) / 100.0;
        return rounded;
    }
}""",
        "plan": {
            "target_class": "Calculator",
            "ast_mutations": [
                {
                    "action": "ADD_METHOD",
                    "target": "computeTaxWithRounding",
                    "details": {
                        "modifiers": ["private"],
                        "type": "double",
                        "parameters": [{"type": "double", "name": "subtotal"}, {"type": "double", "name": "taxRate"}],
                        "logic_changes": ["Extract tax calculation and rounding"],
                        "body_abstract": "Compute tax, add to subtotal, round to 2 decimal places, return result"
                    }
                },
                {
                    "action": "MODIFY_METHOD",
                    "target": "calculateTotal",
                    "details": {
                        "modifiers": ["public"],
                        "type": "double",
                        "parameters": [{"type": "double", "name": "price"}, {"type": "int", "name": "quantity"}, {"type": "double", "name": "taxRate"}],
                        "logic_changes": ["Replace tax logic with call to computeTaxWithRounding"],
                        "body_abstract": "Compute subtotal from price*quantity, call computeTaxWithRounding, return result"
                    }
                }
            ]
        },
    },
    {
        "name": "gen_extract_prime_count",
        "intent": "EXTRACT_METHOD",
        "code": """public int numPrimeArrangements(int n) {
    boolean[] isPrime = new boolean[n + 1];
    Arrays.fill(isPrime, true); isPrime[0] = false; isPrime[1] = false;
    for (int i = 2; i * i <= n; i++) if (isPrime[i])
        for (int j = i * i; j <= n; j += i) isPrime[j] = false;
    int pc = 0; for (int i = 2; i <= n; i++) if (isPrime[i]) pc++;
    int cc = n - pc;
    long res = 1; int MOD = 1000000007;
    for (int i = 1; i <= pc; i++) res = res * i % MOD;
    for (int i = 1; i <= cc; i++) res = res * i % MOD;
    return (int) res;
}""",
        "plan": {
            "target_class": "Solution",
            "ast_mutations": [
                {
                    "action": "ADD_METHOD",
                    "target": "countPrimes",
                    "details": {
                        "modifiers": ["private"],
                        "type": "int",
                        "parameters": [{"type": "int", "name": "n"}],
                        "logic_changes": ["Extract Sieve of Eratosthenes"],
                        "body_abstract": "Run Sieve up to n, return count of primes"
                    }
                },
                {
                    "action": "MODIFY_METHOD",
                    "target": "numPrimeArrangements",
                    "details": {
                        "modifiers": ["public"],
                        "type": "int",
                        "parameters": [{"type": "int", "name": "n"}],
                        "logic_changes": ["Replace sieve logic with call to countPrimes"],
                        "body_abstract": "Call countPrimes(n), compute factorial result, return as int"
                    }
                }
            ]
        },
    },
    {
        "name": "gen_extract_set_zeroes_helpers",
        "intent": "EXTRACT_METHOD",
        "code": """public void setZeroes(int[][] matrix) {
    int rows = matrix.length, cols = matrix[0].length;
    boolean firstRow = false, firstCol = false;
    for (int i = 0; i < rows; i++) for (int j = 0; j < cols; j++)
        if (matrix[i][j] == 0) {
            if (i == 0) firstRow = true; if (j == 0) firstCol = true;
            matrix[i][0] = 0; matrix[0][j] = 0;
        }
    for (int i = 1; i < rows; i++) for (int j = 1; j < cols; j++)
        if (matrix[i][0] == 0 || matrix[0][j] == 0) matrix[i][j] = 0;
    if (firstRow) for (int j = 0; j < cols; j++) matrix[0][j] = 0;
    if (firstCol) for (int i = 0; i < rows; i++) matrix[i][0] = 0;
}""",
        "plan": {
            "target_class": "Solution",
            "ast_mutations": [
                {
                    "action": "ADD_METHOD",
                    "target": "markZeroes",
                    "details": {
                        "modifiers": ["private"],
                        "type": "void",
                        "parameters": [{"type": "int[][]", "name": "matrix"}],
                        "logic_changes": ["Extract zero-marking logic"],
                        "body_abstract": "Find zeros, mark first row and first column"
                    }
                },
                {
                    "action": "MODIFY_METHOD",
                    "target": "setZeroes",
                    "details": {
                        "modifiers": ["public"],
                        "type": "void",
                        "parameters": [{"type": "int[][]", "name": "matrix"}],
                        "logic_changes": ["Call markZeroes then apply row/col zeroing"],
                        "body_abstract": "Call markZeroes(matrix), then set rows/cols to zero"
                    }
                }
            ]
        },
    },

    # ---- FLATTEN_CONDITIONAL (2) ----
    {
        "name": "gen_flatten_orderprocessor",
        "intent": "FLATTEN_CONDITIONAL",
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
            "ast_mutations": [
                {
                    "action": "MODIFY_METHOD",
                    "target": "processOrder",
                    "details": {
                        "modifiers": ["public"],
                        "type": "void",
                        "parameters": [{"type": "Order", "name": "order"}, {"type": "User", "name": "user"}],
                        "logic_changes": ["Replace nested ifs with guard clauses using early exceptions"],
                        "body_abstract": "Invert all conditionals. Each original exception becomes a guard clause at the top with immediate throw."
                    }
                }
            ]
        },
    },
    {
        "name": "gen_flatten_simple_ifs",
        "intent": "FLATTEN_CONDITIONAL",
        "code": """void process(Object x, Object y) {
    if (x != null) {
        if (y != null) {
            doWork(x, y);
        } else {
            throw new IllegalArgumentException("y is null");
        }
    } else {
        throw new IllegalArgumentException("x is null");
    }
}""",
        "plan": {
            "target_class": "Processor",
            "ast_mutations": [
                {
                    "action": "MODIFY_METHOD",
                    "target": "process",
                    "details": {
                        "modifiers": [],
                        "type": "void",
                        "parameters": [{"type": "Object", "name": "x"}, {"type": "Object", "name": "y"}],
                        "logic_changes": ["Flatten nested ifs to guard clauses"],
                        "body_abstract": "Check x==null throw, check y==null throw, then doWork"
                    }
                }
            ]
        },
    },

    # ---- RENAME_SYMBOL (2) ----
    {
        "name": "gen_rename_field",
        "intent": "RENAME_SYMBOL",
        "code": """public class UserManager {
    private String n;
    public String getN() { return n; }
    public void setN(String n) { this.n = n; }
}""",
        "plan": {
            "target_class": "UserManager",
            "ast_mutations": [
                {
                    "action": "RENAME_SYMBOL",
                    "target": "n",
                    "details": {
                        "modifiers": [],
                        "type": "String",
                        "parameters": [],
                        "logic_changes": ["Rename field n to username"],
                        "body_abstract": "Update field, getter, and setter to use username"
                    }
                }
            ]
        },
    },
    {
        "name": "gen_rename_variables",
        "intent": "RENAME_SYMBOL",
        "code": """class ListNode { int val; ListNode next; ListNode(int x) { val = x; } }
public ListNode removeNthFromEnd(ListNode head, int n) {
    ListNode first = head; ListNode second = head;
    for (int i = 0; i < n; i++) first = first.next;
    if (first == null) { head = head.next; return head; }
    while (first.next != null) { first = first.next; second = second.next; }
    second.next = second.next.next;
    return head;
}""",
        "plan": {
            "target_class": "Solution",
            "ast_mutations": [
                {
                    "action": "RENAME_SYMBOL",
                    "target": "first",
                    "details": {
                        "modifiers": [],
                        "type": "",
                        "parameters": [],
                        "logic_changes": ["Rename first to fast"],
                        "body_abstract": ""
                    }
                },
                {
                    "action": "RENAME_SYMBOL",
                    "target": "second",
                    "details": {
                        "modifiers": [],
                        "type": "",
                        "parameters": [],
                        "logic_changes": ["Rename second to slow"],
                        "body_abstract": ""
                    }
                }
            ]
        },
    },

    # ---- ADD_CONSTANT (2) ----
    {
        "name": "gen_extract_pi_constant",
        "intent": "ADD_CONSTANT",
        "code": """public class Circle {
    public double calculateArea(double radius) {
        return 3.14159 * radius * radius;
    }
    public double calculateCircumference(double radius) {
        return 2 * 3.14159 * radius;
    }
}""",
        "plan": {
            "target_class": "Circle",
            "ast_mutations": [
                {
                    "action": "ADD_CONSTANT",
                    "target": "PI",
                    "details": {
                        "modifiers": ["private", "static", "final"],
                        "type": "double",
                        "parameters": [],
                        "logic_changes": [],
                        "body_abstract": ""
                    }
                },
                {
                    "action": "MODIFY_METHOD",
                    "target": "calculateArea",
                    "details": {
                        "modifiers": ["public"],
                        "type": "double",
                        "parameters": [{"type": "double", "name": "radius"}],
                        "logic_changes": ["Replace 3.14159 with PI"],
                        "body_abstract": ""
                    }
                },
                {
                    "action": "MODIFY_METHOD",
                    "target": "calculateCircumference",
                    "details": {
                        "modifiers": ["public"],
                        "type": "double",
                        "parameters": [{"type": "double", "name": "radius"}],
                        "logic_changes": ["Replace 3.14159 with PI"],
                        "body_abstract": ""
                    }
                }
            ]
        },
    },
    {
        "name": "gen_extract_mod_constant",
        "intent": "ADD_CONSTANT",
        "code": """class Solution {
    public int compute(int n) {
        int result = 1;
        for (int i = 1; i <= n; i++) {
            result = result * i % 1000000007;
        }
        return result;
    }
}""",
        "plan": {
            "target_class": "Solution",
            "ast_mutations": [
                {
                    "action": "ADD_CONSTANT",
                    "target": "MOD",
                    "details": {
                        "modifiers": ["private", "static", "final"],
                        "type": "int",
                        "parameters": [],
                        "logic_changes": [],
                        "body_abstract": ""
                    }
                },
                {
                    "action": "MODIFY_METHOD",
                    "target": "compute",
                    "details": {
                        "modifiers": ["public"],
                        "type": "int",
                        "parameters": [{"type": "int", "name": "n"}],
                        "logic_changes": ["Replace 1000000007 with MOD constant"],
                        "body_abstract": ""
                    }
                }
            ]
        },
    },

    # ---- DECOMPOSE_CONDITIONAL (1) ----
    {
        "name": "gen_decompose_simple",
        "intent": "DECOMPOSE_CONDITIONAL",
        "code": """public boolean isEligible(int age, double income, int score) {
    if (age >= 18 && age <= 65 && income > 30000 && score > 650) {
        return true;
    }
    return false;
}""",
        "plan": {
            "target_class": "Checker",
            "ast_mutations": [
                {
                    "action": "MODIFY_METHOD",
                    "target": "isEligible",
                    "details": {
                        "modifiers": ["public"],
                        "type": "boolean",
                        "parameters": [{"type": "int", "name": "age"}, {"type": "double", "name": "income"}, {"type": "int", "name": "score"}],
                        "logic_changes": ["Decompose compound condition into named booleans"],
                        "body_abstract": "Create boolean variables for each condition, combine with &&, return result"
                    }
                }
            ]
        },
    },

    # ---- SPLIT_LOOP (1) ----
    {
        "name": "gen_split_simple_loop",
        "intent": "SPLIT_LOOP",
        "code": """void process(int[] arr) {
    for (int i = 0; i < arr.length; i++) {
        arr[i] = arr[i] * 2;
    }
    for (int i = 0; i < arr.length; i++) {
        System.out.println(arr[i]);
    }
}""",
        "plan": {
            "target_class": "Processor",
            "ast_mutations": [
                {
                    "action": "MODIFY_METHOD",
                    "target": "process",
                    "details": {
                        "modifiers": [],
                        "type": "void",
                        "parameters": [{"type": "int[]", "name": "arr"}],
                        "logic_changes": [],
                        "body_abstract": ""
                    }
                }
            ]
        },
    },

    # ---- Bad-plan stress tests (3) ----
    {
        "name": "bad_missing_target",
        "intent": "STRESS",
        "bad_plan": True,
        "code": """public class Calculator {
    public double calculateTotal(double price, int quantity, double taxRate) {
        return price * quantity * (1 + taxRate);
    }
}""",
        "plan": {
            "target_class": "Calculator",
            "ast_mutations": [
                {
                    "action": "MODIFY_METHOD",
                    "target": "nonExistentMethod",
                    "details": {
                        "modifiers": ["public"],
                        "type": "void",
                        "parameters": [],
                        "logic_changes": ["Change nothing"],
                        "body_abstract": ""
                    }
                }
            ]
        },
    },
    {
        "name": "bad_empty_mutations",
        "intent": "STRESS",
        "bad_plan": True,
        "code": """public class A {
    void m() { int x = 1; }
}""",
        "plan": {
            "target_class": "A",
            "ast_mutations": []
        },
    },
    {
        "name": "bad_hallucinated_add",
        "intent": "STRESS",
        "bad_plan": True,
        "code": """public class A {
    void m() { int x = 1; }
}""",
        "plan": {
            "target_class": "A",
            "ast_mutations": [
                {
                    "action": "ADD_METHOD",
                    "target": "xyZzZzZzHelperMethod",
                    "details": {
                        "modifiers": ["private"],
                        "type": "void",
                        "parameters": [],
                        "logic_changes": ["Do something"],
                        "body_abstract": ""
                    }
                }
            ]
        },
    },
]


def check_planned_elements(
    output_ast, plan: Dict, code_ids: set
) -> Dict[str, Any]:
    mutations = plan.get("ast_mutations", [])
    present = 0
    total = 0
    details = []

    for m in mutations:
        action = m.get("action", "")
        target = m.get("target", "").split("(")[0].strip()
        if action in ("ADD_METHOD", "ADD_FIELD", "ADD_CONSTANT"):
            total += 1
            if action == "ADD_METHOD":
                methods = ASTWalker.find_nodes(output_ast, javalang.tree.MethodDeclaration)
                exists = any(getattr(md, "name", "") == target for md in methods)
            elif action == "ADD_FIELD":
                fields = ASTWalker.find_nodes(output_ast, javalang.tree.FieldDeclaration)
                exists = any(
                    getattr(d, "name", "") == target
                    for f in fields
                    for d in (f.declarators if hasattr(f, "declarators") else [])
                )
            elif action == "ADD_CONSTANT":
                fields = ASTWalker.find_nodes(output_ast, javalang.tree.FieldDeclaration)
                exists = any(
                    getattr(d, "name", "") == target
                    for f in fields
                    for d in (f.declarators if hasattr(f, "declarators") else [])
                )
            else:
                exists = False

            if exists:
                present += 1
                details.append(f"{action}({target}) — present ✓")
            else:
                details.append(f"{action}({target}) — missing ✗")

        elif action in ("MODIFY_METHOD", "REMOVE_METHOD"):
            total += 1
            if action == "MODIFY_METHOD":
                methods = ASTWalker.find_nodes(output_ast, javalang.tree.MethodDeclaration)
                exists = any(getattr(md, "name", "") == target for md in methods)
            elif action == "REMOVE_METHOD":
                methods = ASTWalker.find_nodes(output_ast, javalang.tree.MethodDeclaration)
                exists = not any(getattr(md, "name", "") == target for md in methods)
            else:
                exists = True

            if exists:
                present += 1
                details.append(f"{action}({target}) — ok ✓")
            else:
                details.append(f"{action}({target}) — not found ✗")

        elif action == "RENAME_SYMBOL":
            total += 1
            methods = ASTWalker.find_nodes(output_ast, javalang.tree.MethodDeclaration)
            fields_in_output = []
            for fdecl in ASTWalker.find_nodes(output_ast, javalang.tree.FieldDeclaration):
                for d in (fdecl.declarators if hasattr(fdecl, "declarators") else []):
                    fields_in_output.append(getattr(d, "name", ""))
            method_names = [getattr(md, "name", "") for md in methods]
            old_exists = target in method_names or target in fields_in_output
            exists = not old_exists
            if exists:
                present += 1
                details.append(f"RENAME_SYMBOL({target}) — old name absent ✓")
            else:
                details.append(f"RENAME_SYMBOL({target}) — old name still present ✗")

    return {"present": present, "total": total, "details": details}


def detect_anti_patterns(original_code: str, output_code: str, intent: str = "") -> List[str]:
    violations = []

    if output_code.strip() == original_code.strip():
        violations.append("Returned original code unchanged")
        return violations

    orig_throws = re.findall(r"throw\s+new\s+(\w+)", original_code)
    refac_throws = re.findall(r"throw\s+new\s+(\w+)", output_code)
    if set(orig_throws) != set(refac_throws):
        missing = set(orig_throws) - set(refac_throws)
        added = set(refac_throws) - set(orig_throws)
        if missing or added:
            violations.append(f"Exception types changed: missing={missing}, added={added}")

    # For FLATTEN_CONDITIONAL: check throw messages instead of if-count
    # Fewer ifs is expected behavior — but merged throws are not
    if intent == "FLATTEN_CONDITIONAL":
        orig_throw_msgs = re.findall(r'throw\s+new\s+\w+\(([^)]+)\)', original_code)
        refac_throw_msgs = re.findall(r'throw\s+new\s+\w+\(([^)]+)\)', output_code)
        # Check if throw messages were merged (fewer distinct messages)
        if len(refac_throw_msgs) < len(orig_throw_msgs) and len(orig_throw_msgs) >= 2:
            violations.append("May have merged guard clause exception messages")
        # Check if any original throw message was lost
        orig_msgs_clean = {msg.strip().strip('"').strip("'") for msg in orig_throw_msgs}
        refac_msgs_clean = {msg.strip().strip('"').strip("'") for msg in refac_throw_msgs}
        lost = orig_msgs_clean - refac_msgs_clean
        if lost:
            violations.append(f"Original exception messages lost: {lost}")
    else:
        # Original check for non-FLATTEN intents
        orig_ifs = len(re.findall(r"if\s*\(", original_code))
        refac_ifs = len(re.findall(r"if\s*\(", output_code))
        if orig_ifs > 0 and refac_ifs > 0 and refac_ifs < orig_ifs:
            orig_throws_count = len(orig_throws) if orig_throws else 0
            refac_throws_count = len(refac_throws) if refac_throws else 0
            if refac_throws_count < orig_throws_count and orig_throws_count >= 2:
                violations.append("May have merged guard clauses")

    return violations


def _diagnose_gen_what(result: Dict, case: Dict) -> str:
    lines = []
    if not result["syntax_valid"]:
        lines.append("Generated code failed Java syntax validation. ")
    if result["planned_present"] < result["planned_total"]:
        lines.append(
            f"Only {result['planned_present']}/{result['planned_total']} planned elements present. "
        )
    if result["anti_patterns"]:
        lines.append(f"Anti-pattern violations: {result['anti_patterns']}. ")
    if result["verdict"] == "PASS":
        lines.append(
            "All planned elements created, syntax valid, no anti-pattern violations. "
        )
    return "".join(lines) if lines else "All checks passed."


def _diagnose_gen_why(result: Dict, case: Dict) -> str:
    lines = []
    mutation_count = result.get("mutation_count", 0)

    if case.get("bad_plan"):
        name = case["name"]
        if "missing_target" in name:
            lines.append(
                "MODIFY_METHOD target doesn't exist in code. Generator treated it as valid instruction — plan is trusted blindly. "
            )
        elif "empty_mutations" in name:
            lines.append(
                "Empty mutations list. Generator had nothing to change — returned original code (correct behavior). "
            )
        else:
            lines.append(
                "Hallucinated ADD_METHOD name. Generator created the method — treats all plan entries as authoritative. "
            )
        return "".join(lines)

    if mutation_count > 4:
        lines.append(
            f"Plan has {mutation_count} mutations — the 3B model may lose track of later mutations after executing early ones. "
        )
    if result.get("intent") == "DECOMPOSE_CONDITIONAL":
        lines.append(
            "DECOMPOSE is the hardest intent — requires creating multiple named booleans and restructuring conditions. 3B model capability limit. "
        )
    if "exception" in str(result.get("plan_summary", "")).lower():
        lines.append(
            "Plan includes exception handling logic. The coder anti-pattern list has 8 rules — by the time the model reaches the guard clause rule, it may have already violated it. "
        )
    if not lines:
        lines.append(
            "Simple plan within model's reliable range. "
        )
    return "".join(lines)


async def run_generator_case(
    harness: ModelTestHarness, case: Dict[str, Any]
) -> Dict[str, Any]:
    code = case["code"]
    plan = case["plan"]

    user_prompt = (
        f"Modification Plan: {json.dumps(plan)}\n"
        f"Base Code: <code>{code}</code>"
    )

    result = await harness.generate(
        system_prompt=harness.prompts["generator"]["coder"],
        user_prompt=user_prompt,
        temp=0.1,
        max_tokens=2048,
    )

    output_code = ""
    if result["success"]:
        extracted = ResponseParser.extract_xml(result["content"], "code")
        if extracted:
            output_code = extracted
        else:
            output_code = result["content"]

    r: Dict[str, Any] = {
        "name": case["name"],
        "intent": case.get("intent", "STRESS"),
        "bad_plan": case.get("bad_plan", False),
        "code_len": len(code),
        "mutation_count": len(plan.get("ast_mutations", [])),
        "plan_summary": ", ".join(
            m.get("action", "?") for m in plan.get("ast_mutations", [])
        ),
        "output_code": output_code,
        "duration": result["duration"],
        "verdict": "FAIL",
    }

    syntax_res = harness.validator.check_syntax(output_code)
    r["syntax_valid"] = syntax_res["is_valid"]

    if syntax_res["is_valid"] and syntax_res.get("ast"):
        ast = syntax_res["ast"]
        code_ids = harness.find_ast_identifiers(code)
        planned = check_planned_elements(ast, plan, code_ids)
        r["planned_present"] = planned["present"]
        r["planned_total"] = planned["total"]
        r["planned_details"] = planned["details"]

        if not case.get("bad_plan"):
            r["anti_patterns"] = detect_anti_patterns(code, output_code, case.get("intent", ""))
            r["anti_pattern_count"] = len(r["anti_patterns"])
            r["compliance_pass"] = planned["present"] == planned["total"]
        else:
            r["anti_patterns"] = []
            r["anti_pattern_count"] = 0
            r["compliance_pass"] = True
            r["graceful"] = r["syntax_valid"] and len(output_code) > 20
    else:
        r["planned_present"] = 0
        r["planned_total"] = len(plan.get("ast_mutations", []))
        r["planned_details"] = ["Syntax invalid — cannot check plans"]
        r["anti_patterns"] = []
        r["anti_pattern_count"] = 0
        r["compliance_pass"] = False
        r["graceful"] = False

    is_pass = (
        r["syntax_valid"]
        and r["compliance_pass"]
        and r["anti_pattern_count"] == 0
    )
    r["verdict"] = "PASS" if is_pass else "FAIL"

    r["what_happened"] = _diagnose_gen_what(r, case)
    r["why"] = _diagnose_gen_why(r, case)
    r["plan"] = plan

    return r


async def main():
    print("=" * 60)
    print("GENERATOR ISOLATED TEST")
    print(f"Cases: {len(TEST_CASES)} ({sum(1 for c in TEST_CASES if not c.get('bad_plan'))} real + {sum(1 for c in TEST_CASES if c.get('bad_plan'))} stress)")
    print("=" * 60)

    harness = ModelTestHarness("generator")
    print("Loading generator model...")
    await harness.load_model()

    results = []
    for i, case in enumerate(TEST_CASES):
        tag = "[STRESS]" if case.get("bad_plan") else "[REAL]"
        print(f"\n[{i+1}/{len(TEST_CASES)}] {tag} {case['name']}")
        print(f"  Code: {len(case['code'])} chars | Mutations: {len(case.get('plan', {}).get('ast_mutations', []))}")
        try:
            await harness.clear_context()
            r = await run_generator_case(harness, case)
            results.append(r)
            print(f"  -> {r['verdict']} | syntax={'OK' if r['syntax_valid'] else 'FAIL'} | plan={r['planned_present']}/{r['planned_total']} | anti={r['anti_pattern_count']} | {r['duration']}s")
        except Exception as e:
            print(f"  -> ERROR: {e}")
            results.append({"name": case["name"], "verdict": "ERROR", "error": str(e)})

    await harness.unload_model()

    json_path = harness.save_results(results, "generator")
    report = harness.build_generator_report(results)
    report_path = "tests/results/generator_isolated_report.md"
    with open(report_path, "w") as f:
        f.write(report)

    real = [r for r in results if not r.get("bad_plan")]
    passed = sum(1 for r in real if r.get("verdict") == "PASS")
    print(f"\nDONE. Real cases: {passed}/{len(real)} PASS")
    print(f"JSON: {json_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
