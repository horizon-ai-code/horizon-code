"""Pipeline test: planner -> generator -> validator (skip judge)."""
import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, ".")

from app.modules.agent_service import AgentService
from app.modules.orchestrator import Orchestrator
from app.modules.validator import Validator
from app.utils.types import ExitStatus


TEST_CASES: List[Dict[str, Any]] = [
    {
        "name": "EXTRACT_METHOD",
        "code": """public String reformat(String s) {
    Queue<Character> letters = new LinkedList<>();
    Queue<Character> digits = new LinkedList<>();
    for (char c : s.toCharArray()) {
        if (Character.isLetter(c)) letters.add(c);
        else digits.add(c);
    }
    if (Math.abs(letters.size() - digits.size()) > 1) return "";
    StringBuilder result = new StringBuilder();
    boolean useLetter = letters.size() > digits.size();
    while (!letters.isEmpty() || !digits.isEmpty()) {
        if (useLetter) result.append(letters.poll());
        else result.append(digits.poll());
        useLetter = !useLetter;
    }
    return result.toString();
}""",
        "instruction": "The reformat method separates characters into queues then interleaves them. Extract the interleaving logic into a private helper called interleaveQueues that takes the two queues as parameters and returns StringBuilder. Keep separation in main method and call interleaveQueues from there.",
    },
    {
        "name": "EXTRACT_CONSTANT",
        "code": """public String boxCategory(int length, int width, int height, int mass) {
    boolean bulky = length >= 10000 || width >= 10000 || height >= 10000 || length * width * height >= 1000000000;
    boolean heavy = mass >= 100;
    if (bulky && heavy) return "Both";
    else if (bulky) return "Bulky";
    else if (heavy) return "Heavy";
    else return "Neither";
}""",
        "instruction": "Extract 10000 into BULKY_DIMENSION_THRESHOLD and 100 into HEAVY_MASS_THRESHOLD.",
    },
    {
        "name": "FLATTEN_CONDITIONAL",
        "code": """public int increasingQuadruplets(int[] nums) {
    int n = nums.length, count = 0;
    for(int i = 0; i < n - 3; i++) {
        for(int j = i + 1; j < n - 2; j++) {
            for(int k = j + 1; k < n - 1; k++) {
                if(nums[i] < nums[k] && nums[k] < nums[j]) {
                    for(int l = k + 1; l < n; l++) {
                        if(nums[j] < nums[l]) count++;
                    }
                }
            }
        }
    }
    return count;
}""",
        "instruction": "The four nested for-loops create a pyramid of checks. Restructure using guard clauses with continue. Each invalid comparison skips to next iteration immediately at loop top. Remove all nesting.",
    },
    {
        "name": "DECOMPOSE_CONDITIONAL",
        "code": """public boolean canPermutePalindrome(String s) {
    HashMap<Character, Integer> count = new HashMap<>();
    for(char c : s.toCharArray())
        count.put(c, count.getOrDefault(c, 0) + 1);
    int odd_count = 0;
    for(int value : count.values()) {
        if(value % 2 != 0) odd_count++;
    }
    return odd_count <= 1;
}""",
        "instruction": "Decompose the odd-count validation check into a boolean variable called hasPalindromePermutation that explains what the threshold means for palindrome properties.",
    },
    {
        "name": "RENAME_SYMBOL",
        "code": """public int uniquePathsWithObstacles(int[][] grid) {
    int m = grid.length;
    int n = grid[0].length;
    if (grid[0][0] == 1) return 0;
    grid[0][0] = 1;
    for (int i = 1; i < m; ++i)
        grid[i][0] = (grid[i][0] == 0 && grid[i-1][0] == 1) ? 1 : 0;
    for (int i = 1; i < n; ++i)
        grid[0][i] = (grid[0][i] == 0 && grid[0][i-1] == 1) ? 1 : 0;
    for (int i = 1; i < m; ++i)
        for (int j = 1; j < n; ++j)
            if (grid[i][j] == 0)
                grid[i][j] = grid[i-1][j] + grid[i][j-1];
    return grid[m-1][n-1];
}""",
        "instruction": "Rename m to rowCount and n to colCount throughout the entire method. Update every reference.",
    },
]


class MockDB:
    def __init__(self):
        self.sessions = {}
    def create_session(self, id=None, instruction="", original_code=""):
        self.sessions[id] = {}
    def log_status(self, **kw):
        pass
    def complete_session(self, **kw):
        pass
    def mark_as_halted(self, id):
        pass


class MockClient:
    def __init__(self, cid: str):
        self.id = cid
        self.statuses = []
        self.results = None
    @property
    def is_stale(self) -> bool:
        return False
    async def send_status(self, role, content, **kw):
        self.statuses.append((role, str(content)[:200]))
    async def send_result(self, **kw):
        self.results = kw
    async def send_insights(self, insights):
        pass


async def run_case(case: Dict[str, Any], index: int, total: int) -> Dict[str, Any]:
    case_name = case["name"]
    print(f"\n{'='*60}")
    print(f"[{index+1}/{total}] {case_name}")
    print(f"{'='*60}")

    agent = AgentService()
    validator = Validator()
    db = MockDB()

    orch = Orchestrator(agent, validator, db)
    orch.SKIP_JUDGE = True

    client = MockClient(f"test-{case_name}")

    t_start = time.time()
    try:
        await orch.execute_orchestration(client, case["code"], case["instruction"])
    except Exception as e:
        print(f"  Orchestration error: {e}")
    total_duration = int((time.time() - t_start) * 1000)

    state = getattr(orch, 'state', None)
    if state:
        original_cc = state.original_complexity
        working_code = state.working_code
        refactored_cc = validator.get_complexity(working_code)
        feedback = state.cumulative_feedback

        result = {
            "case": case_name,
            "exit_status": state.exit_status.value if state.exit_status else "N/A",
            "strategy_iter": state.strategy_iter,
            "syntax_iter": state.syntax_iter,
            "current_phase": state.current_phase,
            "total_duration_ms": total_duration,
            "original_cc": original_cc,
            "refactored_cc": refactored_cc,
            "cc_delta": refactored_cc - original_cc,
            "working_code_changed": working_code.strip() != case["code"].strip(),
            "working_code_unchanged": working_code.strip() == case["code"].strip(),
            "validation_findings": [f for f in feedback],
            "num_validation_findings": len(feedback),
            "mutation_index": state.mutation_index,
            "mutation_queue_len": len(state.mutation_queue) if hasattr(state, 'mutation_queue') else 0,
        }

        if hasattr(state, 'gen_timings') and state.gen_timings:
            result["gen_timings"] = state.gen_timings
            ok_steps = sum(1 for t in state.gen_timings if t.get("status") == "OK")
            fail_steps = sum(1 for t in state.gen_timings if t.get("status") != "OK")
            result["gen_ok_steps"] = ok_steps
            result["gen_fail_steps"] = fail_steps
            total_gen = sum(t.get("time_ms", 0) for t in state.gen_timings)
            result["gen_total_time_ms"] = total_gen
        else:
            result["gen_timings"] = []
            result["gen_ok_steps"] = 0
            result["gen_fail_steps"] = 0
            result["gen_total_time_ms"] = 0
    else:
        result = {
            "case": case_name,
            "error": "No state available",
            "total_duration_ms": total_duration,
        }

    print(f"  Status:   {result.get('exit_status', '?')}")
    print(f"  CC:       {result.get('original_cc', '?')} → {result.get('refactored_cc', '?')} (Δ={result.get('cc_delta', '?')})")
    print(f"  Findings: {result.get('num_validation_findings', '?')}")
    print(f"  Gen OK:   {result.get('gen_ok_steps', '?')}/{result.get('gen_ok_steps', 0) + result.get('gen_fail_steps', 0)}")
    print(f"  Time:     {total_duration}ms")

    await agent.unload()
    return result


async def main() -> None:
    os.makedirs("tests/results", exist_ok=True)

    all_results = []
    for i, case in enumerate(TEST_CASES):
        r = await run_case(case, i, len(TEST_CASES))
        all_results.append(r)

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_cases": len(all_results),
        "results": all_results,
    }
    with open("tests/results/no_judge_pipeline_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print("SUMMARY — No Judge Pipeline")
    print(f"{'='*60}")
    print(f"{'Case':25s} {'Status':25s} {'CC Δ':>5s} {'Findings':>9s} {'Gen OK':>6s} {'Time':>8s}")
    print("-" * 80)
    for r in all_results:
        findings = r.get('num_validation_findings', 0)
        cc_delta = r.get('cc_delta', 0)
        gen_ok = f"{r.get('gen_ok_steps', '?')}/{r.get('gen_ok_steps', 0) + r.get('gen_fail_steps', 0)}"
        status = r.get('exit_status', '?')
        if r.get('working_code_unchanged'):
            status += " (UNCHANGED)"
        print(f"{r['case']:25s} {status:25s} {cc_delta:>+5d} {findings:>9d} {gen_ok:>6s} {r.get('total_duration_ms', 0):>8d}ms")
    print(f"\nResults saved to tests/results/no_judge_pipeline_results.json")


if __name__ == "__main__":
    asyncio.run(main())
