"""Test: run LONG_METHOD_FLATTEN to verify repetition detection fires."""
import asyncio
import sys
import time

sys.path.insert(0, ".")

from app.modules.agent_service import AgentService
from app.modules.orchestrator import Orchestrator, detect_repetition
from app.modules.validator import Validator
from app.utils.response_parser import ResponseParser


LONG_METHOD_CODE = """public int longMethod(int a, int b, int c, int d) {
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
}"""

INSTRUCTION = "Flatten the deeply nested if-else into early return guard clauses."


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
    def __init__(self):
        self.id = "test-repetition-detection"
        self.statuses = []
        self.results = None
        self.log = []
    async def send_status(self, role, content, phase=None, **kw):
        self.statuses.append((str(role)[:50], str(content)[:200]))
    async def send_result(self, **kw):
        self.results = kw
    async def send_insights(self, insights):
        pass


async def main():
    agent = AgentService()
    validator = Validator()
    db = MockDB()

    orch = Orchestrator(agent, validator, db)
    orch.SKIP_JUDGE = False

    client = MockClient()

    t_start = time.time()
    try:
        await orch.execute_orchestration(client, LONG_METHOD_CODE, INSTRUCTION)
    except Exception as e:
        print(f"\nOrchestration error: {e}")
    total_ms = int((time.time() - t_start) * 1000)

    state = getattr(orch, 'state', None)
    if state:
        exit_status = state.exit_status.value if state.exit_status else "N/A"
        mutations = state.active_plan.get("ast_mutations", []) if state.active_plan else []
        gen_ok = sum(1 for t in getattr(state, 'gen_timings', []) if t.get("status") == "OK")
        gen_fail = sum(1 for t in getattr(state, 'gen_timings', []) if t.get("status") != "OK")
        print(f"\nResult: {exit_status}")
        print(f"Time:   {total_ms}ms")
        print(f"Mutations in plan: {len(mutations)}")
        print(f"Gen OK/Fail: {gen_ok}/{gen_fail}")
        print(f"Phase:    {state.current_phase}")
        if state.working_code and state.working_code.strip() != LONG_METHOD_CODE.strip():
            print("Code CHANGED successfully")
    else:
        print("No state available")

    await agent.unload()


if __name__ == "__main__":
    asyncio.run(main())
