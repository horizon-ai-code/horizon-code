"""Integration test with 20 polish cases — full orchestrator pipeline."""
import asyncio
import json
import sys
import time
from datetime import datetime
from typing import List

sys.path.insert(0, ".")

from tests.pipeline.test_integration import IntegrationTester

# 20 Polish cases with varying instruction lengths
TEST_CASES = [
    # FLATTEN (2)
    {
        "name": "polish_flatten_short_mindist",
        "code": "public int minDistance(String word1, String word2) { int m = word1.length(), n = word2.length(); int[][] dp = new int[m+1][n+1]; for(int i = 0; i <= m; i++) { for(int j = 0; j <= n; j++) { if(i == 0 || j == 0) dp[i][j] = i + j; else if(word1.charAt(i-1) == word2.charAt(j-1)) dp[i][j] = dp[i-1][j-1]; else dp[i][j] = 1 + Math.min(dp[i-1][j], dp[i][j-1]); } } return dp[m][n]; }",
        "instruction": "Flatten.",
    },
    {
        "name": "polish_flatten_long_quads",
        "code": "public int increasingQuadruplets(int[] nums) { int n = nums.length, count = 0; for(int i = 0; i < n - 3; i++) { for(int j = i + 1; j < n - 2; j++) { for(int k = j + 1; k < n - 1; k++) { if(nums[i] < nums[k] && nums[k] < nums[j]) { for(int l = k + 1; l < n; l++) { if(nums[j] < nums[l]) count++; } } } } } return count; }",
        "instruction": "The four nested for-loops in this method create a pyramid of condition checks that is difficult to follow. Restructure the entire method body to use guard clauses with continue. Each invalid comparison should skip to the next iteration immediately at the top of the loop. Remove all nesting — no for-loop should appear inside another for-loop's body after refactoring.",
    },
    # DECOMPOSE (2)
    {
        "name": "polish_decompose_med_nim",
        "code": "public boolean canWinNim(int n) { return n % 4 != 0; }",
        "instruction": "Decompose this simple boolean expression into a well-named variable that explains what the calculation means in game theory.",
    },
    {
        "name": "polish_decompose_long_palindrome",
        "code": "public boolean canPermutePalindrome(String s) { HashMap<Character, Integer> count = new HashMap<>(); for(char c : s.toCharArray()) count.put(c, count.getOrDefault(c, 0) + 1); int odd_count = 0; for(int value : count.values()) { if(value % 2 != 0) odd_count++; } return odd_count <= 1; }",
        "instruction": "The loop body in canPermutePalindrome mixes character counting with implicit type operations. Break the logic apart: decompose the odd-count validation check into a clearly named boolean variable called hasPalindromePermutation that explains what the threshold means for palindrome properties.",
    },
    # CONSOLIDATE (2)
    {
        "name": "polish_consolidate_short_fixed",
        "code": "public int fixedPoint(int[] arr) { int left = 0, right = arr.length - 1; while (left < right) { int middle = left + (right - left) / 2; if (arr[middle] < middle) left = middle + 1; else right = middle; } return arr[left] == left ? left : -1; }",
        "instruction": "Consolidate.",
    },
    {
        "name": "polish_consolidate_long_lhs",
        "code": "public int findLHS(int[] nums) { HashMap<Integer, Integer> count = new HashMap<>(); for (int num : nums) count.put(num, count.getOrDefault(num, 0) + 1); int longest_sequence = 0; for (int key : count.keySet()) { if (count.containsKey(key + 1)) longest_sequence = Math.max(longest_sequence, count.get(key) + count.get(key + 1)); } return longest_sequence; }",
        "instruction": "Look at how the hashmap is populated and then iterated. The two sequential for-loops can be merged into a single pass. Also, the conditional check inside the second loop has an implicit assumption about key ordering — consolidate the key lookup into a single well-structured condition using the map's built-in methods instead of separate containsKey and get calls.",
    },
    # EXTRACT_CONSTANT (2)
    {
        "name": "polish_const_short_box",
        "code": "public String boxCategory(int length, int width, int height, int mass) { boolean bulky = length >= 10000 || width >= 10000 || height >= 10000 || length * width * height >= 1000000000; boolean heavy = mass >= 100; if (bulky && heavy) return \"Both\"; else if (bulky) return \"Bulky\"; else if (heavy) return \"Heavy\"; else return \"Neither\"; }",
        "instruction": "Extract 10000 into BULKY_DIMENSION_THRESHOLD and 100 into HEAVY_MASS_THRESHOLD.",
    },
    {
        "name": "polish_const_long_derangement",
        "code": "public int findDerangement(int n) { long[] dp = new long[n + 1]; dp[2] = 1; for (int i = 3; i <= n; i++) dp[i] = (i - 1) * (dp[i - 1] + dp[i - 2]) % 1000000007; return (int) dp[n]; }",
        "instruction": "There are several literal values used in the arithmetic that represent mathematical identities — particularly the modulo value 1000000007 which is used for overflow prevention. Extract this magic number into a named constant called MOD. Also, find any other literals that benefit from naming and extract them too. The constant declaration should be at the class level as static final.",
    },
    # EXTRACT_METHOD (2)
    {
        "name": "polish_extract_short_palindrome",
        "code": "public class Solution { private boolean isPalindrome(String s, int start, int end) { while (start < end) { if (s.charAt(start) != s.charAt(end)) return false; start++; end--; } return true; } public boolean checkPartitioning(String s) { int n = s.length(); for (int i = 0; i < n - 2; ++i) if (isPalindrome(s, 0, i)) for (int j = i + 1; j < n - 1; ++j) if (isPalindrome(s, i + 1, j) && isPalindrome(s, j + 1, n - 1)) return true; return false; } }",
        "instruction": "Extract isPalindrome into a separate utility class.",
    },
    {
        "name": "polish_extract_long_reformat",
        "code": "public String reformat(String s) { Queue<Character> letters = new LinkedList<>(); Queue<Character> digits = new LinkedList<>(); for (char c : s.toCharArray()) { if (Character.isLetter(c)) letters.add(c); else digits.add(c); } if (Math.abs(letters.size() - digits.size()) > 1) return \"\"; StringBuilder result = new StringBuilder(); boolean useLetter = letters.size() > digits.size(); while (!letters.isEmpty() || !digits.isEmpty()) { if (useLetter) result.append(letters.poll()); else result.append(digits.poll()); useLetter = !useLetter; } return result.toString(); }",
        "instruction": "The reformat method does two distinct things: it separates characters into queues, then interleaves them into a result string. Extract the interleaving logic — everything after the initial separation into queues — into a private helper called interleaveQueues. The helper should take the two queues as parameters and return the StringBuilder result. Keep the character separation in the main method and call interleaveQueues from there.",
    },
    # RENAME_SYMBOL (2)
    {
        "name": "polish_rename_short_judge",
        "code": "public int findJudge(int n, int[][] trust) { int[] trustCounts = new int[n + 1]; for (int[] t : trust) { trustCounts[t[0]]--; trustCounts[t[1]]++; } for (int i = 1; i <= n; i++) if (trustCounts[i] == n - 1) return i; return -1; }",
        "instruction": "Rename trustCounts to trustScores.",
    },
    {
        "name": "polish_rename_long_paths",
        "code": "public int uniquePathsWithObstacles(int[][] grid) { int m = grid.length; int n = grid[0].length; if (grid[0][0] == 1) return 0; grid[0][0] = 1; for (int i = 1; i < m; ++i) grid[i][0] = (grid[i][0] == 0 && grid[i-1][0] == 1) ? 1 : 0; for (int i = 1; i < n; ++i) grid[0][i] = (grid[0][i] == 0 && grid[0][i-1] == 1) ? 1 : 0; for (int i = 1; i < m; ++i) for (int j = 1; j < n; ++j) if (grid[i][j] == 0) grid[i][j] = grid[i-1][j] + grid[i][j-1]; return grid[m-1][n-1]; }",
        "instruction": "The variable names in this grid path calculation are overly abbreviated. Rename m to rowCount, n to colCount throughout the entire method. Update every reference — the loop bounds, the array indexing, and any condition checks that use these variables. Do not change the method's logic or behavior in any other way.",
    },
    # SPLIT_LOOP (2)
    {
        "name": "polish_split_med_distinct",
        "code": "public int distinctIntegersAfterReversingAndAdding(int[] nums) { Set<Integer> distinct = new HashSet<>(); for (int num : nums) { distinct.add(num); int reversed = 0; while (num > 0) { reversed = reversed * 10 + num % 10; num /= 10; } distinct.add(reversed); } return distinct.size(); }",
        "instruction": "Split the loop into two: one for adding original values, one for adding reversed values.",
    },
    {
        "name": "polish_split_long_gray",
        "code": "public List<Integer> grayCode(int n) { List<Integer> result = new ArrayList<>(); for (int i = 0; i < (1 << n); i++) result.add(i ^ (i >> 1)); return result; }",
        "instruction": "The for-loop in grayCode does two bitwise operations in one expression — the XOR and the right-shift. Split this into two separate computation steps: first calculate the shifted value into a variable, then XOR it with the original index into the result list. This clarifies the bit-manipulation logic without changing the output.",
    },
    # EXTRACT_VARIABLE (2)
    {
        "name": "polish_extvar_med_seconds",
        "code": "public int minSeconds(int[] amount) { int total = amount[0] + amount[1] + amount[2]; int largestTwo = Math.max(amount[0] + amount[1], Math.max(amount[1] + amount[2], amount[0] + amount[2])); return (total + 1) / 2 - (largestTwo + 1) / 2 + largestTwo; }",
        "instruction": "Extract the expression (total + 1) / 2 into a variable called halfTotalCeil.",
    },
    {
        "name": "polish_extvar_long_binary",
        "code": "public int fixedPoint(int[] arr) { int left = 0, right = arr.length - 1; while (left < right) { int middle = left + (right - left) / 2; if (arr[middle] < middle) left = middle + 1; else right = middle; } return arr[left] == left ? left : -1; }",
        "instruction": "The expression left + (right - left) / 2 appears in the binary search computation. Extract this midpoint calculation into a local variable called midPoint and use it instead of repeating the expression. While you're at it, also extract arr[middle] < middle into a boolean variable called shouldSearchRight — this makes the conditional logic self-documenting.",
    },
    # INLINE_VARIABLE (1)
    {
        "name": "polish_inlinevar_dp",
        "code": "public int minDistance(String word1, String word2) { int m = word1.length(), n = word2.length(); int[][] dp = new int[m+1][n+1]; for (int i = 0; i <= m; i++) dp[i][0] = i; for (int j = 0; j <= n; j++) dp[0][j] = j; for (int i = 1; i <= m; i++) for (int j = 1; j <= n; j++) if (word1.charAt(i-1) == word2.charAt(j-1)) dp[i][j] = dp[i-1][j-1]; else dp[i][j] = 1 + Math.min(dp[i-1][j], dp[i][j-1]); return dp[m][n]; }",
        "instruction": "Inline the variables m and n.",
    },
    # REMOVE_CONTROL_FLAG (1)
    {
        "name": "polish_remflag_search",
        "code": "public int search(int[] arr, int target) { boolean found = false; int result = -1; for (int i = 0; i < arr.length; i++) { if (arr[i] == target) { found = true; result = i; break; } } if (found) return result; return -1; }",
        "instruction": "The method uses a boolean found flag to track whether an element was located in the loop. Remove this control flag entirely and use an early return directly when the element is matched.",
    },
    # REPLACE_LOOP_WITH_PIPELINE (1)
    {
        "name": "polish_pipeline_gray",
        "code": "public List<Integer> grayCode(int n) { List<Integer> result = new ArrayList<>(); for (int i = 0; i < (1 << n); i++) result.add(i ^ (i >> 1)); return result; }",
        "instruction": "Replace the for-loop with a stream pipeline.",
    },
    # INLINE_METHOD (1)
    {
        "name": "polish_inline_nim",
        "code": "public class Solution { public boolean canWinNim(int n) { return n % 4 != 0; } public boolean check(int n) { return canWinNim(n); } }",
        "instruction": "Inline the canWinNim method into its caller and remove it.",
    },
]


async def main():
    tester = IntegrationTester(uri="ws://localhost:8000/ws")
    
    print("=" * 70)
    print("POLISH 20-CASE ORCHESTRATOR INTEGRATION TEST")
    print(f"{len(TEST_CASES)} cases, full Phase 1-6 pipeline")
    print("=" * 70)
    
    results = []
    for i, case in enumerate(TEST_CASES):
        print(f"\n[{i+1:2d}/20] {case['name']}")
        print(f"      code={len(case['code'])}c | inst={len(case['instruction'])}c")
        try:
            result = await tester.run_test_case(case)
            results.append(result)
            status = "✓" if result.passed else "✗"
            print(f"      {status} | {result.duration:.1f}s | CC: {result.original_complexity}→{result.refactored_complexity}")
            if result.error:
                print(f"      Error: {result.error}")
        except Exception as e:
            print(f"      ✗ ERROR: {str(e)[:100]}")
    
    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    
    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"  Passed: {passed}/{total}")
    print(f"  Failed: {total - passed}/{total}")
    
    if results:
        avg_duration = sum(r.duration for r in results) / len(results)
        print(f"  Avg Duration: {avg_duration:.1f}s")
    
    # Per-test detail
    print(f"\n{'='*70}")
    print("DETAIL")
    for r in results:
        status = "✓" if r.passed else "✗"
        print(f"  {status} {r.name[:50]:50} {r.duration:6.1f}s  CC: {r.original_complexity}→{r.refactored_complexity}")
        if r.events:
            # Count audit cycles
            audit_count = sum(1 for e in r.events if isinstance(e, dict) and e.get("type") == "status" and "Audit Finished" in str(e.get("content", "")))
            if audit_count:
                print(f"      audits={audit_count}")
    
    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = f"/tmp/horizon_polish_integration_{ts}.json"
    with open(path, "w") as f:
        json.dump([{"name": r.name, "passed": r.passed, "verdict": r.verdict, 
                      "duration": r.duration, "outer_loops": r.outer_loops,
                      "error": r.error, "cc_orig": r.original_complexity, 
                      "cc_refac": r.refactored_complexity} for r in results], f, indent=2)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
