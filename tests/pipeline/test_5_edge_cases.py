"""Edge case tests for full pipeline — empty bodies, nested classes, long methods, etc."""
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
        "name": "EMPTY_METHOD_BODY",
        "code": """public void foo() {}""",
        "instruction": "Extract the empty body into a helper method called fooHelper.",
    },
    {
        "name": "STANDALONE_METHOD",
        "code": """void bar(int x) {
    return;
}""",
        "instruction": "Rename bar to execute.",
    },
    {
        "name": "LONG_METHOD_FLATTEN",
        "code": """public int longMethod(int a, int b, int c, int d) {
    if (a > 0) {
        if (b > 0) {
            if (c > 0) {
                if (d > 0) {
                    return a + b + c + d;
                } else {
                    return a + b + c;
                }
            } else {
                if (d > 0) {
                    return a + b + d;
                } else {
                    return a + b;
                }
            }
        } else {
            if (c > 0) {
                if (d > 0) {
                    return a + c + d;
                } else {
                    return a + c;
                }
            } else {
                if (d > 0) {
                    return a + d;
                } else {
                    return a;
                }
            }
        }
    } else {
        if (b > 0) {
            if (c > 0) {
                if (d > 0) {
                    return b + c + d;
                } else {
                    return b + c;
                }
            } else {
                if (d > 0) {
                    return b + d;
                } else {
                    return b;
                }
            }
        } else {
            if (c > 0) {
                if (d > 0) {
                    return c + d;
                } else {
                    return c;
                }
            } else {
                if (d > 0) {
                    return d;
                } else {
                    return 0;
                }
            }
        }
    }
}""",
        "instruction": "Flatten the deeply nested if-else into early return guard clauses. Each branch should return immediately without nesting.",
    },
    {
        "name": "NESTED_INNER_CLASSES",
        "code": """import java.util.List;
import java.util.ArrayList;

public class Outer {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String n) {
        this.name = n;
    }

    static class InnerOne {
        private int value;

        public int getValue() {
            return value;
        }

        public void setValue(int v) {
            this.value = v;
        }
    }

    static class InnerTwo {
        private List<String> items;

        public void addItem(String item) {
            if (items == null) {
                items = new ArrayList<>();
            }
            items.add(item);
        }

        public List<String> getItems() {
            return items;
        }
    }
}""",
        "instruction": "Extract the getName and setName methods in Outer class into a separate NameHolder interface.",
    },
    {
        "name": "NOOP_RENAME",
        "code": """import java.util.List;
import java.util.ArrayList;

public class Processor {
    private List<String> data;

    public void process() {
        if (data != null && !data.isEmpty()) {
            for (String item : data) {
                System.out.println(item);
            }
        }
    }
}""",
        "instruction": "Rename the process method to processItems.",
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
        self.log: List[Dict] = []
    @property
    def is_stale(self) -> bool:
        return False
    async def send_status(self, role, content, phase=None, **kw):
        entry = {"role": role.value if hasattr(role, 'value') else str(role), "phase": phase, "content": str(content)[:500]}
        self.statuses.append((role, str(content)[:200]))
        self.log.append(entry)
    async def send_result(self, **kw):
        self.results = kw
        self.log.append({"event": "send_result", "data": {k: str(v)[:200] for k, v in kw.items()}})
    async def send_insights(self, insights):
        self.log.append({"event": "send_insights", "insights": str(insights)[:200]})


async def run_case(case: Dict[str, Any], index: int, total: int) -> Dict[str, Any]:
    case_name = case["name"]
    code = case["code"]
    instruction = case["instruction"]
    print(f"\n{'='*60}")
    print(f"[{index+1}/{total}] {case_name}")
    print(f"{'='*60}")
    print(f"Instruction: {instruction[:120]}...")

    agent = AgentService()
    validator = Validator()
    db = MockDB()

    orch = Orchestrator(agent, validator, db)
    orch.SKIP_JUDGE = False

    client = MockClient(f"test-{case_name}")

    phase_log: List[Dict] = []
    t_start = time.time()
    try:
        await orch.execute_orchestration(client, code, instruction)
    except Exception as e:
        print(f"  Orchestration error: {e}")
        import traceback
        traceback.print_exc()
        phase_log.append({"phase": "error", "error": str(e)[:300]})
    total_duration = int((time.time() - t_start) * 1000)

    state = getattr(orch, 'state', None)
    if state:
        original_cc = state.original_complexity
        working_code = state.working_code
        refactored_cc = validator.get_complexity(working_code)
        feedback = state.cumulative_feedback

        phase_log.append({
            "phase": "exit",
            "exit_status": state.exit_status.value if state.exit_status else "N/A",
            "strategy_iter": state.strategy_iter,
            "syntax_iter": state.syntax_iter,
            "current_phase": state.current_phase,
            "duration_ms": total_duration,
        })

        result = {
            "case": case_name,
            "instruction": instruction,
            "code": code,
            "exit_status": state.exit_status.value if state.exit_status else "N/A",
            "strategy_iter": state.strategy_iter,
            "syntax_iter": state.syntax_iter,
            "current_phase": state.current_phase,
            "total_duration_ms": total_duration,
            "original_cc": original_cc,
            "refactored_cc": refactored_cc,
            "cc_delta": refactored_cc - original_cc,
            "working_code_changed": working_code.strip() != code.strip(),
            "working_code_unchanged": working_code.strip() == code.strip(),
            "generated_code": working_code,
            "validation_findings": [
                {
                    "tier": str(f.failure_tier.value) if hasattr(f, 'failure_tier') else str(f),
                    "message": str(f.error_report.message) if hasattr(f, 'error_report') else str(f),
                }
                for f in feedback
            ] if feedback else [],
            "num_validation_findings": len(feedback),
            "mutation_index": state.mutation_index,
            "mutation_queue_len": len(state.mutation_queue) if hasattr(state, 'mutation_queue') else 0,
            "phase_log": phase_log,
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

        if hasattr(state, 'intent_packet') and state.intent_packet:
            result["intent_packet"] = state.intent_packet

        status = result.get('exit_status', '?')
        cc_delta = result.get('cc_delta', 0)
        gen_ok = result.get('gen_ok_steps', 0)
        gen_fail = result.get('gen_fail_steps', 0)
        findings = result.get('num_validation_findings', 0)
        unchanged = result.get('working_code_unchanged', False)
        arrow = "\u2192"
        delta_sym = "\u0394"
        print(f"  Status:   {status}{' (UNCHANGED)' if unchanged else ''}")
        print(f"  CC:       {result.get('original_cc', '?')} {arrow} {result.get('refactored_cc', '?')} ({delta_sym}={cc_delta})")
        print(f"  Findings: {findings}")
        print(f"  Gen OK:   {gen_ok}/{gen_ok + gen_fail}")
        print(f"  Time:     {total_duration}ms")
    else:
        result = {
            "case": case_name,
            "instruction": instruction,
            "code": code,
            "error": "No state available",
            "total_duration_ms": total_duration,
            "phase_log": phase_log,
        }

    await agent.unload()
    return result


async def main() -> None:
    os.makedirs("tests/results", exist_ok=True)

    print(f"\n{'='*60}")
    print("Edge Case Pipeline Tests")
    print(f"Mode: Orchestrator (SKIP_JUDGE=False)")
    print(f"{'='*60}")

    all_results = []
    for i, case in enumerate(TEST_CASES):
        r = await run_case(case, i, len(TEST_CASES))
        all_results.append(r)

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_cases": len(all_results),
        "config": {
            "SKIP_JUDGE": False,
        },
        "results": all_results,
    }
    output_path = "tests/results/edge_cases_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    status_ok = {"SUCCESS", "PROCESSING"}
    print(f"\n{'='*60}")
    print("SUMMARY — Edge Case Tests")
    print(f"{'='*60}")
    cc_header = "CC \u0394"
    print(f"{'Case':40s} {'Status':15s} {cc_header:>5s} {'Findings':>9s} {'Gen OK':>7s} {'Time':>8s}")
    print("-" * 90)
    for r in all_results:
        findings = r.get('num_validation_findings', 0)
        cc_delta = r.get('cc_delta', 0)
        gen_ok = f"{r.get('gen_ok_steps', '?')}/{r.get('gen_ok_steps', 0) + r.get('gen_fail_steps', 0)}"
        status = r.get('exit_status', '?')
        if r.get('working_code_unchanged'):
            status += " (IDEN)"
        print(f"{r['case']:40s} {status:15s} {cc_delta:>+5d} {findings:>9d} {gen_ok:>7s} {r.get('total_duration_ms', 0):>8d}ms")

    passed = sum(1 for r in all_results if r.get('exit_status') in status_ok)
    failed = sum(1 for r in all_results if r.get('exit_status') not in status_ok and r.get('exit_status') != '?')
    print(f"\nTotal: {len(all_results)} | Pass: {passed} | Fail: {failed}")
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
