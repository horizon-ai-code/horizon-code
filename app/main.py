import asyncio

from app.modules.agent_service import AgentService
from app.modules.orchestrator import Orchestrator
from app.modules.validator import Validator
from app.utils.paths import MODELS_DIR, MODELS_CONFIG_PATH

# ---------------------------------------------------------------------------
# Sample inputs — swap these out for your own snippet + instruction
# ---------------------------------------------------------------------------
SAMPLE_CODE = """
public int factorial(int n) {
    if n == 0 return 1;
    return n * factorial(n - 1)
}
"""

SAMPLE_INSTRUCTION = (
    "Fix the syntax errors and refactor the method to use an iterative "
    "approach instead of recursion."
)


async def main():
    # Wire up services (no real WebSocket needed for a local test)
    agent_service = AgentService()
    validator = Validator()
    websocket = None  # orchestrator accepts None; it's passed through but unused here

    orchestrator = Orchestrator(
        agent_service=agent_service,
        validator=validator,
        websocket_manager=None,
    )

    print("=" * 60)
    print("Starting orchestration test run...")
    print(f"Input code:\n{SAMPLE_CODE.strip()}")
    print(f"\nInstruction: {SAMPLE_INSTRUCTION}")
    print("=" * 60)

    refactored_code, insights = await orchestrator.execute_orchestration(
        websocket=websocket,
        user_code=SAMPLE_CODE,
        user_instruction=SAMPLE_INSTRUCTION,
    )

    print("\n[RESULT] Refactored code:")
    print("-" * 40)
    print(refactored_code)
    print("\n[RESULT] Insights:")
    print("-" * 40)
    print(insights.get("insights", "(no insights returned)"))


if __name__ == "__main__":
    print(MODELS_DIR)
    print(MODELS_CONFIG_PATH)
    asyncio.run(main())
