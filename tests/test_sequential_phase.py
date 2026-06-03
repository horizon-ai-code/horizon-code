"""Sequential mutation application — 5-case validation with generation timing."""
import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, ".")

from app.modules.orchestrator import Orchestrator
from app.modules.validator import Validator
from app.modules.agent_service import AgentService
from app.utils.paths import MODELS_CONFIG_PATH, PROMPTS_CONFIG_PATH

import yaml


# 5 selected cases — rich multi-mutation data
TEST_CASES: List[Dict[str, Any]] = [
    {
        "name": "polish_extract_long_reformat",
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
        "expected_intent": "EXTRACT_METHOD",
    },
    {
        "name": "polish_const_short_box",
        "code": """public String boxCategory(int length, int width, int height, int mass) {
    boolean bulky = length >= 10000 || width >= 10000 || height >= 10000 || length * width * height >= 1000000000;
    boolean heavy = mass >= 100;
    if (bulky && heavy) return "Both";
    else if (bulky) return "Bulky";
    else if (heavy) return "Heavy";
    else return "Neither";
}""",
        "instruction": "Extract 10000 into BULKY_DIMENSION_THRESHOLD and 100 into HEAVY_MASS_THRESHOLD.",
        "expected_intent": "EXTRACT_CONSTANT",
    },
    {
        "name": "polish_flatten_long_quads",
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
        "expected_intent": "FLATTEN_CONDITIONAL",
    },
    {
        "name": "polish_decompose_long_palindrome",
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
        "expected_intent": "DECOMPOSE_CONDITIONAL",
    },
    {
        "name": "polish_rename_long_paths",
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
        "expected_intent": "RENAME_SYMBOL",
    },
]


class MockDB:
    """In-memory mock for DatabaseManager — no persistence needed."""
    def __init__(self):
        self.sessions = {}
    def create_session(self, id=None, instruction="", original_code=""):
        self.sessions[id] = {"instruction": instruction, "original": original_code, "logs": []}
    def log_status(self, session_id=None, role="", status="", content=None, phase=None, outer_loop=0, inner_loop=0):
        if session_id and session_id in self.sessions:
            self.sessions[session_id]["logs"].append({"role": role, "status": status, "phase": phase})
    def complete_session(self, **kwargs):
        pass
    def mark_as_halted(self, id):
        pass


def extract_timing_from_statuses(statuses) -> Dict[str, Any]:
    """Extract generator timing from status messages."""
    gen_steps = []
    total_ms = 0
    for role, content in statuses:
        text = str(content) if content else ""
        if "Applied" in text and ("ADD_" in text or "MODIFY_" in text or "RENAME_" in text or "All " in text):
            ms = 0
            import re as _re
            m = _re.search(r'(\d+)ms', text)
            if m:
                ms = int(m.group(1))
                total_ms += ms
            gen_steps.append({"msg": text[:150], "ms": ms})
    return {"gen_steps": gen_steps, "total_gen_time_ms": total_ms}


async def run_case(case: Dict[str, Any], results: List[Dict[str, Any]], index: int, total: int, sequential_mode: bool = True) -> None:
    """Run a single case through the orchestrator, capture timing."""
    case_name = case["name"]
    mode_name = "SEQUENTIAL" if sequential_mode else "ONE-SHOT"
    print(f"\n{'='*60}")
    print(f"[{index+1}/{total}] [{mode_name}] {case_name}")
    print(f"Intent: {case['expected_intent']}")
    print(f"Code length: {len(case['code'])} chars")
    print(f"{'='*60}")

    agent = AgentService()
    validator = Validator()
    db = MockDB()

    orch = Orchestrator(agent, validator, db)
    orch.USE_SEQUENTIAL = sequential_mode

    client_id = f"test-seq-{case_name}"

    class MockClient:
        def __init__(self, cid):
            self.id = cid
            self.statuses = []
            self.results = None
            self.insights = None
        async def send_status(self, role, content, **kw):
            self.statuses.append((role, content))
        async def send_result(self, **kwargs):
            self.results = kwargs
        async def send_insights(self, insights):
            self.insights = insights

    client = MockClient(client_id)

    t_start = time.time()
    try:
        await orch.execute_orchestration(client, case["code"], case["instruction"])
        total_duration = int((time.time() - t_start) * 1000)
    except Exception as e:
        total_duration = int((time.time() - t_start) * 1000)
        print(f"ERROR: {e}")

    timing = extract_timing_from_statuses(client.statuses)

    result = {
        "case": case_name,
        "intent": case["expected_intent"],
        "exit_status": getattr(orch.state, 'exit_status', 'N/A').value if hasattr(orch, 'state') else 'N/A',
        "strategy_iter": getattr(orch.state, 'strategy_iter', 'N/A') if hasattr(orch, 'state') else 'N/A',
        "total_duration_ms": total_duration,
        "gen_time_ms": timing["total_gen_time_ms"],
        "gen_steps": timing["gen_steps"],
    }

    if hasattr(orch, 'state') and hasattr(orch.state, 'gen_timings'):
        result["gen_timings_raw"] = [
            {k: v for k, v in e.items()}
            for e in orch.state.gen_timings
        ]
        result["mutation_index"] = orch.state.mutation_index
        result["mutation_queue_len"] = len(orch.state.mutation_queue)

    if client.results:
        result["refactored_code"] = client.results.get("final_code", "")[:100] if client.results.get("final_code") else None

    result["num_statuses"] = len(client.statuses)
    result["key_statuses"] = [
        str(s[1])[:200] for s in client.statuses[-10:]
    ]

    results.append(result)
    print(f"\n--- Result ---")
    print(f"Status: {result['exit_status']}")
    print(f"Total: {total_duration}ms | Gen: {timing['total_gen_time_ms']}ms")
    print(f"Gen steps: {len(timing['gen_steps'])}")
    print(f"{'='*60}\n")

    await agent.unload()


async def run_all(mode_name: str, sequential: bool, output_file: str) -> None:
    """Run all 5 cases with a given mode, save results."""
    print(f"\n\n{'='*70}")
    print(f"RUNNING MODE: {mode_name.upper()}")
    print(f"{'='*70}\n")

    results: List[Dict[str, Any]] = []
    for i, case in enumerate(TEST_CASES):
        await run_case(case, results, i, len(TEST_CASES), sequential_mode=sequential)

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode_name,
        "total_cases": len(results),
        "results": results,
    }

    with open(f"test_results/{output_file}", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print(f"MODE: {mode_name.upper()} — SUMMARY")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['case']:40s} | {r['exit_status']:20s} | {r['total_duration_ms']:6d}ms | gen: {r['gen_time_ms']:6d}ms")
    print(f"{'='*60}")
    print(f"Results saved to test_results/{output_file}")


async def main() -> None:
    os.makedirs("test_results", exist_ok=True)

    await run_all("SEQUENTIAL", sequential=True, output_file="enriched_sequential_results.json")
    await run_all("ONE-SHOT", sequential=False, output_file="enriched_oneshot_results.json")

    print(f"\n\n{'='*70}")
    print("FINAL COMPARISON")
    print(f"{'='*70}")

    with open("test_results/enriched_sequential_results.json") as f:
        seq = json.load(f)
    with open("test_results/enriched_oneshot_results.json") as f:
        one = json.load(f)

    print(f"{'Case':40s} {'Seq Status':20s} {'1S Status':20s} {'Seq Gen':10s} {'1S Gen':10s}")
    print("-" * 100)
    for sr, or_ in zip(seq["results"], one["results"]):
        print(f"{sr['case']:40s} {sr['exit_status']:20s} {or_['exit_status']:20s} {sr.get('gen_time_ms', 0):>8d}ms {or_.get('gen_time_ms', 0):>8d}ms")
    print(f"\nComparison saved to test_results/enriched_comparison.md")


if __name__ == "__main__":
    asyncio.run(main())
