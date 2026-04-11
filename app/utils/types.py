from enum import Enum
from typing import Literal

from pydantic import BaseModel


class RefactorRequest(BaseModel):
    code: str
    user_instruction: str


class HaltRequest(BaseModel):
    type: Literal["halt"]


class Role(str, Enum):
    Planner = "Planner"
    Generator = "Generator"
    Judge = "Judge"
    Validator = "Validator"
    System = "System"
