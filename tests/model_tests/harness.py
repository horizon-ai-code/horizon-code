import asyncio
import json
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

import yaml
from pydantic import BaseModel

sys.path.insert(0, ".")

from app.modules.agent_service import AgentService
from app.modules.validator import Validator, ASTWalker
from app.utils.paths import MODELS_CONFIG_PATH, PROMPTS_CONFIG_PATH
from app.utils.response_parser import ResponseParser
from app.utils.schemas import (
    ArchitectAnalysisResponse,
    ASTArchitectResponse,
    IntentClassifierResponse,
    StructuralAuditorResponse,
)


class ModelTestHarness:
    def __init__(self, role: str):
        self.role = role
        self.agent = AgentService()
        self.validator = Validator()

        with open(MODELS_CONFIG_PATH, "r") as f:
            self.model_config = yaml.safe_load(f)
        with open(PROMPTS_CONFIG_PATH, "r") as f:
            self.prompts = yaml.safe_load(f)

        self._model_loaded = False

    async def load_model(self) -> None:
        if self.role in ("planner", "generator"):
            config_key = self.role
        elif self.role == "judge":
            config_key = "judge"
        else:
            raise ValueError(f"Unknown role: {self.role}")

        await self.agent.load(self.model_config[config_key])
        self._model_loaded = True

    async def unload_model(self) -> None:
        if self._model_loaded:
            await self.agent.unload()
            self._model_loaded = False

    async def clear_context(self) -> None:
        if self._model_loaded:
            await self.agent.clear_context()

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temp: float = 0.1,
        max_tokens: int = 1024,
        response_model: Optional[Type[BaseModel]] = None,
    ) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        start = time.time()
        try:
            raw = await self.agent.generate(
                messages=messages,
                temp=temp,
                max_tokens=max_tokens,
                response_model=response_model,
            )
            duration = round(time.time() - start, 2)
            content = raw["choices"][0]["message"].get("content") or ""
            return {
                "success": True,
                "content": content,
                "duration": duration,
                "error": None,
            }
        except Exception as e:
            duration = round(time.time() - start, 2)
            return {
                "success": False,
                "content": "",
                "duration": duration,
                "error": str(e),
            }

    def check_scope_anchor_exists(
        self, code: str, target_class: str, member: str
    ) -> Dict[str, Any]:
        res = self.validator.check_syntax(code)
        if not res["is_valid"]:
            return {"valid": False, "class_exists": False, "member_exists": False, "error": "Code syntax invalid"}
        ast = res["ast"]
        import javalang
        classes = ASTWalker.find_nodes(ast, javalang.tree.ClassDeclaration)
        if classes:
            class_exists = any(
                getattr(c, "name", "") == target_class for c in classes
            )
        else:
            class_exists = not target_class
        member_exists = False
        if member:
            methods = ASTWalker.find_nodes(ast, javalang.tree.MethodDeclaration)
            member_exists = any(
                getattr(m, "name", "") == member for m in methods
            )
            # Also check fields and variables (for RENAME_SYMBOL on fields/vars)
            if not member_exists:
                fields = ASTWalker.find_nodes(ast, javalang.tree.FieldDeclaration)
                for f in fields:
                    for d in (f.declarators if hasattr(f, "declarators") else []):
                        if getattr(d, "name", "") == member:
                            member_exists = True
                            break
                    if member_exists:
                        break
            if not member_exists:
                vars = ASTWalker.find_nodes(ast, javalang.tree.VariableDeclarator)
                member_exists = any(
                    getattr(v, "name", "") == member for v in vars
                )
        else:
            member_exists = True
        return {
            "valid": True,
            "class_exists": class_exists,
            "member_exists": member_exists,
            "error": None,
        }

    def find_ast_identifiers(self, code: str) -> set:
        identifiers = set()
        res = self.validator.check_syntax(code)
        if not res["is_valid"]:
            return identifiers

        import javalang

        ast = res["ast"]

        for cls in ASTWalker.find_nodes(ast, javalang.tree.ClassDeclaration):
            name = getattr(cls, "name", None)
            if name:
                identifiers.add(name)
        for m in ASTWalker.find_nodes(ast, javalang.tree.MethodDeclaration):
            name = getattr(m, "name", None)
            if name:
                identifiers.add(name)
            for param in (m.parameters or []):
                pname = getattr(param, "name", None)
                if pname:
                    identifiers.add(pname)
        for f in ASTWalker.find_nodes(ast, javalang.tree.FieldDeclaration):
            for d in (f.declarators if hasattr(f, "declarators") else []):
                name = getattr(d, "name", None)
                if name:
                    identifiers.add(name)
        for v in ASTWalker.find_nodes(ast, javalang.tree.VariableDeclarator):
            name = getattr(v, "name", None)
            if name:
                identifiers.add(name)
        for inv in ASTWalker.find_nodes(ast, javalang.tree.MethodInvocation):
            name = getattr(inv, "member", None)
            if name:
                identifiers.add(name)
        for ref in ASTWalker.find_nodes(ast, javalang.tree.MemberReference):
            name = getattr(ref, "member", None)
            if name:
                identifiers.add(name)

        throw_pattern = re.findall(r"throw\s+new\s+(\w+)", code)
        identifiers.update(throw_pattern)
        str_pattern = re.findall(r'"([^"]*)"', code)
        identifiers.update(str_pattern)

        type_refs = set(re.findall(r"\b(List|Map|Set|HashMap|HashSet|ArrayList|Stack|StringBuilder|Arrays|Collections|Math|Integer|Double|Boolean|Character|String|Object|Order|User|OrderProcessor|Solution|Calculator|LoanApprover|Flag|Circle|Processor|Checker|UserManager|ListNode|TreeNode)\b", code))
        identifiers.update(type_refs)

        return identifiers

    def detect_hallucinations(self, plan_or_analysis: Dict, code_identifiers: set) -> List[str]:
        candidates = set()
        exempt = set()

        # Exempt items the instruction explicitly requests as new structures
        for item in plan_or_analysis.get("new_structures_needed", []) or []:
            if isinstance(item, str):
                exempt.add(item.split("(")[0].strip())

        if "target" in plan_or_analysis:
            candidates.add(plan_or_analysis["target"])
        for key in ("primary_targets", "secondary_targets", "new_structures_needed"):
            for item in plan_or_analysis.get(key, []) or []:
                if isinstance(item, str):
                    candidates.add(item.split("(")[0].strip())

        for m in plan_or_analysis.get("ast_mutations", []) or []:
            target = (m.get("target", "") or "").split("(")[0].strip()
            action = m.get("action", "")
            if target:
                candidates.add(target)
                # ADD_* targets are expected to be new names — exempt them
                if action in ("ADD_METHOD", "ADD_FIELD", "ADD_CONSTANT", "ADD_ENUM"):
                    exempt.add(target)
            for param in m.get("details", {}).get("parameters", []) or []:
                pname = param.get("type") or param.get("name")
                if pname and pname not in ("int", "double", "float", "boolean", "String", "void", "char", "long", "byte", "short"):
                    pass

        hallucinations = []
        for c in candidates:
            if c and len(c) >= 2 and c not in code_identifiers and c not in exempt:
                if not any(c in ci for ci in code_identifiers) and not any(ci in c for ci in code_identifiers):
                    hallucinations.append(c)
        return hallucinations

    def save_results(self, results: List[Dict], role: str) -> str:
        path = f"test_results/{role}_isolated_results.json"
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        return path

    @staticmethod
    def build_planner_report(results: List[Dict]) -> str:
        from tests.model_tests.report_templates import build_report
        return build_report("planner", results)

    @staticmethod
    def build_judge_report(results: List[Dict]) -> str:
        from tests.model_tests.report_templates import build_report
        return build_report("judge", results)

    @staticmethod
    def build_generator_report(results: List[Dict]) -> str:
        from tests.model_tests.report_templates import build_report
        return build_report("generator", results)
