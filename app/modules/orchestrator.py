import re
from typing import List

import yaml
from llama_cpp import ChatCompletionRequestMessage, CreateChatCompletionResponse

from app.modules.agent_service import AgentService
from app.modules.validator import Validator
from app.modules.websocket_manager import WebSocketManager


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
            with open("model_config.yaml", "r") as config:
                self.model_config: dict = yaml.safe_load(config)
        except yaml.YAMLError as e:
            print(f"Error loading config: {e}")

    #     def execute_orchestration(self, websocket, user_code, user_instruction):
    #         current_code = user_code
    #         current_instruction = user_instruction

    #         while True:
    #             await self.agent_service.load(
    #                 path=str(
    #                     MODELS_DIR / self.model_config["models"][planner_model]["file_name"]
    #                 ),
    #                 n_gpu_layers=self.model_config["models"][planner_model]["layers"],
    #                 n_ctx=self.model_config["agents"]["planner"]["context_tokens"],
    #             )

    #             plan, instructions = await self.generate_plan_and_instructions(
    #                 current_code, current_instruction
    #             )

    #             await self.agent_service.swap(
    #                 path=str(
    #                     MODELS_DIR
    #                     / self.model_config["models"][generator_model]["file_name"]
    #                 ),
    #                 n_gpu_layers=self.model_config["models"][generator_model]["layers"],
    #                 n_ctx=self.model_config["agents"]["generator"]["context_tokens"],
    #             )

    #             refactored_code = await self.generate_refactored_code(
    #                 current_code, instructions
    #             )

    #             syntax_verdict = self.validator.check_syntax(refactored_code)

    #             if syntax_verdict["is_valid"]:
    #                 current_code = refactored_code
    #                 break

    #             await self.agent_service.swap(
    #                 path=str(
    #                     MODELS_DIR / self.model_config["models"][judge_model]["file_name"]
    #                 ),
    #                 n_gpu_layers=self.model_config["models"][judge_model]["layers"],
    #                 n_ctx=self.model_config["agents"]["judge"]["context_tokens"],
    #             )

    #             log_interpretation, judge_instructions = (
    #                 self.interpret_errors_and_generate_instructions(
    #                     syntax_verdict["errors"]
    #                 )
    #             )

    #             self.agent_service.unload()

    #             current_code = refactored_code
    #             current_instruction = judge_instructions

    #         complexity = self.validator.check_cc(current_code)

    #         await self.agent_service.load(
    #             path=str(
    #                 MODELS_DIR / self.model_config["models"][judge_model]["file_name"]
    #             ),
    #             n_gpu_layers=self.model_config["models"][judge_model]["layers"],
    #             n_ctx=self.model_config["agents"]["judge"]["context_tokens"],
    #         )

    #         insights = self.generate_insights(user, current_code, complexity)

    #         return current_code, insights

    async def generate_plan_and_instruction(self, code: str, instructions: str) -> dict:
        prompt: str = f"<code>{code}</code>\n<instruction>{instructions}</instruction>"
        query: List[ChatCompletionRequestMessage] = [
            {
                "role": "system",
                "content": self.model_config["agents"]["generator"]["system_prompt"],
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
                "content": self.model_config["agents"]["generator"]["system_prompt"],
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
                "content": self.model_config["judge"]["system_prompt"],
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

        result: dict[str, str] = {
            "code": self._extract_text(raw_text=text, tags="code"),
        }

        return result

    def _get_response(self, response: CreateChatCompletionResponse) -> str:
        return response["choices"][0]["message"]["content"]  # type: ignore

    def _extract_text(self, raw_text: str, tags: str) -> str:
        pattern = rf"<{tags}\b[^>]*>(.*?)</{tags}>"

        match = re.search(pattern, raw_text)
        if match:
            return match.group(1)

        return ""
