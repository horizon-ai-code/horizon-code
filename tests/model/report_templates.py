from datetime import datetime
from typing import Any, Dict, List


def build_report(role: str, results: List[Dict]) -> str:
    if role == "planner":
        return _build_planner_report(results)
    elif role == "judge":
        return _build_judge_report(results)
    elif role == "generator":
        return _build_generator_report(results)
    raise ValueError(f"Unknown role: {role}")


def _build_planner_report(results: List[Dict]) -> str:
    now = datetime.now().isoformat()
    total = len(results)
    passed = sum(1 for r in results if r.get("verdict") == "PASS")

    intent_acc = sum(1 for r in results if r.get("intent_correct", False))
    scope_ok = sum(1 for r in results if r.get("scope_valid", False))
    analysis_ok = sum(1 for r in results if r.get("analysis_complete", False))
    plan_ok = sum(1 for r in results if r.get("plan_executable", False))
    hallucinations = sum(len(r.get("hallucinations", [])) for r in results)
    coherence = sum(1 for r in results if r.get("coherent", False))

    lines = [
        "# Planner Isolated Reasoning Report",
        "",
        f"**Date:** {now}",
        "**Model:** Qwen2.5-Coder-3B-Instruct",
        f"**Cases:** {total} code+instruction pairs",
        f"**Calls:** {total * 3} (3 model calls per case: classifier → analysis → synthesis)",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|--------|--------|",
        f"| Total cases | {total} |",
        f"| Classifier accuracy (intent matches expected) | {intent_acc}/{total} |",
        f"| Scope anchor validity (member+class exist in AST) | {scope_ok}/{total} |",
        f"| Analysis completeness (targets+preserve captured) | {analysis_ok}/{total} |",
        f"| Plan executability (mutations reference real targets) | {plan_ok}/{total} |",
        f"| Hallucination rate (invented names in plan) | {hallucinations} hallucinations |",
        f"| Analysis→Plan coherence (plan references analysis items) | {coherence}/{total} |",
        "",
        "---",
        "",
        "## By Intent",
        "",
        "| Intent | Cases | Class Acc | Scope | Analysis | Plan | Hallucinations |",
        "|--------|-------|-----------|-------|----------|------|----------------|",
    ]

    intents: Dict[str, List[Dict]] = {}
    for r in results:
        name = r.get("expected_intent", "UNKNOWN")
        intents.setdefault(name, []).append(r)

    for intent, cases in intents.items():
        n = len(cases)
        ic = sum(1 for r in cases if r.get("intent_correct"))
        sc = sum(1 for r in cases if r.get("scope_valid"))
        an = sum(1 for r in cases if r.get("analysis_complete"))
        pl = sum(1 for r in cases if r.get("plan_executable"))
        hal = sum(len(r.get("hallucinations", [])) for r in cases)
        lines.append(f"| {intent} | {n} | {ic}/{n} | {sc}/{n} | {an}/{n} | {pl}/{n} | {hal} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Detailed Results",
            "",
        ]
    )

    for i, r in enumerate(results):
        verdict = r.get("verdict", "FAIL")
        name = r.get("name", f"case_{i}")
        lines.append(f"### Case {i+1}: {name} ({verdict})")
        lines.append("")
        lines.append(f"- **Input:** code ({r.get('code_len', '?')} chars) + instruction \"{r.get('instruction_short', '')}\"")
        lines.append(f"- **Expected intent:** {r.get('expected_intent', 'N/A')}")
        lines.append(f"- **Classifier output:** {r.get('actual_intent', '?')} {_mark(r.get('intent_correct'))}")
        lines.append(f"- **Scope anchor:** {r.get('scope_detail', '?')}")
        lines.append(f"- **Analysis targets:** {r.get('targets', '?')}")
        lines.append(f"- **Analysis must_preserve:** {r.get('must_preserve', '?')}")
        lines.append(f"- **Plan mutations:** {r.get('mutation_count', 0)} mutations")
        lines.append(f"- **Hallucinations:** {', '.join(r.get('hallucinations', [])) or 'None'}")
        lines.append(f"- **Coherence:** Analysis→Plan {r.get('coherence_detail', '?')}")
        lines.append(f"- **Duration:** {r.get('duration', '?')}s")
        lines.append(f"- **Verdict:** {verdict}")
        lines.append("")
        lines.append("#### What happened")
        lines.append(r.get("what_happened", "N/A"))
        lines.append("")
        lines.append("#### Why this likely happened")
        lines.append(r.get("why", "N/A"))
        lines.append("")
        lines.append("#### Raw output")
        lines.append("```json")
        lines.append(json.dumps(r.get("raw_output", {}), indent=2, default=str))
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Cross-Case Analysis",
            "",
            "### Planner succeeds reliably when:",
            "",
            "| Pattern | Pass rate | Cases |",
            "|---------|-----------|-------|",
        ]
    )

    for label, condition in _planner_patterns(results):
        matches = [r for r in results if condition(r)]
        rate = (
            f"{sum(1 for r in matches if r.get('verdict') == 'PASS')}/{len(matches)}"
            if matches
            else "N/A"
        )
        lines.append(f"| {label} | {rate} | {', '.join(r.get('name', str(i)) for i, r in enumerate(results) if r in matches)} |")

    lines.extend(
        [
            "",
            "### Planner struggles when:",
            "",
            "| Pattern | Pass rate | Cases |",
            "|---------|-----------|-------|",
        ]
    )

    for label, condition in _planner_struggles(results):
        matches = [r for r in results if condition(r)]
        rate = (
            f"{sum(1 for r in matches if r.get('verdict') == 'PASS')}/{len(matches)}"
            if matches
            else "N/A"
        )
        lines.append(f"| {label} | {rate} | {', '.join(r.get('name', str(i)) for i, r in enumerate(results) if r in matches)} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Raw Data",
            "",
            f"Full results as JSON saved to: `tests/results/planner_isolated_results.json`",
        ]
    )

    return "\n".join(lines)


def _build_judge_report(results: List[Dict]) -> str:
    now = datetime.now().isoformat()

    runs = []
    for r in results:
        for run in r.get("runs", []):
            run["case_name"] = r.get("name", "")
            run["expected"] = r.get("expected_verdict", "")
            runs.append(run)

    total_runs = len(runs)
    if total_runs == 0:
        return "# Judge Isolated Reasoning Report\n\nNo results."

    correct = sum(1 for run in runs if run.get("verdict") == run.get("expected"))
    accept_expected = [run for run in runs if run.get("expected") == "ACCEPT"]
    revise_expected = [run for run in runs if run.get("expected") == "REVISE"]
    false_accept = sum(1 for run in revise_expected if run.get("verdict") == "ACCEPT")
    false_revise = sum(1 for run in accept_expected if run.get("verdict") == "REVISE")

    unanimous = 0
    split = 0
    for r in results:
        verdicts = [run.get("verdict") for run in r.get("runs", [])]
        if len(set(verdicts)) == 1:
            unanimous += 1
        elif 2 <= max(verdicts.count(v) for v in set(verdicts)) <= 3:
            split += 1

    avg_scratch = (
        sum(len(run.get("scratchpad", "")) for run in runs) / total_runs
        if total_runs
        else 0
    )
    avg_issues = (
        sum(len(run.get("issues", [])) for run in runs) / total_runs if total_runs else 0
    )

    lines = [
        "# Judge Isolated Reasoning Report",
        "",
        f"**Date:** {now}",
        "**Model:** Llama-3.2-3B-Instruct",
        f"**Cases:** {len(results)} cases × 5 runs = {total_runs} calls",
        "**Design:** 5 ACCEPT-expected + 5 REVISE-expected, each run 5× for consistency",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|--------|--------|",
        f"| Total runs | {total_runs} |",
        f"| Correct verdict (matches expected) | {correct}/{total_runs} ({_pct(correct, total_runs)}) |",
        f"| False ACCEPT rate (REVISE-expected but ACCEPT) | {false_accept}/{len(revise_expected)} |",
        f"| False REVISE rate (ACCEPT-expected but REVISE) | {false_revise}/{len(accept_expected)} |",
        f"| Accuracy on ACCEPT-expected cases | {len(accept_expected) - false_revise}/{len(accept_expected)} |",
        f"| Accuracy on REVISE-expected cases | {len(revise_expected) - false_accept}/{len(revise_expected)} |",
        f"| Unanimous cases (5/5 same verdict) | {unanimous}/{len(results)} |",
        f"| Volatile cases (3-2 split) | {split}/{len(results)} |",
        f"| Avg scratchpad length | {avg_scratch:.0f} chars |",
        f"| Avg issues count | {avg_issues:.1f} |",
        "",
        "---",
        "",
        "## Per-Case Detail",
        "",
    ]

    for i, r in enumerate(results):
        name = r.get("name", f"case_{i}")
        expected = r.get("expected_verdict", "?")
        case_runs = r.get("runs", [])
        verdicts_list = [run.get("verdict", "?") for run in case_runs]

        if case_runs:
            acc = sum(1 for run in case_runs if run.get("verdict") == run.get("expected"))
            if len(set(verdicts_list)) == 1:
                consistency = "unanimous"
            elif max(verdicts_list.count(v) for v in set(verdicts_list)) >= 4:
                consistency = "4-1 split"
            elif max(verdicts_list.count(v) for v in set(verdicts_list)) >= 3:
                consistency = "3-2 split"
            else:
                consistency = "scattered"
        else:
            acc = 0
            consistency = "no results"

        lines.append(f"### Case {i+1}: {name} (expected: {expected})")
        lines.append("")
        lines.append("| Run | Verdict | Issues | Scratchpad len | Duration |")
        lines.append("|-----|---------|--------|----------------|----------|")
        for j, run in enumerate(case_runs):
            issues_str = run.get("issues", "")
            if isinstance(issues_str, list):
                issues_str = ", ".join(str(x) for x in issues_str[:2])
            lines.append(
                f"| {j+1} | {run.get('verdict', '?')} | \"{str(issues_str)[:80]}\" | {len(run.get('scratchpad', ''))} | {run.get('duration', '?')}s |"
            )
        lines.append(f"- **Accuracy:** {acc}/{len(case_runs)}")
        lines.append(f"- **Consistency:** {consistency}")
        lines.append(f"- **Raw verdicts:** `{verdicts_list}`")
        lines.append("")
        lines.append("#### What happened")
        lines.append(r.get("what_happened", "N/A"))
        lines.append("")
        lines.append("#### Why this likely happened")
        lines.append(r.get("why", "N/A"))
        lines.append("")
        lines.append("#### Raw output per run")
        lines.append("```json")
        lines.append(json.dumps([{"run": j+1, "content": run.get("raw_content", "")} for j, run in enumerate(case_runs)], indent=2, default=str))
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Cross-Case Analysis",
            "",
            "### When Judge is reliable",
            "",
            "| Pattern | Accuracy | Cases |",
            "|---------|----------|-------|",
        ]
    )

    for label, condition in _judge_patterns(results):
        cases_hit = []
        hits = 0
        total = 0
        for r in results:
            for run in r.get("runs", []):
                if condition(run):
                    total += 1
                    if run.get("verdict") == run.get("expected"):
                        hits += 1
            if any(condition(run) for run in r.get("runs", [])):
                cases_hit.append(r.get("name", "?"))
        rate = f"{_pct(hits, total)}" if total else "N/A"
        lines.append(f"| {label} | {rate} | {', '.join(set(cases_hit))} |")

    lines.extend(
        [
            "",
            "### When Judge is unreliable",
            "",
            "| Pattern | Accuracy | Cases |",
            "|---------|----------|-------|",
        ]
    )

    for label, condition in _judge_struggles(results):
        cases_hit = []
        hits = 0
        total = 0
        for r in results:
            for run in r.get("runs", []):
                if condition(run):
                    total += 1
                    if run.get("verdict") == run.get("expected"):
                        hits += 1
            if any(condition(run) for run in r.get("runs", [])):
                cases_hit.append(r.get("name", "?"))
        rate = f"{_pct(hits, total)}" if total else "N/A"
        lines.append(f"| {label} | {rate} | {', '.join(set(cases_hit))} |")

    lines.extend(
        [
            "",
            "### Scratchpad length vs accuracy",
            "",
            "| Scratchpad | Runs | Accuracy |",
            "|-----------|------|----------|",
        ]
    )

    short = [run for run in runs if len(run.get("scratchpad", "")) < 100]
    mid = [run for run in runs if 100 <= len(run.get("scratchpad", "")) <= 200]
    long = [run for run in runs if len(run.get("scratchpad", "")) > 200]

    for label, subset in [("< 100 chars", short), ("100-200 chars", mid), ("> 200 chars", long)]:
        if subset:
            acc = sum(1 for r in subset if r["verdict"] == r["expected"])
            lines.append(f"| {label} | {len(subset)} | {_pct(acc, len(subset))} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Raw Data",
            "",
            f"Full results as JSON saved to: `tests/results/judge_isolated_results.json`",
        ]
    )

    return "\n".join(lines)


def _build_generator_report(results: List[Dict]) -> str:
    now = datetime.now().isoformat()
    total = len(results)
    real = [r for r in results if not r.get("bad_plan", False)]
    stress = [r for r in results if r.get("bad_plan", False)]

    syntax_pass = sum(1 for r in results if r.get("syntax_valid"))
    compliance = sum(1 for r in real if r.get("compliance_pass"))
    planned_present = sum(r.get("planned_present", 0) for r in real)
    planned_expected = sum(r.get("planned_total", 0) for r in real)
    anti = sum(1 for r in real if r.get("anti_pattern_count", 0) > 0)
    bad_ok = sum(1 for r in stress if r.get("graceful", False))

    lines = [
        "# Generator Isolated Reasoning Report",
        "",
        f"**Date:** {now}",
        "**Model:** Qwen2.5-Coder-3B-Instruct",
        f"**Cases:** {total} ({len(real)} real plans + {len(stress)} bad-plan stress tests)",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|--------|--------|",
        f"| Total cases | {total} |",
        f"| Syntax pass rate | {syntax_pass}/{total} ({_pct(syntax_pass, total)}) |",
        f"| Plan compliance rate (real cases) | {compliance}/{len(real)} |",
        f"| Planned elements present (total / total expected) | {planned_present} / {planned_expected} |",
        f"| Anti-pattern violation rate (real cases) | {anti}/{len(real)} |",
        f"| Bad-plan graceful handling | {bad_ok}/{len(stress)} |",
        "",
        "---",
        "",
        "## By Intent",
        "",
        "| Intent | Cases | Syntax | Compliance | Anti-patterns |",
        "|--------|-------|--------|------------|---------------|",
    ]

    intents: Dict[str, List[Dict]] = {}
    for r in real:
        name = r.get("intent", "UNKNOWN")
        intents.setdefault(name, []).append(r)

    for intent, cases in intents.items():
        n = len(cases)
        sx = sum(1 for r in cases if r.get("syntax_valid"))
        cp = sum(1 for r in cases if r.get("compliance_pass"))
        ap = sum(1 for r in cases if r.get("anti_pattern_count", 0) > 0)
        lines.append(f"| {intent} | {n} | {sx}/{n} | {cp}/{n} | {ap}/{n} |")

    lines.extend(
        [
            f"| Bad-plan stress | {len(stress)} | {sum(1 for r in stress if r.get('syntax_valid'))}/{len(stress)} | N/A | N/A |",
            "",
            "---",
            "",
            "## Detailed Results",
            "",
        ]
    )

    for i, r in enumerate(results):
        verdict = r.get("verdict", "FAIL")
        name = r.get("name", f"case_{i}")
        lines.append(f"### Case {i+1}: {name} ({verdict})")
        lines.append("")
        lines.append(f"- **Input:** code ({r.get('code_len', '?')} chars) + plan with {r.get('mutation_count', 0)} mutations")
        lines.append(f"- **Syntax:** {'Valid' if r.get('syntax_valid') else 'Invalid'} {_mark(r.get('syntax_valid'))}")
        lines.append(f"- **Planned elements:** {r.get('planned_present', 0)}/{r.get('planned_total', 0)} present")
        for detail in r.get("planned_details", []):
            lines.append(f"  - {detail}")
        anti_count = r.get("anti_pattern_count", 0)
        ap_text = ", ".join(r.get("anti_patterns", [])) if anti_count > 0 else "None"
        lines.append(f"- **Anti-pattern violations:** {ap_text} {_mark(anti_count == 0)}")
        lines.append(f"- **Duration:** {r.get('duration', '?')}s")
        lines.append(f"- **Verdict:** {verdict}")
        lines.append("")
        lines.append("#### What happened")
        lines.append(r.get("what_happened", "N/A"))
        lines.append("")
        lines.append("#### Why this likely happened")
        lines.append(r.get("why", "N/A"))
        lines.append("")
        lines.append("#### Plan fed to Generator")
        lines.append("```json")
        lines.append(json.dumps(r.get("plan", {}), indent=2, default=str))
        lines.append("```")
        lines.append("")
        lines.append("#### Generated output")
        lines.append("```java")
        lines.append(r.get("output_code", "N/A"))
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Cross-Case Analysis",
            "",
            "### Generator succeeds reliably when:",
            "",
            "| Pattern | Pass rate | Cases |",
            "|---------|-----------|-------|",
        ]
    )

    for label, condition in _generator_patterns(results):
        matches = [r for r in results if condition(r)]
        rate = (
            f"{sum(1 for r in matches if r.get('verdict') == 'PASS')}/{len(matches)}"
            if matches
            else "N/A"
        )
        lines.append(f"| {label} | {rate} | {', '.join(r.get('name', str(i)) for i, r in enumerate(results) if r in matches)} |")

    lines.extend(
        [
            "",
            "### Generator struggles when:",
            "",
            "| Pattern | Pass rate | Cases |",
            "|---------|-----------|-------|",
        ]
    )

    for label, condition in _generator_struggles(results):
        matches = [r for r in results if condition(r)]
        rate = (
            f"{sum(1 for r in matches if r.get('verdict') == 'PASS')}/{len(matches)}"
            if matches
            else "N/A"
        )
        lines.append(f"| {label} | {rate} | {', '.join(r.get('name', str(i)) for i, r in enumerate(results) if r in matches)} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Raw Data",
            "",
            f"Full results as JSON saved to: `tests/results/generator_isolated_results.json`",
        ]
    )

    return "\n".join(lines)


def _mark(condition: bool) -> str:
    return "✓" if condition else "✗"


def _pct(n: int, d: int) -> str:
    if d == 0:
        return "0%"
    return f"{round(n / d * 100)}%"


def _planner_patterns(results: List[Dict]) -> List:
    return [
        ("Single-method code", lambda r: r.get("method_count", 0) == 1),
        ("Short code (< 400 chars)", lambda r: r.get("code_len", 0) < 400),
        ("FLATTEN_CONDITIONAL intent", lambda r: r.get("expected_intent") == "FLATTEN_CONDITIONAL"),
        ("RENAME_SYMBOL intent", lambda r: r.get("expected_intent") == "RENAME_SYMBOL"),
    ]


def _planner_struggles(results: List[Dict]) -> List:
    return [
        ("Multi-method code (> 2 methods)", lambda r: r.get("method_count", 0) > 2),
        ("Long code (> 800 chars)", lambda r: r.get("code_len", 0) > 800),
        ("DECOMPOSE_CONDITIONAL intent", lambda r: r.get("expected_intent") == "DECOMPOSE_CONDITIONAL"),
        ("EXTRACT_CONSTANT with multiple methods", lambda r: r.get("expected_intent") == "EXTRACT_CONSTANT" and r.get("method_count", 0) > 1),
    ]


def _judge_patterns(results: List[Dict]) -> List:
    return [
        ("Obvious signature change (return type mismatch)", lambda run: run.get("case_name", "").startswith("extract_constant_broken")),
        ("Code identical to original", lambda run: run.get("case_name", "").startswith("decompose_returned")),
        ("Long scratchpad (> 200 chars)", lambda run: len(run.get("scratchpad", "")) > 200),
    ]


def _judge_struggles(results: List[Dict]) -> List:
    return [
        ("Correct code (false REVISE risk)", lambda run: run.get("case_name", "").startswith("extract_method_correct") or run.get("case_name", "").startswith("rename_symbol_correct") or run.get("case_name", "").startswith("split_loop_correct")),
        ("Short scratchpad (< 100 chars)", lambda run: len(run.get("scratchpad", "")) < 100),
        ("Complex multi-method refactoring", lambda run: run.get("case_name", "").startswith("extract_method")),
    ]


def _generator_patterns(results: List[Dict]) -> List:
    return [
        ("Single mutation plan", lambda r: r.get("mutation_count", 0) == 1),
        ("RENAME_SYMBOL plan", lambda r: r.get("intent") == "RENAME_SYMBOL"),
        ("Short code (< 400 chars)", lambda r: r.get("code_len", 0) < 400),
        ("ADD_CONSTANT plan", lambda r: r.get("intent") == "ADD_CONSTANT"),
    ]


def _generator_struggles(results: List[Dict]) -> List:
    return [
        ("Multi-mutation plan (> 4 mutations)", lambda r: r.get("mutation_count", 0) > 4),
        ("DECOMPOSE_CONDITIONAL plan", lambda r: r.get("intent") == "DECOMPOSE_CONDITIONAL"),
        ("FLATTEN_CONDITIONAL with exceptions", lambda r: r.get("intent") == "FLATTEN_CONDITIONAL" and "exception" in r.get("plan_summary", "").lower()),
    ]


import json
