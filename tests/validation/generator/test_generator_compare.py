"""
Generator ICL comparison — TEXT vs ICL guidance.
Uses 20 correct plans from polish pipeline (cached once).
All guidance hardcoded — no dependency on prompts.yaml.
"""
import asyncio
import json
import re
import sys
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.modules.validator import Validator
from app.utils.formatters import format_plan_for_generator
from app.utils.response_parser import ResponseParser
from app.utils.schemas import (
    ArchitectAnalysisResponse,
    ASTArchitectResponse,
    IntentClassifierResponse,
)
from app.utils.types import RefactorIntent
from tests.model_tests.harness import ModelTestHarness


# ============================================================
# TEST CASES (same 20 from polish pipeline)
# ============================================================

TEST_CASES: List[Dict[str, Any]] = [
    # FLATTEN (2)
    {"name":"polish_flatten_short_mindist","expected_intent":"FLATTEN_CONDITIONAL",
     "code":"public int minDistance(String word1, String word2) { int m = word1.length(), n = word2.length(); int[][] dp = new int[m+1][n+1]; for(int i = 0; i <= m; i++) { for(int j = 0; j <= n; j++) { if(i == 0 || j == 0) dp[i][j] = i + j; else if(word1.charAt(i-1) == word2.charAt(j-1)) dp[i][j] = dp[i-1][j-1]; else dp[i][j] = 1 + Math.min(dp[i-1][j], dp[i][j-1]); } } return dp[m][n]; }",
     "instruction": "Flatten."},
    {"name":"polish_flatten_long_quads","expected_intent":"FLATTEN_CONDITIONAL",
     "code":"public int increasingQuadruplets(int[] nums) { int n = nums.length, count = 0; for(int i = 0; i < n - 3; i++) { for(int j = i + 1; j < n - 2; j++) { for(int k = j + 1; k < n - 1; k++) { if(nums[i] < nums[k] && nums[k] < nums[j]) { for(int l = k + 1; l < n; l++) { if(nums[j] < nums[l]) count++; } } } } } return count; }",
     "instruction": "The four nested for-loops in this method create a pyramid of condition checks that is difficult to follow. Restructure the entire method body to use guard clauses with continue. Each invalid comparison should skip to the next iteration immediately at the top of the loop. Remove all nesting."},
    # DECOMPOSE (2)
    {"name":"polish_decompose_med_nim","expected_intent":"DECOMPOSE_CONDITIONAL",
     "code":"public boolean canWinNim(int n) { return n % 4 != 0; }",
     "instruction": "Decompose this simple boolean expression into a well-named variable that explains what the calculation means in game theory."},
    {"name":"polish_decompose_long_palindrome","expected_intent":"DECOMPOSE_CONDITIONAL",
     "code":"public boolean canPermutePalindrome(String s) { HashMap<Character, Integer> count = new HashMap<>(); for(char c : s.toCharArray()) count.put(c, count.getOrDefault(c, 0) + 1); int odd_count = 0; for(int value : count.values()) { if(value % 2 != 0) odd_count++; } return odd_count <= 1; }",
     "instruction": "The loop body in canPermutePalindrome mixes character counting with implicit type operations. Break the logic apart: decompose the odd-count validation check into a clearly named boolean variable called hasPalindromePermutation that explains what the threshold means for palindrome properties."},
    # CONSOLIDATE (2)
    {"name":"polish_consolidate_short_fixed","expected_intent":"CONSOLIDATE_CONDITIONAL",
     "code":"public int fixedPoint(int[] arr) { int left = 0, right = arr.length - 1; while (left < right) { int middle = left + (right - left) / 2; if (arr[middle] < middle) left = middle + 1; else right = middle; } return arr[left] == left ? left : -1; }",
     "instruction": "Consolidate."},
    {"name":"polish_consolidate_long_lhs","expected_intent":"CONSOLIDATE_CONDITIONAL",
     "code":"public int findLHS(int[] nums) { HashMap<Integer, Integer> count = new HashMap<>(); for (int num : nums) count.put(num, count.getOrDefault(num, 0) + 1); int longest_sequence = 0; for (int key : count.keySet()) { if (count.containsKey(key + 1)) longest_sequence = Math.max(longest_sequence, count.get(key) + count.get(key + 1)); } return longest_sequence; }",
     "instruction": "Look at how the hashmap is populated and then iterated. The two sequential for-loops can be merged into a single pass. Also consolidate the key lookup into a single well-structured condition."},
    # EXTRACT_CONSTANT (2)
    {"name":"polish_const_short_box","expected_intent":"EXTRACT_CONSTANT",
     "code":"public String boxCategory(int length, int width, int height, int mass) { boolean bulky = length >= 10000 || width >= 10000 || height >= 10000 || length * width * height >= 1000000000; boolean heavy = mass >= 100; if (bulky && heavy) return \"Both\"; else if (bulky) return \"Bulky\"; else if (heavy) return \"Heavy\"; else return \"Neither\"; }",
     "instruction": "Extract 10000 into BULKY_DIMENSION_THRESHOLD and 100 into HEAVY_MASS_THRESHOLD."},
    {"name":"polish_const_long_derangement","expected_intent":"EXTRACT_CONSTANT",
     "code":"public int findDerangement(int n) { long[] dp = new long[n + 1]; dp[2] = 1; for (int i = 3; i <= n; i++) dp[i] = (i - 1) * (dp[i - 1] + dp[i - 2]) % 1000000007; return (int) dp[n]; }",
     "instruction": "There are several literal values used in the arithmetic that represent mathematical identities — particularly the modulo value 1000000007 which is used for overflow prevention. Extract this magic number into a named constant called MOD."},
    # EXTRACT_METHOD (2)
    {"name":"polish_extract_short_palindrome","expected_intent":"EXTRACT_METHOD",
     "code":"public class Solution { private boolean isPalindrome(String s, int start, int end) { while (start < end) { if (s.charAt(start) != s.charAt(end)) return false; start++; end--; } return true; } public boolean checkPartitioning(String s) { int n = s.length(); for (int i = 0; i < n - 2; ++i) if (isPalindrome(s, 0, i)) for (int j = i + 1; j < n - 1; ++j) if (isPalindrome(s, i + 1, j) && isPalindrome(s, j + 1, n - 1)) return true; return false; } }",
     "instruction": "Extract isPalindrome into a separate utility class."},
    {"name":"polish_extract_long_reformat","expected_intent":"EXTRACT_METHOD",
     "code":"public String reformat(String s) { Queue<Character> letters = new LinkedList<>(); Queue<Character> digits = new LinkedList<>(); for (char c : s.toCharArray()) { if (Character.isLetter(c)) letters.add(c); else digits.add(c); } if (Math.abs(letters.size() - digits.size()) > 1) return \"\"; StringBuilder result = new StringBuilder(); boolean useLetter = letters.size() > digits.size(); while (!letters.isEmpty() || !digits.isEmpty()) { if (useLetter) result.append(letters.poll()); else result.append(digits.poll()); useLetter = !useLetter; } return result.toString(); }",
     "instruction": "The reformat method does two distinct things: it separates characters into queues, then interleaves them into a result string. Extract the interleaving logic into a private helper called interleaveQueues."},
    # RENAME_SYMBOL (2)
    {"name":"polish_rename_short_judge","expected_intent":"RENAME_SYMBOL",
     "code":"public int findJudge(int n, int[][] trust) { int[] trustCounts = new int[n + 1]; for (int[] t : trust) { trustCounts[t[0]]--; trustCounts[t[1]]++; } for (int i = 1; i <= n; i++) if (trustCounts[i] == n - 1) return i; return -1; }",
     "instruction": "Rename trustCounts to trustScores."},
    {"name":"polish_rename_long_paths","expected_intent":"RENAME_SYMBOL",
     "code":"public int uniquePathsWithObstacles(int[][] grid) { int m = grid.length; int n = grid[0].length; if (grid[0][0] == 1) return 0; grid[0][0] = 1; for (int i = 1; i < m; ++i) grid[i][0] = (grid[i][0] == 0 && grid[i-1][0] == 1) ? 1 : 0; for (int i = 1; i < n; ++i) grid[0][i] = (grid[0][i] == 0 && grid[0][i-1] == 1) ? 1 : 0; for (int i = 1; i < m; ++i) for (int j = 1; j < n; ++j) if (grid[i][j] == 0) grid[i][j] = grid[i-1][j] + grid[i][j-1]; return grid[m-1][n-1]; }",
     "instruction": "The variable names in this grid path calculation are overly abbreviated. Rename m to rowCount, n to colCount throughout the entire method."},
    # SPLIT_LOOP (2)
    {"name":"polish_split_med_distinct","expected_intent":"SPLIT_LOOP",
     "code":"public int distinctIntegersAfterReversingAndAdding(int[] nums) { Set<Integer> distinct = new HashSet<>(); for (int num : nums) { distinct.add(num); int reversed = 0; while (num > 0) { reversed = reversed * 10 + num % 10; num /= 10; } distinct.add(reversed); } return distinct.size(); }",
     "instruction": "Split the loop into two: one for adding original values, one for adding reversed values."},
    {"name":"polish_split_long_gray","expected_intent":"SPLIT_LOOP",
     "code":"public List<Integer> grayCode(int n) { List<Integer> result = new ArrayList<>(); for (int i = 0; i < (1 << n); i++) result.add(i ^ (i >> 1)); return result; }",
     "instruction": "The for-loop in grayCode does two bitwise operations in one expression — the XOR and the right-shift. Split this into two separate computation steps."},
    # EXTRACT_VARIABLE (2)
    {"name":"polish_extvar_med_seconds","expected_intent":"EXTRACT_VARIABLE",
     "code":"public int minSeconds(int[] amount) { int total = amount[0] + amount[1] + amount[2]; int largestTwo = Math.max(amount[0] + amount[1], Math.max(amount[1] + amount[2], amount[0] + amount[2])); return (total + 1) / 2 - (largestTwo + 1) / 2 + largestTwo; }",
     "instruction": "Extract the expression (total + 1) / 2 into a variable called halfTotalCeil."},
    {"name":"polish_extvar_long_binary","expected_intent":"EXTRACT_VARIABLE",
     "code":"public int fixedPoint(int[] arr) { int left = 0, right = arr.length - 1; while (left < right) { int middle = left + (right - left) / 2; if (arr[middle] < middle) left = middle + 1; else right = middle; } return arr[left] == left ? left : -1; }",
     "instruction": "The expression left + (right - left) / 2 appears in the binary search computation. Extract this midpoint calculation into a local variable called midPoint and use it instead of repeating the expression."},
    # RARE INTENTS (4)
    {"name":"polish_inlinevar_dp","expected_intent":"INLINE_VARIABLE",
     "code":"public int minDistance(String word1, String word2) { int m = word1.length(), n = word2.length(); int[][] dp = new int[m+1][n+1]; for (int i = 0; i <= m; i++) dp[i][0] = i; for (int j = 0; j <= n; j++) dp[0][j] = j; for (int i = 1; i <= m; i++) for (int j = 1; j <= n; j++) if (word1.charAt(i-1) == word2.charAt(j-1)) dp[i][j] = dp[i-1][j-1]; else dp[i][j] = 1 + Math.min(dp[i-1][j], dp[i][j-1]); return dp[m][n]; }",
     "instruction": "Inline the variables m and n."},
    {"name":"polish_remflag_search","expected_intent":"REMOVE_CONTROL_FLAG",
     "code":"public int search(int[] arr, int target) { boolean found = false; int result = -1; for (int i = 0; i < arr.length; i++) { if (arr[i] == target) { found = true; result = i; break; } } if (found) return result; return -1; }",
     "instruction": "The method uses a boolean found flag to track whether an element was located in the loop. Remove this control flag entirely and use an early return directly when the element is matched."},
    {"name":"polish_pipeline_gray","expected_intent":"REPLACE_LOOP_WITH_PIPELINE",
     "code":"public List<Integer> grayCode(int n) { List<Integer> result = new ArrayList<>(); for (int i = 0; i < (1 << n); i++) result.add(i ^ (i >> 1)); return result; }",
     "instruction": "Replace the for-loop with a stream pipeline."},
    {"name":"polish_inline_nim","expected_intent":"INLINE_METHOD",
     "code":"public class Solution { public boolean canWinNim(int n) { return n % 4 != 0; } public boolean check(int n) { return canWinNim(n); } }",
     "instruction": "Inline the canWinNim method into its caller and remove it."},
]


# ============================================================
# GUIDANCE VARIANTS
# ============================================================

GUIDANCE_TEXT: Dict[str, str] = {
    "FLATTEN_CONDITIONAL": """### FLATTEN_CONDITIONAL
Convert nested if-statements into flat guard clauses.
ANTI-PATTERNS:
- Do NOT merge multiple guard clauses into one check using || or &&.
- Do NOT change any exception type or error message.
- Do NOT return the original code unchanged.
- Do NOT leave any if-inside-if nesting.
CONSTRAINTS:
- Each nested condition becomes a separate guard clause at method top.
- Each guard throws or returns immediately.
- Valid code runs after all guards pass.""",

    "DECOMPOSE_CONDITIONAL": """### DECOMPOSE_CONDITIONAL
Break a compound condition into named boolean variables.
ANTI-PATTERNS:
- Do NOT create any extra methods (no initialize(), setup(), helper).
- Do NOT invert logic with negation (!).
- Do NOT change the method signature.
CONSTRAINTS:
- Each boolean from new_structures_needed must be declared.
- Inside the target method: declare variables, assign conditions, use in if.""",

    "CONSOLIDATE_CONDITIONAL": """### CONSOLIDATE_CONDITIONAL
Merge duplicate conditional branches.
ANTI-PATTERNS: Do NOT change return values or outcomes.
CONSTRAINTS: Branches with identical bodies combined via || or lookup.""",

    "EXTRACT_CONSTANT": """### EXTRACT_CONSTANT
Replace a magic number with a static final constant.
ANTI-PATTERNS:
- Do NOT change any method signature, return type, or parameters.
- Do NOT remove any methods.
- Do NOT add validation checks or new exceptions.
CONSTRAINTS:
- Every occurrence of the literal must use the constant name.
- The ADD_CONSTANT instruction declares the constant. MODIFY_METHOD replaces.""",

    "EXTRACT_METHOD": """### EXTRACT_METHOD
Move code into a new private helper method.
ANTI-PATTERNS:
- Do NOT copy all parameters from original. Use ONLY listed parameters.
- Do NOT change the original method's signature or return type.
CONSTRAINTS:
- New helper exists and is called from original.
- Original method body calls helper instead of inline code.""",

    "RENAME_SYMBOL": """### RENAME_SYMBOL
Rename a symbol everywhere it appears.
ANTI-PATTERNS:
- Old name must NOT appear anywhere in output.
- Do NOT change method behavior or logic.
CONSTRAINTS:
- Update getter/setter names to match renamed field.""",

    "SPLIT_LOOP": """### SPLIT_LOOP
Separate one loop into multiple loops.
ANTI-PATTERNS: Do NOT create new methods. Keep in same method.
CONSTRAINTS: Each loop handles one operation. Same overall behavior.""",

    "REMOVE_CONTROL_FLAG": """### REMOVE_CONTROL_FLAG
Eliminate a boolean flag variable.
ANTI-PATTERNS: Do NOT keep the flag. Do NOT change return behavior.
CONSTRAINTS: Replace flag with direct break/return.""",

    "REPLACE_LOOP_WITH_PIPELINE": """### REPLACE_LOOP_WITH_PIPELINE
Convert loop into stream operations.
ANTI-PATTERNS: Do NOT keep the original loop.
CONSTRAINTS: Use .stream() with map/filter/collect. Preserve order/type.""",

    "INLINE_METHOD": """### INLINE_METHOD
Remove a method and inline its body at call sites.
ANTI-PATTERNS: Target method must NOT exist in output.
CONSTRAINTS: Replace every call with method body. Rename variables to avoid conflicts.""",

    "EXTRACT_VARIABLE": """### EXTRACT_VARIABLE
Assign repeated expression to a named local variable.
ANTI-PATTERNS: Do NOT change expression value or result type.
CONSTRAINTS: Declare variable before first use. Replace ALL occurrences.""",

    "INLINE_VARIABLE": """### INLINE_VARIABLE
Remove a local variable and use its value directly.
ANTI-PATTERNS: Variable declaration must NOT exist.
CONSTRAINTS: Replace every use with expression. Remove declaration.""",
}


GUIDANCE_ICL: Dict[str, str] = {
    "FLATTEN_CONDITIONAL": """### FLATTEN_CONDITIONAL
Convert nested if-statements into flat guard clauses.

EXAMPLE:
Base Code:
<code>void check(String s) { if(s!=null){ if(s.length()>0){ work(s); }
  } else { throw new IllegalArgumentException("null"); }}</code>
Instructions:
1. MODIFY_METHOD check - Move nested conditions to method top as guard clauses
CORRECT OUTPUT:
<code>void check(String s) { if(s==null) throw new IllegalArgumentException("null");
  if(s.length()==0) return; work(s); }</code>

ANTI-PATTERNS:
- Do NOT merge multiple guard clauses into one check using || or &&.
- Do NOT change any exception type or error message.
- Do NOT return the original code unchanged.
- Do NOT leave any if-inside-if nesting.
CONSTRAINTS:
- Each nested condition becomes a separate guard clause at method top.
- Each guard throws or returns immediately.
- Valid code runs after all guards pass.""",

    "DECOMPOSE_CONDITIONAL": """### DECOMPOSE_CONDITIONAL
Break a compound condition into named boolean variables.

EXAMPLE:
Base Code:
<code>boolean ok(int a){ if(a>=18&&a<=65) return true; return false; }</code>
Instructions:
1. ADD_FIELD isAdult - type: boolean
2. ADD_FIELD notRetired - type: boolean
3. MODIFY_METHOD ok - Declare booleans, assign conditions, use in if
CORRECT OUTPUT:
<code>boolean ok(int a){ boolean isAdult=a>=18; boolean notRetired=a<=65;
  return isAdult&&notRetired; }</code>

ANTI-PATTERNS:
- Do NOT create any extra methods (no initialize(), setup(), helper).
- Do NOT invert logic with negation (!).
- Do NOT change the method signature.
CONSTRAINTS:
- Each boolean from new_structures_needed must be declared.
- Inside the target method: declare variables, assign conditions, use in if.""",

    "CONSOLIDATE_CONDITIONAL": """### CONSOLIDATE_CONDITIONAL
Merge duplicate conditional branches.

EXAMPLE:
Base Code:
<code>String f(int x){ if(x==1) return "a"; if(x==2) return "a"; return "b"; }</code>
Instructions:
1. MODIFY_METHOD f - Combine duplicate branches into one check
CORRECT OUTPUT:
<code>String f(int x){ if(x==1||x==2) return "a"; return "b"; }</code>

ANTI-PATTERNS: Do NOT change return values or outcomes.
CONSTRAINTS: Branches with identical bodies combined via || or lookup.""",

    "EXTRACT_CONSTANT": """### EXTRACT_CONSTANT
Replace a magic number with a static final constant.

EXAMPLE:
Base Code:
<code>double area(double r){ return 3.14*r*r; }</code>
Instructions:
1. ADD_CONSTANT PI - static final double
2. MODIFY_METHOD area - Replace 3.14 with PI
CORRECT OUTPUT:
<code>private static final double PI=3.14; double area(double r){ return PI*r*r; }</code>

ANTI-PATTERNS:
- Do NOT change any method signature, return type, or parameters.
- Do NOT remove any methods.
- Do NOT add validation checks or new exceptions.
CONSTRAINTS:
- Every occurrence of the literal must use the constant name.""",

    "EXTRACT_METHOD": """### EXTRACT_METHOD
Move code into a new private helper method.

EXAMPLE:
Base Code:
<code>double f(double p,int q,double t){ double s=p*q; return s+s*t; }</code>
Instructions:
1. ADD_METHOD compute - private, returns double, params: s(double), t(double)
2. MODIFY_METHOD f - Call compute(s,t) instead of inline logic
CORRECT OUTPUT:
<code>double f(double p,int q,double t){ return compute(p*q,t); }
  private double compute(double s,double t){ return s+s*t; }</code>

ANTI-PATTERNS:
- Do NOT copy all parameters from original. Use ONLY listed parameters.
- Do NOT change the original method's signature or return type.
CONSTRAINTS:
- New helper exists and is called from original.""",

    "RENAME_SYMBOL": """### RENAME_SYMBOL
Rename a symbol everywhere it appears.

EXAMPLE:
Base Code:
<code>class U{ String n; String getN(){ return n; }}</code>
Instructions:
1. RENAME_SYMBOL n - Rename to username everywhere
2. MODIFY_METHOD getN - Return username, rename to getUsername
CORRECT OUTPUT:
<code>class U{ String username; String getUsername(){ return username; }}</code>

ANTI-PATTERNS:
- Old name must NOT appear anywhere in output.
- Do NOT change method behavior or logic.
CONSTRAINTS:
- Update getter/setter names to match renamed field.""",

    "SPLIT_LOOP": """### SPLIT_LOOP
Separate one loop into multiple loops.

EXAMPLE:
Base Code:
<code>void f(int[] a){ for(int i=0;i<a.length;i++){ a[i]*=2; print(a[i]); }}</code>
Instructions:
1. MODIFY_METHOD f - Split loop into doubling loop and printing loop
CORRECT OUTPUT:
<code>void f(int[] a){ for(int i=0;i<a.length;i++) a[i]*=2;
  for(int i=0;i<a.length;i++) print(a[i]); }</code>

ANTI-PATTERNS: Do NOT create new methods. Keep in same method.
CONSTRAINTS: Each loop handles one operation. Same overall behavior.""",

    "REMOVE_CONTROL_FLAG": """### REMOVE_CONTROL_FLAG
Eliminate a boolean flag variable.

EXAMPLE:
Base Code:
<code>int f(int[] a,int t){ boolean found=false; int r=-1;
  for(int i=0;i<a.length;i++) if(a[i]==t){ found=true; r=i; break; }
  if(found) return r; return -1; }</code>
Instructions:
1. MODIFY_METHOD f - Remove found flag, use early return
CORRECT OUTPUT:
<code>int f(int[] a,int t){ for(int i=0;i<a.length;i++)
  if(a[i]==t) return i; return -1; }</code>

ANTI-PATTERNS: Do NOT keep the flag. Do NOT change return behavior.
CONSTRAINTS: Replace flag with direct break/return.""",

    "REPLACE_LOOP_WITH_PIPELINE": """### REPLACE_LOOP_WITH_PIPELINE
Convert loop into stream operations.

EXAMPLE:
Base Code:
<code>List<Integer> f(int[] a){ List<Integer> r=new ArrayList<>();
  for(int x:a) if(x>0) r.add(x); return r; }</code>
Instructions:
1. MODIFY_METHOD f - Replace for-loop with stream
CORRECT OUTPUT:
<code>List<Integer> f(int[] a){ return Arrays.stream(a).filter(x->x>0)
  .boxed().collect(Collectors.toList()); }</code>

ANTI-PATTERNS: Do NOT keep the original loop.
CONSTRAINTS: Use .stream() with map/filter/collect. Preserve order/type.""",

    "INLINE_METHOD": """### INLINE_METHOD
Remove a method and inline its body at call sites.

EXAMPLE:
Base Code:
<code>boolean canWin(int n){ return n%4!=0; } boolean check(int n){ return canWin(n); }</code>
Instructions:
1. Remove canWin, inline n%4!=0 into check
CORRECT OUTPUT:
<code>boolean check(int n){ return n%4!=0; }</code>

ANTI-PATTERNS: Target method must NOT exist in output.
CONSTRAINTS: Replace every call with method body. Rename variables to avoid conflicts.""",

    "EXTRACT_VARIABLE": """### EXTRACT_VARIABLE
Assign repeated expression to a named local variable.

EXAMPLE:
Base Code:
<code>int f(int n){ return n*n+2*n*n; }</code>
Instructions:
1. MODIFY_METHOD f - Assign n*n to variable sq, replace all occurrences
CORRECT OUTPUT:
<code>int f(int n){ int sq=n*n; return sq+2*sq; }</code>

ANTI-PATTERNS: Do NOT change expression value or result type.
CONSTRAINTS: Declare variable before first use. Replace ALL occurrences.""",

    "INLINE_VARIABLE": """### INLINE_VARIABLE
Remove a local variable and use its value directly.

EXAMPLE:
Base Code:
<code>int f(){ int x=5+3; return x*2; }</code>
Instructions:
1. MODIFY_METHOD f - Replace x with (5+3), remove declaration
CORRECT OUTPUT:
<code>int f(){ return (5+3)*2; }</code>

ANTI-PATTERNS: Variable declaration must NOT exist.
CONSTRAINTS: Replace every use with expression. Remove declaration.""",
}


# ============================================================
# HELPERS
# ============================================================

def inject_analysis_guidance(prompts, intent):
    base = prompts["planner"]["architect_analysis"]
    g = prompts["planner"]["analysis_guidance"].get(intent, "")
    return base + "\n" + g if g else base

def inject_synthesis_guidance(prompts, intent):
    base = prompts["planner"]["architect"]
    g = prompts["planner"]["synthesis_guidance"].get(intent, "")
    return base + "\n" + g if g else base

def run_phase4(original_code, refactored_code, intent, plan):
    validator = Validator()
    findings = []
    orig_cc = validator.get_complexity(original_code)
    refac_cc = validator.get_complexity(refactored_code)

    skip_cc = intent in ("INLINE_METHOD",)
    loosen_cc = intent in ("SPLIT_LOOP",)
    extract_cc = intent in ("EXTRACT_METHOD",)

    if not skip_cc:
        threshold = orig_cc + (1 if loosen_cc else 0)
        if not extract_cc and refac_cc > threshold:
            findings.append(f"CC: {orig_cc}→{refac_cc} (limit≤{threshold})")

    target_scopes = []
    for m in plan.get("ast_mutations", []):
        t = m.get("target", "")
        if t and t not in target_scopes:
            target_scopes.append(t)
    if plan.get("target_class"):
        target_scopes.append(plan["target_class"])

    try:
        bf = validator.verify_boundary(original_code, refactored_code, target_scopes)
        if bf:
            findings.append(f"Boundary: {bf.error_report.message[:80]}")
    except Exception:
        pass

    try:
        ri = RefactorIntent(intent)
        intf = validator.verify_intent(ri, original_code, refactored_code)
        if intf:
            findings.append(f"Intent: {intf.error_report.message[:80]}")
    except Exception:
        pass

    orig_methods = set(re.findall(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(', original_code))
    refac_methods = set(re.findall(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(', refactored_code))
    dropped = orig_methods - refac_methods
    if dropped:
        findings.append(f"Methods dropped: {dropped}")

    return {"pass": len(findings) == 0, "findings": findings, "orig_cc": orig_cc, "refac_cc": refac_cc}


# ============================================================
# MAIN
# ============================================================

async def main():
    print("=" * 70)
    print("GENERATOR ICL COMPARISON")
    print("TEXT guidance vs ICL guidance (20 cases, 12 intents)")
    print("=" * 70)

    # Phase 1: Planner (cached)
    plans_file = "test_results/generator_compare_plans.json"
    try:
        with open(plans_file) as f:
            plans_data = json.load(f)
        print(f"Loaded {len(plans_data)} cached plans from {plans_file}")
    except Exception:
        print("Running Planner for 20 cases...")
        h = ModelTestHarness("planner")
        await h.load_model()
        prompts = h.prompts
        plans_data = []
        for case in TEST_CASES:
            code, inst = case["code"], case["instruction"]
            # Classifier
            cr = await h.generate(prompts["planner"]["classifier"], f"<code>{code}</code>\n<instruction>{inst}</instruction>",
                                  temp=0.1, max_tokens=500, response_model=IntentClassifierResponse)
            intent_key = case["expected_intent"]
            ip = {"specific_intent": case["expected_intent"]}
            if cr["success"]:
                try:
                    ci = ResponseParser.extract_json(cr["content"], IntentClassifierResponse)
                    intent_key = ci.intent_packet.specific_intent.value
                    ip = ci.intent_packet.model_dump()
                except Exception:
                    pass
            # Analysis
            await h.clear_context()
            asys = inject_analysis_guidance(prompts, intent_key)
            ar = await h.generate(asys, f"Intent Packet: {json.dumps(ip)}\nUser Instruction: {inst}\nCode: <code>{code}</code>",
                                  temp=0.1, max_tokens=1024, response_model=ArchitectAnalysisResponse)
            ad = {}
            if ar["success"]:
                try:
                    ad = ResponseParser.extract_json(ar["content"], ArchitectAnalysisResponse).model_dump()
                except Exception:
                    pass
            # Architect
            await h.clear_context()
            ssys = inject_synthesis_guidance(prompts, intent_key)
            sr = await h.generate(ssys, f"Analysis: {json.dumps(ad)}\nIntent: {json.dumps(ip)}\nInstruction: {inst}\nCode: <code>{code}</code>",
                                  temp=0.1, max_tokens=2048, response_model=ASTArchitectResponse)
            plan = {}
            if sr["success"]:
                try:
                    plan = ResponseParser.extract_json(sr["content"], ASTArchitectResponse).ast_modification_plan.model_dump()
                except Exception:
                    pass
            plans_data.append({"name": case["name"], "intent": intent_key, "code": code, "plan": plan})
        await h.unload_model()
        with open(plans_file, "w") as f:
            json.dump(plans_data, f, indent=2)
        print(f"Cached {len(plans_data)} plans.")

    # Phase 2 + 3: Generator comparison
    comparison = []
    h = ModelTestHarness("generator")
    await h.load_model()

    for guid_label, guidance_dict in [("TEXT", GUIDANCE_TEXT), ("ICL", GUIDANCE_ICL)]:
        print(f"\n--- MODE: {guid_label} ---")
        for pd in plans_data:
            name = pd["name"]
            intent = pd["intent"]
            code = pd["code"]
            plan = pd.get("plan", {})

            await h.clear_context()
            system = guidance_dict.get(intent, "Silent execution engine. Apply instructions.")
            user = format_plan_for_generator(plan, code) if plan else f"Base Code:\n<code>{code}</code>\n\nNo mutations."

            gr = await h.generate(system, user, temp=0.1, max_tokens=2048)
            output_code = ""
            cm = re.search(r'<code>(.*?)</code>', gr["content"], re.DOTALL)
            if cm:
                output_code = cm.group(1).strip()

            syntax_ok = False
            try:
                import javalang
                wrapped = f"class __W__ {{ {output_code} }}" if "class" not in output_code else output_code
                javalang.parse.parse(wrapped)
                syntax_ok = True
            except Exception:
                pass

            p4 = {"pass": False, "findings": [], "orig_cc": 0, "refac_cc": 0}
            if syntax_ok and plan:
                p4 = run_phase4(code, output_code, intent, plan)

            orig_methods = set(re.findall(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(', code))
            refac_methods = set(re.findall(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(', output_code))
            methods_ok = orig_methods.issubset(refac_methods)

            comparison.append({
                "name": name, "intent": intent, "mode": guid_label,
                "syntax_ok": syntax_ok, "phase4_pass": p4["pass"],
                "phase4_findings": p4["findings"],
                "orig_cc": p4["orig_cc"], "refac_cc": p4["refac_cc"],
                "methods_ok": methods_ok,
                "duration": gr["duration"],
                "output_len": len(output_code),
            })
            print(f"  {name[:45]:45} syntax={'✓' if syntax_ok else '✗'} phase4={'✓' if p4['pass'] else '✗'} methods={'✓' if methods_ok else '✗'}")

    await h.unload_model()

    # Phase 4: Report
    print(f"\n{'='*70}")
    print("COMPARISON REPORT")
    print(f"{'='*70}")

    for mode in ["TEXT", "ICL"]:
        mr = [r for r in comparison if r["mode"] == mode]
        s = sum(1 for r in mr if r["syntax_ok"])
        p = sum(1 for r in mr if r["phase4_pass"])
        m = sum(1 for r in mr if r["methods_ok"])
        total = len(mr)
        print(f"\n  {mode}:")
        print(f"    Syntax valid:  {s}/{total}")
        print(f"    Phase 4 pass:  {p}/{total}")
        print(f"    Methods OK:    {m}/{total}")

        # Per-intent
        from collections import defaultdict
        intents = defaultdict(lambda: {"total": 0, "syntax": 0, "phase4": 0, "methods": 0})
        for r in mr:
            intent = r["intent"]
            intents[intent]["total"] += 1
            if r["syntax_ok"]: intents[intent]["syntax"] += 1
            if r["phase4_pass"]: intents[intent]["phase4"] += 1
            if r["methods_ok"]: intents[intent]["methods"] += 1
        for intent, stats in sorted(intents.items()):
            print(f"      {intent[:35]:35} syntax={stats['syntax']}/{stats['total']} phase4={stats['phase4']}/{stats['total']} methods={stats['methods']}/{stats['total']}")

    # Per-case comparison
    print(f"\n  PER-CASE DIFF (ICL minus TEXT):")
    for pd in plans_data:
        name = pd["name"]
        t = next((r for r in comparison if r["name"] == name and r["mode"] == "TEXT"), None)
        i = next((r for r in comparison if r["name"] == name and r["mode"] == "ICL"), None)
        if t and i:
            t_pass = t["phase4_pass"]
            i_pass = i["phase4_pass"]
            t_cc = t.get("refac_cc", 0) - t.get("orig_cc", 0)
            i_cc = i.get("refac_cc", 0) - i.get("orig_cc", 0)
            diff = ""
            if t_pass != i_pass:
                diff = f"PHASE4: {t_pass}→{i_pass}"
            elif t_cc != i_cc and t_cc > 0:
                diff = f"CC delta: +{t_cc}→+{i_cc}"
            if diff:
                better = "ICL BETTER" if (not t_pass and i_pass) or (t_cc > i_cc and i_cc <= 0) else ""
                print(f"    {name[:45]:45} {diff} {better}")

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = f"test_results/generator_compare_{ts}.json"
    with open(path, "w") as f:
        json.dump(comparison, f, indent=2, default=str)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
