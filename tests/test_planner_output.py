"""Isolated planner output test — runs only Phase 2 (classifier + architect)."""
import asyncio
import json
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, ".")

import yaml
from llama_cpp import ChatCompletionRequestMessage

from app.modules.agent_service import AgentService
from app.utils.paths import MODELS_CONFIG_PATH, PROMPTS_CONFIG_PATH
from app.utils.response_parser import ResponseParser
from app.utils.schemas import (
    ArchitectAnalysisResponse,
    ASTArchitectResponse,
    IntentClassifierResponse,
)


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
        "expected_intent": "EXTRACT_METHOD",
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
        "expected_intent": "EXTRACT_CONSTANT",
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
        "expected_intent": "FLATTEN_CONDITIONAL",
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
        "expected_intent": "DECOMPOSE_CONDITIONAL",
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
        "expected_intent": "RENAME_SYMBOL",
    },
]


def load_configs():
    with open(MODELS_CONFIG_PATH) as f:
        model_config = yaml.safe_load(f)
    with open(PROMPTS_CONFIG_PATH) as f:
        prompts = yaml.safe_load(f)
    return model_config, prompts


async def test_planner_case(
    agent: AgentService,
    prompts: Dict,
    case: Dict[str, Any],
) -> Dict[str, Any]:
    case_name = case["name"]
    code = case["code"]
    instruction = case["instruction"]

    result = {"case": case_name, "expected_intent": case["expected_intent"]}

    # --- Step 1: Classifier ---
    prompt = f"<code>{code}</code>\n<instruction>{instruction}</instruction>"
    messages: List[ChatCompletionRequestMessage] = [
        {"role": "system", "content": prompts["planner"]["classifier"]},
        {"role": "user", "content": prompt},
    ]

    t0 = time.time()
    try:
        raw = await agent.generate(
            messages, temp=0.1, max_tokens=500, response_model=IntentClassifierResponse
        )
        classifier_text = raw["choices"][0]["message"].get("content") or ""
        cls_tokens = raw["usage"]["completion_tokens"]
        classifier_res = ResponseParser.extract_json(classifier_text, IntentClassifierResponse)
        intent_packet = classifier_res.intent_packet.model_dump()
        classifier_ok = True
        classifier_error = None
    except Exception as e:
        classifier_ok = False
        classifier_error = str(e)[:200]
        classifier_text = ""
        cls_tokens = 0
        intent_packet = None

    result["classifier_ok"] = classifier_ok
    result["classifier_error"] = classifier_error
    result["classifier_tokens"] = cls_tokens

    if not classifier_ok or not intent_packet:
        return result

    await agent.clear_context()

    # --- Step 2: Architect Analysis ---
    analysis_prompt = (
        f"Intent Packet: {json.dumps(intent_packet)}\n"
        f"User Instruction: {instruction}\n"
        f"Code: <code>{code}</code>"
    )
    system_content = prompts["planner"]["architect_analysis"]
    intent_key = intent_packet.get("specific_intent", "")
    guidance = prompts["planner"]["analysis_guidance"].get(intent_key, "")
    if guidance:
        system_content += "\n" + guidance

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": analysis_prompt},
    ]

    try:
        raw = await agent.generate(
            messages, temp=0.1, max_tokens=1024, response_model=ArchitectAnalysisResponse
        )
        analysis_text = raw["choices"][0]["message"].get("content") or ""
        analysis_tokens = raw["usage"]["completion_tokens"]
        analysis_model = ResponseParser.extract_json(analysis_text, ArchitectAnalysisResponse)
        analysis = analysis_model.model_dump()
        analysis_ok = True
        analysis_error = None
    except Exception as e:
        analysis_ok = False
        analysis_error = str(e)[:200]
        analysis_text = ""
        analysis_tokens = 0
        analysis = None

    result["analysis_ok"] = analysis_ok
    result["analysis_error"] = analysis_error
    result["analysis_tokens"] = analysis_tokens

    if not analysis:
        result["time_ms"] = int((time.time() - t0) * 1000)
        return result

    await agent.clear_context()

    # --- Step 3: Architect Synthesis (THE CRITICAL ONE) ---
    arch_prompt = (
        f"Analysis: {json.dumps(analysis)}\n"
        f"Intent: {json.dumps(intent_packet)}\n"
        f"Instruction: {instruction}\n"
        f"Code: <code>{code}</code>"
    )
    system_content = prompts["planner"]["architect"]
    guidance = prompts["planner"]["synthesis_guidance"].get(intent_key, "")
    if guidance:
        system_content += "\n" + guidance

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": arch_prompt},
    ]

    raw_synthesis = None
    try:
        raw = await agent.generate(
            messages, temp=0.2, max_tokens=2048, response_model=ASTArchitectResponse
        )
        arch_text = raw["choices"][0]["message"].get("content") or ""
        arch_tokens = raw["usage"]["completion_tokens"]
        raw_synthesis = arch_text
        result["arch_raw_length"] = len(arch_text)

        # Parse
        parse_t0 = time.time()
        try:
            arch_res = ResponseParser.extract_json(arch_text, ASTArchitectResponse)
            plan = arch_res.ast_modification_plan.model_dump()
            mutations = plan.get("ast_mutations", [])
            parse_ok = True
            parse_error = None
            parse_time_ms = int((time.time() - parse_t0) * 1000)
        except Exception as e:
            parse_ok = False
            parse_error = str(e)[:300]
            mutations = []
            parse_time_ms = int((time.time() - parse_t0) * 1000)

        result["parse_ok"] = parse_ok
        result["parse_error"] = parse_error
        result["parse_time_ms"] = parse_time_ms
        result["raw_mutation_count"] = len(mutations)
        result["arch_tokens"] = arch_tokens

        # Check for truncation (EOF mid-array)
        if "EOF while parsing" in (parse_error or ""):
            result["truncated"] = True
        else:
            result["truncated"] = False

        # Check for repetition
        if mutations:
            seen = set()
            repeats = 0
            for m in mutations:
                key = (m.get("action"), m.get("target"))
                if key in seen:
                    repeats += 1
                else:
                    seen.add(key)
            result["repeated_mutations"] = repeats
            result["unique_mutations"] = len(seen)
            result["mutations_capped"] = len(mutations) > 8
        else:
            result["repeated_mutations"] = 0
            result["unique_mutations"] = 0
            result["mutations_capped"] = False

        # Actions breakdown
        actions = {}
        for m in mutations:
            action = m.get("action", "?")
            actions[action] = actions.get(action, 0) + 1
        result["action_breakdown"] = actions

    except Exception as e:
        result["parse_ok"] = False
        result["parse_error"] = str(e)[:300]
        result["arch_tokens"] = 0
        result["raw_mutation_count"] = 0
        result["truncated"] = "truncat" in str(e).lower() or "EOF" in str(e)
        result["repeated_mutations"] = 0
        result["unique_mutations"] = 0
        result["mutations_capped"] = False
        result["action_breakdown"] = {}

    if raw_synthesis:
        result["arch_preview"] = raw_synthesis[:500]

    result["time_ms"] = int((time.time() - t0) * 1000)
    return result


async def main() -> None:
    import os
    os.makedirs("test_results", exist_ok=True)

    model_config, prompts = load_configs()
    agent = AgentService()

    print(f"\n{'='*60}")
    print("Planner-Only Output Test")
    print(f"Model: {model_config['planner']['filename']}")
    print(f"{'='*60}")

    await agent.load(model_config["planner"])

    all_results = []
    for i, case in enumerate(TEST_CASES):
        print(f"\n--- [{i+1}/{len(TEST_CASES)}] {case['name']} ---")
        result = await test_planner_case(agent, prompts, case)
        all_results.append(result)

        status = "PASS" if result.get("parse_ok") else "FAIL"
        prefix = "  TRUNCATED!" if result.get("truncated") else ""
        print(f"  Classifier: {'OK' if result.get('classifier_ok') else 'FAIL'}")
        print(f"  Analysis:   {'OK' if result.get('analysis_ok') else 'FAIL'}")
        print(f"  Synthesis:  {status} {prefix}")
        print(f"  Mutations:  {result.get('raw_mutation_count', '?')} raw, "
              f"{result.get('unique_mutations', '?')} unique, "
              f"{result.get('repeated_mutations', '?')} repeats")
        print(f"  Tokens:     arch={result.get('arch_tokens', '?')}, "
              f"total_time={result.get('time_ms', '?')}ms")
        if result.get("parse_error"):
            print(f"  Error: {result['parse_error']}")
        if result.get("action_breakdown"):
            print(f"  Actions:    {result['action_breakdown']}")
        print()

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model_config["planner"]["filename"],
        "total_cases": len(all_results),
        "results": all_results,
    }
    with open("test_results/planner_output_check.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in all_results:
        print(f"  {r['case']:25s} | "
              f"Class={'OK' if r.get('classifier_ok') else 'FAIL':4s} | "
              f"Synth={'OK' if r.get('parse_ok') else 'FAIL':4s} | "
              f"Mut={r.get('raw_mutation_count', 0):2d} raw, "
              f"{r.get('unique_mutations', 0):2d} uniq | "
              f"Time={r.get('time_ms', 0):5d}ms")
    print(f"\nResults saved to test_results/planner_output_check.json")

    await agent.unload()


if __name__ == "__main__":
    asyncio.run(main())
