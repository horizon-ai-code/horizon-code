import re
import asyncio
from typing import Any, Dict, List, Optional

import yaml
from llama_cpp import ChatCompletionRequestMessage, CreateChatCompletionResponse

from app.modules.agent_service import AgentService
from app.modules.connection_manager import ClientConnection
from app.modules.context_manager import DatabaseManager
from app.modules.validator import Validator
from app.utils.paths import MODELS_CONFIG_PATH
from app.utils.performance import PerformanceTracker
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
        tracker = PerformanceTracker()
        await tracker.start_tracking()
        try:
            # 1. Initialize the session in the database immediately
            self.db.create_session(
                id=client.id, instruction=user_instruction, original_code=user_code
            )

            # Measure Original Complexity
            orig_complexity_res: Dict[str, Any] = self.validator.check_complexity(user_code)
            original_complexity_score: Optional[int] = orig_complexity_res["complexity_score"]

            current_code: str = user_code
            current_instruction: str = user_instruction

            # Iteration Control
            max_iterations: int = 3
            attempt_count: int = 0
            is_valid_refactor: bool = False

            while attempt_count < max_iterations:
                attempt_count += 1
                await self.agent_service.swap(self.model_config["planner"])

                await self._notify(
                    client=client,
                    role=Role.Planner,
                    message=f"Generating plan & instructions (Attempt {attempt_count}/{max_iterations})...",
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

                # print(f"plan: {result['plan']}")
                # print(f"instruction: {result['instructions']}")

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
                    is_valid_refactor = True
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

            # Fallback Mechanism
            if not is_valid_refactor:
                current_code = user_code

            await self._notify(
                client=client, role=Role.Validator, message="Checking complexity..."
            )

            complexity: Dict[str, Any] = self.validator.check_complexity(current_code)
            refactored_complexity_score: Optional[int] = complexity["complexity_score"]

            await self._notify(
                client=client, role=Role.Validator, message="Complexity measured."
            )

            await tracker.stop_tracking()
            performance_metrics = tracker.get_metrics()

            insights: Dict[str, str] = {}
            if is_valid_refactor:
                await self.agent_service.swap(self.model_config["judge"])

                await self._notify(
                    client=client, role=Role.Judge, message="Generating insights..."
                )

                insights = await self.generate_insights(
                    user_code,
                    current_code,
                    original_complexity_score,
                    refactored_complexity_score,
                    performance_metrics,
                )
            else:
                insights = {
                    "insights": "Unable to refactor: the generated code remained too complex or contained persistent syntax errors after maximum attempts. Reverted to original code."
                }

            await client.send_result(
                final_code=current_code,
                insights=insights["insights"],
                original_complexity=original_complexity_score,
                refactored_complexity=refactored_complexity_score,
                performance_metrics=performance_metrics,
            )
        except asyncio.CancelledError:
            await tracker.stop_tracking()
            self.db.mark_as_halted(client.id)
            await self._notify(client, Role.System, "Process halted.")
            raise
        except Exception as e:
            await tracker.stop_tracking()
            raise e
        finally:
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
        print(text)

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
        self,
        user_code: str,
        refactored_code: str,
        original_complexity: Optional[int],
        refactored_complexity: Optional[int],
        performance_metrics: Dict[str, float],
    ) -> Dict[str, str]:
        # Ensure we have default values to avoid TypeError: unsupported operand type(s) for /: 'NoneType' and 'int'
        gpu_util = performance_metrics.get("avg_gpu_utilization", 0)
        gpu_mem_percent = performance_metrics.get("avg_gpu_memory", 0)
        gpu_mem_used = performance_metrics.get("avg_gpu_memory_used", 0)
        inf_time = performance_metrics.get("inference_time", 0)

        prompt: str = (
            f"<user_code>{user_code}</user_code>\n"
            f"<refactored_code>{refactored_code}</refactored_code>\n"
            f"<original_cc>{original_complexity}</original_cc>\n"
            f"<refactored_cc>{refactored_complexity}</refactored_cc>\n"
            f"<performance>\n"
            f"Avg GPU Utilization: {gpu_util}% \n"
            f"Avg GPU Memory: {gpu_mem_used / (1024*1024*1024):.2f} GB ({gpu_mem_percent}%) \n"
            f"Total Inference Time: {inf_time}s \n"
            f"</performance>"
        )
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
        # 1. Strip the thinking process
        text_without_thoughts: str = re.sub(
            r"<think>.*?</think>", "", raw_text, flags=re.DOTALL | re.IGNORECASE
        )

        # 2. Try the Happy Path: Tags were formatted correctly
        pattern: str = rf"<{tags}\b[^>]*>(.*?)</{tags}>"
        match: Optional[re.Match[str]] = re.search(
            pattern, text_without_thoughts, re.DOTALL
        )

        if match:
            return match.group(1).strip()

        # 3. FALLBACK PATH: The model forgot the XML tags entirely.
        print(f"[Warning] XML tags missing for '{tags}'. Using fallback parser.")

        # Strip out markdown code blocks (e.g., ```java ... ```) so we don't
        # accidentally pass hallucinated code into the instructions.
        # text_without_code_blocks: str = re.sub(
        #     r"```[a-zA-Z]*\n.*?```", "", text_without_thoughts, flags=re.DOTALL
        # )

        # Return the remaining clean text as a fallback.
        # Note: If tags are completely missing, both 'plan' and 'instructions'
        # will end up receiving this same block of text. This is a safe compromise!
        return text_without_thoughts.strip()

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
