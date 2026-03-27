import re
from typing import List

import yaml
from llama_cpp import ChatCompletionRequestMessage, CreateChatCompletionResponse

from app.modules.agent_service import AgentService
from app.modules.validator import Validator
from app.modules.websocket_manager import WebSocketManager
from app.utils.paths import MODELS_CONFIG_PATH


class Orchestrator:
    def __init__(
        self,
        agent_service: AgentService,
        validator: Validator,
        websocket_manager: WebSocketManager,
    ):
        self.agent_service = agent_service
        self.validator = validator
        self.websocket_manager = websocket_manager

        try:
            with open(MODELS_CONFIG_PATH, "r") as config:
                self.model_config: dict = yaml.safe_load(config)
        except yaml.YAMLError as e:
            print(f"Error loading config: {e}")

    async def execute_orchestration(self, websocket, user_code, user_instruction):
        current_code = user_code
        current_instruction = user_instruction
        iteration = 0

        while True:
            iteration += 1
            print(f"\n[Orchestrator] ── Iteration {iteration} ──────────────────────")

            print("[Planner]    Loading model...")
            await self.agent_service.load(self.model_config["planner"])

            print("[Planner]    Generating plan & instructions...")
            result = await self.generate_plan_and_instruction(
                current_code, current_instruction
            )
            instructions = result["instructions"]
            print("[Planner]    Done.")

            print("[Generator]  Swapping model...")
            await self.agent_service.swap(self.model_config["generator"])

            print("[Generator]  Refactoring code...")
            refactored_code = await self.generate_refactored_code(
                current_code, instructions
            )
            print("[Generator]  Done.")

            print("[Validator]  Checking syntax...")
            syntax_verdict = self.validator.check_syntax(refactored_code["code"])
            print(
                f"[Validator]  is_valid={syntax_verdict['is_valid']}, tier={syntax_verdict['structure_tier']}"
            )

            if syntax_verdict["is_valid"]:
                print("[Validator]  Syntax OK — exiting loop.")
                current_code = refactored_code["code"]
                break

            print(
                f"[Validator]  {len(syntax_verdict['errors'])} error(s) found — handing off to Judge."
            )

            print("[Judge]      Swapping model...")
            await self.agent_service.swap(self.model_config["judge"])

            print("[Judge]      Interpreting errors & generating fix instructions...")
            judge_result = await self.interpret_errors_and_generate_instructions(
                refactored_code["code"], syntax_verdict["errors"]
            )
            print("[Judge]      Done.")

            print("[Orchestrator] Unloading model, preparing next iteration...")
            # await self.agent_service.unload()

            current_code = refactored_code["code"]
            current_instruction = judge_result["instructions"]

        print("\n[Validator]  Computing cyclomatic complexity...")
        complexity = self.validator.check_complexity(current_code)
        complexity_score = complexity["complexity_score"]
        print(
            f"[Validator]  complexity_score={complexity_score}, fallback={complexity['is_fallback']}"
        )

        print("[Judge]      Loading model for insights...")
        await self.agent_service.swap(self.model_config["judge"])

        print("[Judge]      Generating insights...")
        insights = await self.generate_insights(
            user_code, current_code, complexity_score
        )
        print("[Judge]      Done. Orchestration complete.\n")

        return current_code, insights

    async def generate_plan_and_instruction(self, code: str, instructions: str) -> dict:
        prompt: str = f"<code>{code}</code>\n<instruction>{instructions}</instruction>"
        query: List[ChatCompletionRequestMessage] = [
            {
                "role": "system",
                "content": self.model_config["planner"]["sysprompt"],
            },
            {"role": "user", "content": prompt},
        ]

        raw_reponse: CreateChatCompletionResponse = await self.agent_service.generate(
            messages=query,
            temp=self.model_config["planner"]["temperature"],
            max_tokens=self.model_config["planner"]["max_tokens"],
            stream=False,
        )

        text: str = self._get_response(raw_reponse)
        print(f"\n[Planner RAW OUTPUT]\n{'─' * 50}\nPlan:\n{text}{'─' * 50}")
        print(
            f"\n[Planner PARSED OUTPUT]\n{'─' * 50}\nPlan:\n{self._extract_text(raw_text=text, tags='plan')}\nInstructions:\n{self._extract_text(raw_text=text, tags='instructions')}\n{'─' * 50}"
        )

        result: dict[str, str] = {
            "plan": self._extract_text(raw_text=text, tags="plan"),
            "instructions": self._extract_text(raw_text=text, tags="instructions"),
        }

        return result

    async def generate_refactored_code(self, code: str, instructions: str):
        prompt: str = f"<code>{code}</code>\n<instruction>{instructions}</instruction>"
        query: List[ChatCompletionRequestMessage] = [
            {
                "role": "system",
                "content": self.model_config["generator"]["sysprompt"],
            },
            {"role": "user", "content": prompt},
        ]

        raw_reponse: CreateChatCompletionResponse = await self.agent_service.generate(
            messages=query,
            temp=self.model_config["generator"]["temperature"],
            max_tokens=self.model_config["generator"]["max_tokens"],
            stream=False,
        )

        text: str = self._get_response(raw_reponse)
        print(f"\n[Generator RAW OUTPUT]\n{'─' * 50}\n{text}\n{'─' * 50}")

        result: dict[str, str] = {
            "code": self._extract_text(raw_text=text, tags="code"),
        }

        return result

    async def interpret_errors_and_generate_instructions(
        self, code: str, error_logs: list
    ):
        formatted_errors: str = "\n".join([f"- {error}" for error in error_logs])
        prompt: str = (
            f"<code>{code}</code>\n<instruction>{formatted_errors}</instruction>"
        )
        query: List[ChatCompletionRequestMessage] = [
            {
                "role": "system",
                "content": self.model_config["judge"]["sysprompt_error_interpreter"],
            },
            {"role": "user", "content": prompt},
        ]

        raw_reponse: CreateChatCompletionResponse = await self.agent_service.generate(
            messages=query,
            temp=self.model_config["judge"]["temperature"],
            max_tokens=self.model_config["judge"]["max_tokens"],
            stream=False,
        )

        text: str = self._get_response(raw_reponse)
        # print(f"\n[Judge ERROR INTERPRETER RAW OUTPUT]\n{'─' * 50}\n{text}\n{'─' * 50}")

        result: dict[str, str] = {
            "interpretation": self._extract_text(raw_text=text, tags="interpretation"),
            "instructions": self._extract_text(raw_text=text, tags="instructions"),
        }

        return result

    async def generate_insights(self, user_code: str, refactored_code: str, cc: int):
        prompt: str = f"<user_code>{user_code}</user_code>\n<refactored_code>{refactored_code}</refactored_code><cc>{cc}</cc>"
        query: List[ChatCompletionRequestMessage] = [
            {
                "role": "system",
                "content": self.model_config["judge"]["sysprompt_insights"],
            },
            {"role": "user", "content": prompt},
        ]

        raw_reponse: CreateChatCompletionResponse = await self.agent_service.generate(
            messages=query,
            temp=self.model_config["judge"]["temperature"],
            max_tokens=self.model_config["judge"]["max_tokens"],
            stream=False,
        )

        text: str = self._get_response(raw_reponse)
        # print(f"\n[Judge INSIGHTS RAW OUTPUT]\n{'─' * 50}\n{text}\n{'─' * 50}")

        result: dict[str, str] = {
            "insights": self._extract_text(raw_text=text, tags="insights"),
        }

        return result

    def _get_response(self, response: CreateChatCompletionResponse) -> str:
        return response["choices"][0]["message"]["content"]  # type: ignore

    def _extract_text(self, raw_text: str, tags: str) -> str:
        # Step 1: Strip out the <think> block(s) completely.
        # re.DOTALL is mandatory here too, so it catches multi-line thought processes.
        # We use re.IGNORECASE just in case the model outputs <THINK> or similar.
        text_without_thoughts = re.sub(
            r"<think>.*?</think>", "", raw_text, flags=re.DOTALL | re.IGNORECASE
        )

        # Step 2: Run your original extraction logic on the cleaned text.
        pattern = rf"<{tags}\b[^>]*>(.*?)</{tags}>"

        # The re.DOTALL flag is MANDATORY here so (.*?) can cross line breaks
        match = re.search(pattern, text_without_thoughts, re.DOTALL)
        if match:
            # .strip() cleans up the extra newlines immediately inside the tags
            return match.group(1).strip()

        return ""
