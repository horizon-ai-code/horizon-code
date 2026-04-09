import re
from typing import Any, Dict, List, Optional

import yaml
from llama_cpp import ChatCompletionRequestMessage, CreateChatCompletionResponse

from app.modules.agent_service import AgentService
from app.modules.connection_manager import ClientConnection
from app.modules.context_manager import DatabaseManager
from app.modules.validator import Validator
from app.utils.paths import MODELS_CONFIG_PATH
from app.utils.types import Role


class Orchestrator:
    def __init__(
        self,
        agent_service: AgentService,
        validator: Validator,
        db: DatabaseManager,
    ) -> None:
        self.agent_service: AgentService = agent_service
        self.validator: Validator = validator
        self.db: DatabaseManager = db

        try:
            with open(MODELS_CONFIG_PATH, "r") as config:
                self.model_config: Dict[str, Any] = yaml.safe_load(config)
        except yaml.YAMLError as e:
            print(f"Error loading config: {e}")

    async def execute_orchestration(
        self, client: ClientConnection, user_code: str, user_instruction: str
    ) -> None:
        # 1. Initialize the session in the database immediately
        self.db.create_session(
            id=client.id, instruction=user_instruction, original_code=user_code
        )

        current_code: str = user_code
        current_instruction: str = user_instruction

        while True:
            await self.agent_service.load(self.model_config["planner"])

            await self._notify(
                client=client,
                role=Role.Planner,
                message="Generating plan & instructions...",
            )

            result: Dict[str, str] = await self.generate_plan_and_instruction(
                current_code, current_instruction
            )
            instructions: str = result["instructions"]

            await self._notify(
                client=client,
                role=Role.Planner,
                message=f"Plan generated: {result['plan']}",
                content=result["plan"],
            )

            print(result["plan"])

            await self.agent_service.swap(self.model_config["generator"])

            await self._notify(
                client=client, role=Role.Generator, message="Refactoring code..."
            )

            refactored_code: Dict[str, str] = await self.generate_refactored_code(
                current_code, instructions
            )
            await self._notify(
                client=client,
                role=Role.Generator,
                message="Refactor draft finished.",
                content=refactored_code["code"],
            )

            await self._notify(
                client=client, role=Role.Validator, message="Checking syntax..."
            )

            # Type is Dict[str, Any] because it contains bools, strings, and lists
            syntax_verdict: Dict[str, Any] = self.validator.check_syntax(
                refactored_code["code"]
            )

            if syntax_verdict["is_valid"]:
                await self._notify(
                    client=client, role=Role.Validator, message="Syntax passed."
                )

                current_code = refactored_code["code"]
                break

            await self._notify(
                client=client, role=Role.Validator, message="Errors detected."
            )

            await self.agent_service.swap(self.model_config["judge"])

            await self._notify(
                client=client,
                role=Role.Judge,
                message="Interpreting errors & generating fix instructions...",
            )

            judge_result: Dict[
                str, str
            ] = await self.interpret_errors_and_generate_instructions(
                refactored_code["code"], syntax_verdict["errors"]
            )
            await self._notify(
                client=client,
                role=Role.Judge,
                message="Errors interpreted.",
                content=judge_result["interpretation"],
            )

            current_code = refactored_code["code"]
            current_instruction = judge_result["instructions"]

        await self._notify(
            client=client, role=Role.Validator, message="Checking complexity..."
        )

        complexity: Dict[str, Any] = self.validator.check_complexity(current_code)

        # Optional[int] because complexity score can technically be None if the snippet is empty
        complexity_score: Optional[int] = complexity["complexity_score"]

        await self._notify(
            client=client, role=Role.Validator, message="Complexity measured."
        )

        await self.agent_service.swap(self.model_config["judge"])

        await self._notify(
            client=client, role=Role.Judge, message="Generating insights..."
        )

        insights: Dict[str, str] = await self.generate_insights(
            user_code, current_code, complexity_score
        )

        await client.send_result(
            final_code=current_code,
            insights=insights["insights"],
            complexity=complexity_score,
        )
        await self.agent_service.unload()

        print("Orchestration finished.")

    async def generate_plan_and_instruction(
        self, code: str, instructions: str
    ) -> Dict[str, str]:
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
        # print(text)

        result: Dict[str, str] = {
            "plan": self._extract_text(raw_text=text, tags="plan"),
            "instructions": self._extract_text(raw_text=text, tags="instructions"),
        }

        return result

    async def generate_refactored_code(
        self, code: str, instructions: str
    ) -> Dict[str, str]:
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

        result: Dict[str, str] = {
            "code": self._extract_text(raw_text=text, tags="code"),
        }

        return result

    async def interpret_errors_and_generate_instructions(
        self, code: str, error_logs: List[Dict[str, Any]]
    ) -> Dict[str, str]:
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

        result: Dict[str, str] = {
            "interpretation": self._extract_text(raw_text=text, tags="interpretation"),
            "instructions": self._extract_text(raw_text=text, tags="instructions"),
        }

        return result

    async def generate_insights(
        self, user_code: str, refactored_code: str, cc: Optional[int]
    ) -> Dict[str, str]:
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

        result: Dict[str, str] = {
            "insights": self._extract_text(raw_text=text, tags="insights"),
        }

        return result

    def _get_response(self, response: CreateChatCompletionResponse) -> str:
        return response["choices"][0]["message"]["content"]  # type: ignore

    def _extract_text(self, raw_text: str, tags: str) -> str:
        text_without_thoughts: str = re.sub(
            r"<think>.*?</think>", "", raw_text, flags=re.DOTALL | re.IGNORECASE
        )

        pattern: str = rf"<{tags}\b[^>]*>(.*?)</{tags}>"

        # Note: Match can be None, so we type it as Optional[re.Match]
        match: Optional[re.Match[str]] = re.search(
            pattern, text_without_thoughts, re.DOTALL
        )
        if match:
            return match.group(1).strip()

        return ""

    async def _notify(
        self,
        client: ClientConnection,
        role: Role,
        message: str,
        content: Optional[str] = None,
    ) -> None:
        """Helper to print to terminal, persist to DB, and notify frontend."""
        print(f"[{role}] {message}")

        # Persist the log entry to the database in real-time
        self.db.log_status(
            session_id=client.id, role=role, status=message, content=content
        )

        await client.send_status(role=role, content=message)
