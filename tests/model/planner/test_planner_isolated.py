import asyncio
import json
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

import javalang

from app.utils.types import RefactorIntent
from tests.model.harness import ModelTestHarness


TEST_CASES: List[Dict[str, Any]] = [
    # ---- FLATTEN_CONDITIONAL (3 cases) ----
    {
        "name": "flat_demo_orderprocessor",
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
        "instruction": "Refactor processOrder to use guard clauses. Invert nested if-statements to handle invalid states at the top with immediate exceptions. Preserve every original exception type and error message exactly.",
        "expected_intent": "FLATTEN_CONDITIONAL",
    },
    {
        "name": "flat_binary_search",
        "code": """public boolean search(int[] nums, int target) {
    int left = 0, right = nums.length - 1;
    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (nums[mid] == target) return true;
        if (nums[mid] == nums[left]) { left++; }
        else if (nums[mid] > nums[left]) {
            if (nums[left] <= target && target < nums[mid]) { right = mid - 1; }
            else { left = mid + 1; }
        } else {
            if (nums[mid] < target && target <= nums[right]) { left = mid + 1; }
            else { right = mid - 1; }
        }
    }
    return false;
}""",
        "instruction": "Flatten the nested if-else branches in the binary search. Use early return for the match case and guard clauses for remaining checks.",
        "expected_intent": "FLATTEN_CONDITIONAL",
    },
    {
        "name": "flat_validate_ip",
        "code": """public String validateIP(String queryIP) {
    String[] ipv4Parts = queryIP.split("\\\\.", -1);
    String[] ipv6Parts = queryIP.split(":", -1);
    if (ipv4Parts.length == 4) {
        if (isValidIPv4(ipv4Parts)) return "IPv4";
    } else if (ipv6Parts.length == 8) {
        if (isValidIPv6(ipv6Parts)) return "IPv6";
    }
    return "Neither";
}""",
        "instruction": "Flatten the nested if-else in validateIP. Use early returns for each validation case instead of nested branches.",
        "expected_intent": "FLATTEN_CONDITIONAL",
    },

    # ---- EXTRACT_METHOD (3 cases) ----
    {
        "name": "extract_set_zeroes",
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
        "instruction": "Extract three private methods from setZeroes: markZeroMarkers for the first loop, setInnerZeros for the second loop, and setFirstRowColZeros for the final checks.",
        "expected_intent": "EXTRACT_METHOD",
    },
    {
        "name": "extract_tax_calculator",
        "code": """public class Calculator {
    public double calculateTotal(double price, int quantity, double taxRate) {
        double subtotal = price * quantity;
        double tax = subtotal * taxRate;
        double total = subtotal + tax;
        double rounded = Math.round(total * 100.0) / 100.0;
        return rounded;
    }
}""",
        "instruction": "Extract the tax calculation logic (tax computation and rounding) into a separate private method called computeTaxWithRounding.",
        "expected_intent": "EXTRACT_METHOD",
    },
    {
        "name": "extract_prime_arrange",
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
        "instruction": "Extract the Sieve of Eratosthenes logic into a separate method called countPrimes that returns the count of primes up to n.",
        "expected_intent": "EXTRACT_METHOD",
    },

    # ---- RENAME_SYMBOL (2 cases) ----
    {
        "name": "rename_user_manager",
        "code": """public class UserManager {
    private String n;
    public String getN() { return n; }
    public void setN(String n) { this.n = n; }
}""",
        "instruction": "Rename the field 'n' to 'username' and update all references.",
        "expected_intent": "RENAME_SYMBOL",
    },
    {
        "name": "rename_remove_nth",
        "code": """class ListNode { int val; ListNode next; ListNode(int x) { val = x; } }
public ListNode removeNthFromEnd(ListNode head, int n) {
    ListNode first = head; ListNode second = head;
    for (int i = 0; i < n; i++) first = first.next;
    if (first == null) { head = head.next; return head; }
    while (first.next != null) { first = first.next; second = second.next; }
    second.next = second.next.next;
    return head;
}""",
        "instruction": "Rename 'first' to 'fast', rename 'second' to 'slow' in removeNthFromEnd. Update all references.",
        "expected_intent": "RENAME_SYMBOL",
    },

    # ---- EXTRACT_CONSTANT (2 cases) ----
    {
        "name": "const_abbreviation",
        "code": """public boolean validWordAbbreviation(String word, String abbr) {
    int i = 0, j = 0;
    while (i < word.length() && j < abbr.length()) {
        if (Character.isDigit(abbr.charAt(j))) {
            if (abbr.charAt(j) == '0') return false;
            int num = 0;
            while (j < abbr.length() && Character.isDigit(abbr.charAt(j)))
                num = num * 10 + (abbr.charAt(j++) - '0');
            i += num;
        } else {
            if (word.charAt(i++) != abbr.charAt(j++)) return false;
        }
    }
    return i == word.length() && j == abbr.length();
}""",
        "instruction": "Extract the magic number '0' used in character-to-digit conversion into constants DIGIT_BASE and LEADING_ZERO_CHAR.",
        "expected_intent": "EXTRACT_CONSTANT",
    },
    {
        "name": "const_circle_pi",
        "code": """public class Circle {
    public double calculateArea(double radius) {
        return 3.14159 * radius * radius;
    }
    public double calculateCircumference(double radius) {
        return 2 * 3.14159 * radius;
    }
}""",
        "instruction": "Extract the magic number 3.14159 into a named constant PI.",
        "expected_intent": "EXTRACT_CONSTANT",
    },

    # ---- DECOMPOSE_CONDITIONAL (2 cases) ----
    {
        "name": "decomp_closed_island",
        "code": """int[] dx = {-1, 1, 0, 0}; int[] dy = {0, 0, -1, 1};
void dfs(int[][] grid, int x, int y) {
    int n = grid.length, m = grid[0].length;
    grid[x][y] = 1;
    for (int i = 0; i < 4; i++) {
        int nx = x + dx[i], ny = y + dy[i];
        if (nx >= 0 && nx < n && ny >= 0 && ny < m && grid[nx][ny] == 0) {
            dfs(grid, nx, ny);
        }
    }
}
public int closedIsland(int[][] grid) {
    int n = grid.length, m = grid[0].length;
    for (int i = 0; i < n; i++) for (int j = 0; j < m; j++)
        if ((i == 0 || i == n - 1 || j == 0 || j == m - 1) && grid[i][j] == 0)
            dfs(grid, i, j);
    int res = 0;
    for (int i = 1; i < n - 1; i++) for (int j = 1; j < m - 1; j++)
        if (grid[i][j] == 0) { dfs(grid, i, j); res++; }
    return res;
}""",
        "instruction": "Decompose the complex DFS boundary condition into well-named booleans: isInBounds, isOnBorder, and isUnvisited.",
        "expected_intent": "DECOMPOSE_CONDITIONAL",
    },
    {
        "name": "decomp_regex_dp",
        "code": """public boolean isMatch(String s, String p) {
    int m = s.length(), n = p.length();
    boolean[][] dp = new boolean[m + 1][n + 1];
    dp[0][0] = true;
    for (int j = 1; j <= n; j++)
        if (p.charAt(j - 1) == '*' && dp[0][j - 2]) dp[0][j] = true;
    for (int i = 1; i <= m; i++) for (int j = 1; j <= n; j++)
        if (p.charAt(j - 1) == s.charAt(i - 1) || p.charAt(j - 1) == '.')
            dp[i][j] = dp[i - 1][j - 1];
        else if (p.charAt(j - 1) == '*')
            dp[i][j] = dp[i][j - 2] || (dp[i - 1][j] && (s.charAt(i - 1) == p.charAt(j - 2) || p.charAt(j - 2) == '.'));
    return dp[m][n];
}""",
        "instruction": "Decompose the complex DP transition for the '*' character into a named boolean like matchesZeroOrMore.",
        "expected_intent": "DECOMPOSE_CONDITIONAL",
    },

    # ---- SPLIT_LOOP (2 cases) ----
    {
        "name": "split_board_path",
        "code": """public String alphabetBoardPath(String target) {
    int x = 0, y = 0; StringBuilder sb = new StringBuilder();
    for (char c : target.toCharArray()) {
        int dx = (c - 'a') / 5, dy = (c - 'a') % 5;
        while (x > dx) { sb.append('U'); x--; }
        while (y > dy) { sb.append('L'); y--; }
        while (x < dx) { sb.append('D'); x++; }
        while (y < dy) { sb.append('R'); y++; }
        sb.append('!');
    }
    return sb.toString();
}""",
        "instruction": "Split the per-character loop into two separate methods: one for vertical movement (U/D) and one for horizontal movement (L/R).",
        "expected_intent": "SPLIT_LOOP",
    },
    {
        "name": "split_unique_paths",
        "code": """public int uniquePathsWithObstacles(int[][] grid) {
    int m = grid.length, n = grid[0].length;
    if (grid[0][0] == 1) return 0;
    grid[0][0] = 1;
    for (int i = 1; i < m; ++i)
        grid[i][0] = (grid[i][0] == 0 && grid[i - 1][0] == 1) ? 1 : 0;
    for (int i = 1; i < n; ++i)
        grid[0][i] = (grid[0][i] == 0 && grid[0][i - 1] == 1) ? 1 : 0;
    for (int i = 1; i < m; ++i) for (int j = 1; j < n; ++j)
        if (grid[i][j] == 0) grid[i][j] = grid[i - 1][j] + grid[i][j - 1];
        else grid[i][j] = 0;
    return grid[m - 1][n - 1];
}""",
        "instruction": "Split the DP initialization into separate methods: initFirstColumn and initFirstRow.",
        "expected_intent": "SPLIT_LOOP",
    },

    # ---- CONSOLIDATE_CONDITIONAL (1 case) ----
    {
        "name": "cons_word_pattern",
        "code": """public boolean wordPatternMatch(String pattern, String s) {
    return backtrack(pattern, 0, s, 0);
}
boolean backtrack(String p, int pi, String s, int si) {
    if (pi == p.length() && si == s.length()) return true;
    if (pi == p.length() || si == s.length()) return false;
    return false;
}""",
        "instruction": "Consolidate the two base-case checks at the top of backtrack into a single if-else: return true if both exhausted, false if only one exhausted.",
        "expected_intent": "CONSOLIDATE_CONDITIONAL",
    },
]


async def run_planner_step(
    harness: ModelTestHarness,
    step_name: str,
    system_key: str,
    user_prompt: str,
    max_tokens: int,
    response_model=None,
) -> Dict[str, Any]:
    print(f"    [{step_name}] Calling model...")
    sys_prompt = harness.prompts["planner"][system_key]
    result = await harness.generate(
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        temp=0.1,
        max_tokens=max_tokens,
        response_model=response_model,
    )
    return result


async def run_planner_case(
    harness: ModelTestHarness, case: Dict[str, Any]
) -> Dict[str, Any]:
    from app.utils.response_parser import ResponseParser
    from app.utils.schemas import IntentClassifierResponse, ASTArchitectResponse, ArchitectAnalysisResponse

    code = case["code"]
    instruction = case["instruction"]
    name = case["name"]
    expected = case["expected_intent"]

    result = {
        "name": name,
        "code_len": len(code),
        "instruction_short": instruction[:80],
        "expected_intent": expected,
        "verdict": "FAIL",
    }

    # Step 1: Classifier
    class_user = f"<code>{code}</code>\n<instruction>{instruction}</instruction>"
    class_res = await run_planner_step(
        harness, "Classifier", "classifier", class_user, 500,
        response_model=IntentClassifierResponse,
    )

    intent_packet = {}
    classifier_valid = False
    if class_res["success"]:
        try:
            parsed = ResponseParser.extract_json(
                class_res["content"], IntentClassifierResponse
            )
            intent_packet = parsed.intent_packet.model_dump()
            classifier_valid = True
        except Exception:
            pass

    result["classifier_raw"] = class_res["content"]
    result["classifier_duration"] = class_res["duration"]
    result["actual_intent"] = intent_packet.get("specific_intent", "PARSE_ERROR")
    result["intent_correct"] = result["actual_intent"] == expected

    scope_anchor = intent_packet.get("scope_anchor", {})
    target_class = scope_anchor.get("target_class", scope_anchor.get("class", ""))
    target_member = scope_anchor.get("member", "")
    unit_type = scope_anchor.get("unit_type", "")

    scope_check = harness.check_scope_anchor_exists(code, target_class, target_member)
    has_classes = len(__import__("javalang").tree.ClassDeclaration.__name__) > 0 and any(
        True for _ in harness.check_scope_anchor_exists(code, target_class, target_member).items()
    )
    scope_check_full = harness.check_scope_anchor_exists(code, target_class, target_member)
    classes_in_code = False
    syntax_r = harness.validator.check_syntax(code)
    if syntax_r["is_valid"]:
        # Use validator's unit detection instead of counting ClassDeclarations in wrapped AST
        unit = syntax_r.get("unit")
        if unit is not None:
            from app.utils.types import StructureUnit
            classes_in_code = unit == StructureUnit.CLASS_UNIT
        elif syntax_r.get("ast"):
            c_nodes = ASTWalker.find_nodes(syntax_r["ast"], javalang.tree.ClassDeclaration)
            classes_in_code = len(c_nodes) > 0

    result["scope_valid"] = (
        scope_check["valid"]
        and (not target_member or scope_check["member_exists"])
        and (scope_check["class_exists"] or not classes_in_code)
    )
    class_ok = scope_check["class_exists"]
    member_ok = scope_check["member_exists"]
    scope_mark = "✓" if result["scope_valid"] else f"✗ (class={class_ok}, member={member_ok}, hasClasses={classes_in_code})"
    result["scope_detail"] = f"{target_class}.{target_member}, {unit_type} {scope_mark}"

    code_ids = harness.find_ast_identifiers(code)

    # Step 2: Analysis
    await harness.clear_context()
    analysis_user = (
        f"Intent Packet: {json.dumps(intent_packet)}\n"
        f"User Instruction: {instruction}\n"
        f"Code: <code>{code}</code>"
    )
    analysis_res = await run_planner_step(
        harness, "Analysis", "architect_analysis", analysis_user, 1024,
        response_model=ArchitectAnalysisResponse,
    )

    analysis_data = {}
    if analysis_res["success"]:
        try:
            parsed = ResponseParser.extract_json(
                analysis_res["content"], ArchitectAnalysisResponse
            )
            analysis_data = parsed.model_dump()
        except Exception:
            pass

    result["analysis_raw"] = analysis_res["content"]
    result["analysis_duration"] = analysis_res["duration"]

    primary = analysis_data.get("primary_targets", [])
    secondary = analysis_data.get("secondary_targets", [])
    must_preserve = analysis_data.get("must_preserve", [])
    new_structures = analysis_data.get("new_structures_needed", [])

    all_targets = primary + secondary
    targets_exist = all(
        t in code_ids or any(t in s for s in code_ids)
        for t in all_targets
    )

    result["targets"] = str(primary) if primary else "[]"
    result["must_preserve"] = str(must_preserve) if must_preserve else "[]"
    result["analysis_complete"] = len(primary) > 0

    analysis_hallucinations = harness.detect_hallucinations(analysis_data, code_ids)

    # Step 3: Synthesis
    await harness.clear_context()
    synth_user = (
        f"Analysis: {json.dumps(analysis_data)}\n"
        f"Intent: {json.dumps(intent_packet)}\n"
        f"Instruction: {instruction}\n"
        f"Code: <code>{code}</code>"
    )
    synth_res = await run_planner_step(
        harness, "Synthesis", "architect", synth_user, 2048,
        response_model=ASTArchitectResponse,
    )

    plan_data = {}
    if synth_res["success"]:
        try:
            parsed = ResponseParser.extract_json(
                synth_res["content"], ASTArchitectResponse
            )
            plan_data = parsed.ast_modification_plan.model_dump()
        except Exception:
            pass

    result["synthesis_raw"] = synth_res["content"]
    result["synthesis_duration"] = synth_res["duration"]

    mutations = plan_data.get("ast_mutations", [])
    result["mutation_count"] = len(mutations)

    mutation_targets = set()
    add_targets = set()
    for m in mutations:
        target = m.get("target", "")
        action = m.get("action", "")
        name = target.split("(")[0].strip()
        if name:
            mutation_targets.add(name)
            if action in ("ADD_METHOD", "ADD_FIELD", "ADD_CONSTANT", "ADD_ENUM"):
                add_targets.add(name)

    targets_exist_in_ast = all(
        t in code_ids or t in add_targets for t in mutation_targets
    )
    result["plan_executable"] = len(mutations) > 0 and targets_exist_in_ast

    plan_hallucinations = harness.detect_hallucinations(plan_data, code_ids)
    all_hallucinations = list(set(analysis_hallucinations + plan_hallucinations))
    result["hallucinations"] = all_hallucinations

    plan_refs_analysis = any(
        str(mutation_targets).count(t) > 0 for t in primary
    )
    result["coherent"] = plan_refs_analysis
    result["coherence_detail"] = (
        "aligned ✓" if plan_refs_analysis else "misaligned ✗ — plan does not reference analysis targets"
    )

    result["duration"] = round(
        result["classifier_duration"] + result["analysis_duration"] + result["synthesis_duration"], 1
    )

    is_pass = (
        result["intent_correct"]
        and result["scope_valid"]
        and result["plan_executable"]
        and len(all_hallucinations) == 0
    )
    result["verdict"] = "PASS" if is_pass else "FAIL"

    result["method_count"] = len(
        [m for m in ASTWalker.find_nodes(
            harness.validator.check_syntax(code).get("ast"),
            javalang.tree.MethodDeclaration,
        )] if harness.validator.check_syntax(code)["is_valid"] else []
    )

    result["what_happened"] = _diagnose_planner_what(result, case)
    result["why"] = _diagnose_planner_why(result, case)
    result["raw_output"] = {
        "classifier": result["classifier_raw"],
        "analysis": result["analysis_raw"],
        "synthesis": result["synthesis_raw"],
    }

    return result


def _diagnose_planner_what(result: Dict, case: Dict) -> str:
    lines = []
    if not result["intent_correct"]:
        lines.append(
            f"Classifier returned {result['actual_intent']} but expected {result['expected_intent']}. "
        )
    if not result["scope_valid"]:
        lines.append("Scope anchor references code elements that do not exist in the AST. ")
    if not result["plan_executable"]:
        lines.append(
            f"Plan contains {result['mutation_count']} mutations but targets do not all exist in code. "
        )
    if result["hallucinations"]:
        lines.append(
            f"Invented identifiers in plan/analysis: {result['hallucinations']}. "
        )
    if result["verdict"] == "PASS":
        lines.append(
            "Model correctly classified intent, identified valid targets, and produced executable plan with no hallucinations. "
        )
    return "".join(lines) if lines else "All checks passed. Model output structurally valid."


def _diagnose_planner_why(result: Dict, case: Dict) -> str:
    lines = []
    code_len = result.get("code_len", 0)
    method_count = result.get("method_count", 0)
    intent = result.get("expected_intent", "")

    if code_len > 800:
        lines.append(
            f"Long code ({code_len} chars) may exceed effective attention for 3B model. "
        )
    if method_count == 0 or method_count > 3:
        lines.append(
            f"Code has {method_count} methods — unusual structure may confuse classifier. "
        )
    if intent == "DECOMPOSE_CONDITIONAL":
        lines.append(
            "DECOMPOSE is the hardest intent for 3B models — requires understanding multi-clause conditions and inventing named variables. "
        )
    if intent == "EXTRACT_CONSTANT" and method_count > 1:
        lines.append(
            f"Constant appears in {method_count} methods — model may miss the cross-method dependency. "
        )
    if not result["coherent"]:
        lines.append(
            "Plan does not reference analysis items — model may have ignored the analysis step and generated plan independently. "
        )
    if result["hallucinations"]:
        lines.append(
            "Model likely generated from memory of similar patterns rather than from specific code analysis. "
        )
    if not lines:
        lines.append(
            "Clean single-method code with unambiguous instruction — within the model's reliable operating range. "
        )
    return "".join(lines)


async def main():
    from app.modules.validator import ASTWalker
    global ASTWalker

    print("=" * 60)
    print("PLANNER ISOLATED TEST")
    print(f"Cases: {len(TEST_CASES)}, Calls: {len(TEST_CASES) * 3}")
    print("=" * 60)

    harness = ModelTestHarness("planner")
    print("Loading planner model...")
    await harness.load_model()

    results = []
    for i, case in enumerate(TEST_CASES):
        print(f"\n[{i+1}/{len(TEST_CASES)}] {case['name']}")
        print(f"  Code: {len(case['code'])} chars | Expected: {case['expected_intent']}")
        try:
            r = await run_planner_case(harness, case)
            results.append(r)
            print(f"  -> {r['verdict']} | intent={r['actual_intent']} | {r['duration']}s")
        except Exception as e:
            print(f"  -> ERROR: {e}")
            results.append({
                "name": case["name"],
                "verdict": "ERROR",
                "error": str(e),
            })

    await harness.unload_model()

    print(f"\nSAVING RESULTS...")
    json_path = harness.save_results(results, "planner")

    report = harness.build_planner_report(results)
    report_path = "tests/results/planner_isolated_report.md"
    with open(report_path, "w") as f:
        f.write(report)

    passed = sum(1 for r in results if r.get("verdict") == "PASS")
    print(f"\nDONE. {passed}/{len(results)} PASS")
    print(f"JSON: {json_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
