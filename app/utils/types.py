from enum import Enum

from pydantic import BaseModel


class RefactorRequest(BaseModel):
    code: str
    user_instruction: str


class Role(str, Enum):
    Planner = "Planner"
    Generator = "Generator"
    Judge = "Judge"
    Validator = "Validator"
