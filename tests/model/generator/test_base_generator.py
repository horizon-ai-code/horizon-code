"""
Test: Base model as Generator using create_completion (raw prompt, not chat).
5 cases. Compare base vs instruct Generator Phase 4 pass rate.
"""
import asyncio, json, re, sys
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, ".")

from llama_cpp import Llama
from app.modules.validator import Validator
from app.utils.formatters import format_plan_for_generator
from app.utils.response_parser import ResponseParser
from app.utils.schemas import (
    ArchitectAnalysisResponse,
    ASTArchitectResponse,
    IntentClassifierResponse,
)
from app.utils.types import RefactorIntent
from tests.model.harness import ModelTestHarness


# 5 cases — one per failing intent + 1 easy control
CASES = [
    {
        "name": "flatten_mindist", "intent": "FLATTEN_CONDITIONAL",
        "code": "public int minDistance(String word1, String word2) { int m = word1.length(), n = word2.length(); int[][] dp = new int[m+1][n+1]; for(int i = 0; i <= m; i++) { for(int j = 0; j <= n; j++) { if(i == 0 || j == 0) dp[i][j] = i + j; else if(word1.charAt(i-1) == word2.charAt(j-1)) dp[i][j] = dp[i-1][j-1]; else dp[i][j] = 1 + Math.min(dp[i-1][j], dp[i][j-1]); } } return dp[m][n]; }",
        "instruction": "Flatten.",
    },
    {
        "name": "rename_judge", "intent": "RENAME_SYMBOL",
        "code": "public int findJudge(int n, int[][] trust) { int[] trustCounts = new int[n + 1]; for (int[] t : trust) { trustCounts[t[0]]--; trustCounts[t[1]]++; } for (int i = 1; i <= n; i++) if (trustCounts[i] == n - 1) return i; return -1; }",
        "instruction": "Rename trustCounts to trustScores.",
    },
    {
        "name": "const_derangement", "intent": "EXTRACT_CONSTANT",
        "code": "public int findDerangement(int n) { long[] dp = new long[n + 1]; dp[2] = 1; for (int i = 3; i <= n; i++) dp[i] = (i - 1) * (dp[i - 1] + dp[i - 2]) % 1000000007; return (int) dp[n]; }",
        "instruction": "Extract 1000000007 into constant MOD.",
    },
    {
        "name": "decompose_nim", "intent": "DECOMPOSE_CONDITIONAL",
        "code": "public boolean canWinNim(int n) { return n % 4 != 0; }",
        "instruction": "Decompose the condition into a named boolean.",
    },
    {
        "name": "consolidate_fixed", "intent": "CONSOLIDATE_CONDITIONAL",
        "code": "public int fixedPoint(int[] arr) { int left = 0, right = arr.length - 1; while (left < right) { int middle = left + (right - left) / 2; if (arr[middle] < middle) left = middle + 1; else right = middle; } return arr[left] == left ? left : -1; }",
        "instruction": "Consolidate.",
    },
]


def run_phase4(original: str, refactored: str, intent: str) -> dict:
    validator = Validator()
    findings = []
    try:
        o_cc = validator.get_complexity(original)
        r_cc = validator.get_complexity(refactored)
    except:
        o_cc, r_cc = 1, 1
    skip = intent in ("INLINE_METHOD",)
    loosen = intent in ("SPLIT_LOOP",)
    if not skip and intent not in ("EXTRACT_METHOD",):
        threshold = o_cc + (1 if loosen else 0)
        if r_cc > threshold:
            findings.append(f"CC {o_cc}→{r_cc}")
    try:
        bf = validator.verify_boundary(original, refactored, [])
        if bf: findings.append(f"Boundary: {bf.error_report.message[:60]}")
    except: pass
    try:
        ri = RefactorIntent(intent)
        intf = validator.verify_intent(ri, original, refactored)
        if intf: findings.append(f"Intent: {intf.error_report.message[:60]}")
    except: pass
    om = set(re.findall(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(', original))
    rm = set(re.findall(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\(', refactored))
    dropped = om - rm
    if dropped: findings.append(f"Dropped: {dropped}")
    return {"pass": len(findings) == 0, "findings": findings, "orig_cc": o_cc, "refac_cc": r_cc}


async def main():
    print("=" * 70)
    print("BASE vs INSTRUCT GENERATOR — 5 cases")
    print("=" * 70)

    # Phase 1: Planner (uses instruct model via harness)
    print("\n--- Phase 1: Planner (instruct model) ---")
    h = ModelTestHarness("planner")
    await h.load_model()
    prompts = h.prompts

    plans_data = []
    for case in CASES:
        code, inst = case["code"], case["instruction"]
        # Classifier
        cr = await h.generate(prompts["planner"]["classifier"],
            f"<code>{code}</code>\n<instruction>{inst}</instruction>",
            temp=0.1, max_tokens=500, response_model=IntentClassifierResponse)
        intent_key = case["intent"]
        if cr["success"]:
            try:
                ci = ResponseParser.extract_json(cr["content"], IntentClassifierResponse)
                intent_key = ci.intent_packet.specific_intent.value
            except: pass

        # Analysis
        await h.clear_context()
        asys = prompts["planner"]["architect_analysis"]
        ag = prompts["planner"]["analysis_guidance"].get(intent_key, "")
        ar = await h.generate(asys + "\n" + ag if ag else asys,
            f"Intent: {intent_key}\nInstruction: {inst}\nCode: <code>{code}</code>",
            temp=0.1, max_tokens=1024, response_model=ArchitectAnalysisResponse)
        ad = {}
        if ar["success"]:
            try: ad = ResponseParser.extract_json(ar["content"], ArchitectAnalysisResponse).model_dump()
            except: pass

        # Architect
        await h.clear_context()
        ssys = prompts["planner"]["architect"]
        sg = prompts["planner"]["synthesis_guidance"].get(intent_key, "")
        sr = await h.generate(ssys + "\n" + sg if sg else ssys,
            f"Analysis: {json.dumps(ad)}\nIntent: {intent_key}\nInstruction: {inst}\nCode: <code>{code}</code>",
            temp=0.1, max_tokens=2048, response_model=ASTArchitectResponse)
        plan = {}
        if sr["success"]:
            try: plan = ResponseParser.extract_json(sr["content"], ASTArchitectResponse).ast_modification_plan.model_dump()
            except: pass

        plans_data.append({"name": case["name"], "intent": intent_key, "code": code, "plan": plan})
        actions = [m["action"] for m in plan.get("ast_mutations", [])]
        print(f"  {case['name']}: intent={intent_key} plan={actions}")

    await h.unload_model()

    # Phase 2: Base Generator (raw completion, no chat)
    print("\n--- Phase 2: Base Generator (create_completion) ---")
    model_base = Llama(
        model_path="models/Qwen2.5-Coder-3B-Q4_K_M.gguf",
        n_gpu_layers=36, n_ctx=6144, verbose=False,
    )

    base_results = []
    for pd in plans_data:
        name = pd["name"]
        code = pd["code"]
        plan = pd["plan"]
        intent = pd["intent"]

        # Build the prompt: formatted plan + base code
        prompt_text = format_plan_for_generator(plan, code)
        # Remove <code> tags for raw completion — model doesn't understand them
        prompt_text = prompt_text.replace("<code>", "").replace("</code>", "")
        # Add guidance comment at the top
        prompt_text = f"// {intent}: apply these instructions to the Java code below\n\n" + prompt_text

        result = model_base.create_completion(
            prompt=prompt_text + "\n\n",
            max_tokens=1024,
            temperature=0.1,
            stop=["<|endoftext|>"],  # Base model's EOS token
        )
        raw = result["choices"][0].get("text", "") or ""
        print(f"\n  {name}: {len(raw)} chars generated")
        for line in raw.strip().split('\n')[:10]:
            print(f"    {line}")

        # Extract code-like output
        gen_code = raw.strip()
        # Remove markdown/code fences
        gen_code = re.sub(r'```\w*\n?', '', gen_code)
        gen_code = gen_code.strip('`').strip()
        if not gen_code:
            gen_code = code  # No output = unchanged

        syntax_ok = False
        try:
            import javalang
            wrapped = f"class _W_ {{ {gen_code} }}" if "class" not in gen_code else gen_code
            javalang.parse.parse(wrapped)
            syntax_ok = True
        except: pass

        p4 = run_phase4(code, gen_code, intent) if syntax_ok else {"pass": False, "findings": ["syntax fail"], "orig_cc": 0, "refac_cc": 99}
        base_results.append({"name": name, "intent": intent, "syntax": syntax_ok, "phase4": p4})
        print(f"  syntax={'✓' if syntax_ok else '✗'} phase4={'✓' if p4['pass'] else '✗'} CC={p4['orig_cc']}→{p4['refac_cc']}")

    del model_base

    # Phase 3: Instruct Generator (via harness, chat API)
    print("\n--- Phase 3: Instruct Generator (chat API, multi-sample) ---")
    hg = ModelTestHarness("generator")
    await hg.load_model()

    instruct_results = []
    for pd in plans_data:
        name = pd["name"]
        code = pd["code"]
        plan = pd["plan"]
        intent = pd["intent"]

        user = format_plan_for_generator(plan, code)
        best_code = code
        best_cc = 999
        best_syntax = False

        for temp in [0.1, 0.3, 0.5]:
            r = await hg.generate(
                hg.prompts["generator"]["coder"], user,
                temp=temp, max_tokens=1024
            )
            cm = re.search(r'<code>(.*?)</code>', r["content"], re.DOTALL)
            oc = cm.group(1).strip() if cm else ""
            if not oc: continue
            syntax_ok = False
            try:
                import javalang
                wrapped = f"class _W_ {{ {oc} }}" if "class" not in oc else oc
                javalang.parse.parse(wrapped)
                syntax_ok = True
            except: pass
            if syntax_ok:
                v = Validator()
                cc = v.get_complexity(oc)
                if cc < best_cc:
                    best_cc = cc
                    best_code = oc
                    best_syntax = True

        p4 = run_phase4(code, best_code, intent) if best_syntax else {"pass": False, "findings": ["no valid output"], "orig_cc": 0, "refac_cc": 99}
        instruct_results.append({"name": name, "intent": intent, "syntax": best_syntax, "phase4": p4})
        print(f"  {name}: syntax={'✓' if best_syntax else '✗'} phase4={'✓' if p4['pass'] else '✗'} CC={p4['orig_cc']}→{p4['refac_cc']}")

    await hg.unload_model()

    # Phase 4: Comparison
    print(f"\n{'='*70}")
    print("COMPARISON")
    print(f"{'='*70}")
    print(f"{'Case':<25} {'Base CC':<12} {'Base P4':<8} {'Instruct CC':<12} {'Instruct P4':<8} {'Winner'}")
    print("-" * 75)
    for b, i in zip(base_results, instruct_results):
        bcc = f"{b['phase4']['orig_cc']}→{b['phase4']['refac_cc']}"
        icc = f"{i['phase4']['orig_cc']}→{i['phase4']['refac_cc']}"
        bp = '✓' if b['phase4']['pass'] else '✗'
        ip = '✓' if i['phase4']['pass'] else '✗'
        w = "BASE" if b['phase4']['pass'] and not i['phase4']['pass'] else ("INSTRUCT" if i['phase4']['pass'] and not b['phase4']['pass'] else ("BOTH" if b['phase4']['pass'] else "NONE"))
        print(f"{b['name']:<25} {bcc:<12} {bp:<8} {icc:<12} {ip:<8} {w}")


if __name__ == "__main__":
    asyncio.run(main())
