from pydantic import BaseModel, UUID4
from datetime import datetime
from typing import List, Optional

class LogEntry(BaseModel):
    role: str
    status: str
    content: Optional[str] = None
    created_at: datetime

class HistoryStub(BaseModel):
    id: UUID4
    user_instruction: str

class HistoryDetail(BaseModel):
    id: UUID4
    user_instruction: str
    original_code: str
    refactored_code: Optional[str] = None
    insights: Optional[str] = None
    original_complexity: Optional[int] = None
    refactored_complexity: Optional[int] = None
    planner_model: Optional[str] = None
    generator_model: Optional[str] = None
    judge_model: Optional[str] = None
    avg_gpu_utilization: Optional[float] = None
    avg_gpu_memory: Optional[float] = None
    avg_gpu_memory_used: Optional[float] = None
    inference_time: Optional[float] = None
    created_at: datetime
    logs: List[LogEntry]

class DeleteResponse(BaseModel):
    status: str
    message: str
