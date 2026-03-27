from pydantic import BaseModel


class RefactorRequest(BaseModel):
    code: str
    user_instruction: str
