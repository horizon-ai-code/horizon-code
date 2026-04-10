import asyncio
import json
import os
import time

from app.modules.agent_service import AgentService
from app.modules.context_manager import DatabaseManager

# IMPORTANT: Import your Orchestrator and any required dependencies here.
# You may need to adjust this import path based on how your app is structured.
from app.modules.orchestrator import Orchestrator
from app.modules.validator import Validator

# e.g., from app.modules.agent_service import AgentService
# e.g., from app.modules.validator import Validator

TEST_SUITE_FILE = "refactoring_test_suite.json"


async def main():
    print("Which configuration are you currently testing?")
    print("1. deepseek_loose")
    print("2. deepseek_strict")
    print("3. qwen_loose")
    print("4. qwen_strict")
    choice = input("Enter the number of the configuration (1-4): ")

    config_map = {
        "1": "deepseek_loose",
        "2": "deepseek_strict",
        "3": "qwen_loose",
        "4": "qwen_strict",
    }
    config_name = config_map.get(choice, "custom_run")
    output_json = f"results_{config_name}.json"

    # 1. Load the test suite
    if not os.path.exists(TEST_SUITE_FILE):
        print(f"Error: Could not find {TEST_SUITE_FILE}.")
        return

    with open(TEST_SUITE_FILE, "r") as f:
        tests = json.load(f)

    # 2. Initialize your Orchestrator
    print("\nInitializing Orchestrator dependencies...")
    # NOTE: Instantiate your Orchestrator exactly how your FastAPI app does it.
    agent_service = AgentService()
    validator = Validator()
    db = DatabaseManager()
    # Placeholder for the instantiated class:
    orchestrator = Orchestrator(
        agent_service=agent_service, validator=validator, db=db
    )  # Modify this line to pass your actual dependencies

    print(f"Loaded {len(tests)} tests. Starting execution for: {config_name}\n")

    all_results = []

    # 3. Run tests sequentially
    for i, test in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] Running Test {test['id']}: {test['name']}...")
        start_time = time.time()

        try:
            # Call the method directly
            result = await orchestrator.test_orchestration(
                user_code=test["code"], user_instruction=test["instruction"]
            )

            elapsed_time = round(time.time() - start_time, 2)

            # Combine test metadata with the exact dictionary returned by Orchestrator
            test_record = {
                "test_id": test["id"],
                "category": test["category"],
                "name": test["name"],
                "purpose": test["purpose"],
                "time_seconds": elapsed_time,
                **result,  # This unpackages the passed, cc, insights, and logs array seamlessly
            }

            all_results.append(test_record)

            print(
                f"  -> Finished in {elapsed_time}s | Passed: {result.get('passed')} | Iterations: {result.get('num_of_iterations')}"
            )

        except Exception as e:
            print(f"  -> [ERROR] Test failed: {e}")
            all_results.append(
                {
                    "test_id": test["id"],
                    "name": test["name"],
                    "passed": False,
                    "error": str(e),
                }
            )

        print("-" * 50)

        # Small delay to clear VRAM between runs
        await asyncio.sleep(2)

    # 4. Save the combined results to a single JSON file
    with open(output_json, "w", encoding="utf-8") as jsonfile:
        json.dump(all_results, jsonfile, indent=4)

    print("\nAll tests completed!")
    print(f"Complete results and iteration logs saved to: {output_json}")


if __name__ == "__main__":
    asyncio.run(main())
