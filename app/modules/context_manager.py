import datetime
from typing import Any, Dict, List, Optional

import peewee
from playhouse.shortcuts import model_to_dict

from app.utils.paths import DB_DIR, DB_PATH

# 1. Initialize the SQLite database connection
# WAL mode (Write-Ahead Logging) is excellent for handling concurrent WebSocket requests]

DB_DIR.mkdir(parents=True, exist_ok=True)

db = peewee.SqliteDatabase(DB_PATH, pragmas={"journal_mode": "wal"})


# 2. Define the Database Schema
class RefactorHistory(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    status = peewee.CharField(default="Processing")
    user_instruction = peewee.TextField()
    original_code = peewee.TextField()
    refactored_code = peewee.TextField(null=True)
    insights = peewee.TextField(null=True)
    complexity = peewee.IntegerField(null=True)
    avg_gpu_utilization = peewee.FloatField(null=True)
    avg_gpu_memory = peewee.FloatField(null=True)
    avg_gpu_memory_used = peewee.FloatField(null=True)
    inference_time = peewee.FloatField(null=True)
    created_at = peewee.DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = db


class OrchestrationLog(peewee.Model):
    id = peewee.AutoField()
    session = peewee.ForeignKeyField(
        RefactorHistory, backref="logs", on_delete="CASCADE"
    )
    role = peewee.CharField()
    status = peewee.TextField()
    content = peewee.TextField(null=True)
    created_at = peewee.DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = db


# 3. Create the Context Manager
class DatabaseManager:
    def __init__(self):
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Safely creates the tables when the app starts if they don't exist."""
        db.connect(reuse_if_open=True)
        db.create_tables([RefactorHistory, OrchestrationLog], safe=True)
        db.close()

    def create_session(self, id: str, instruction: str, original_code: str) -> None:
        """Initializes a refactoring session in the database."""
        with db.atomic():
            RefactorHistory.create(
                id=id,
                user_instruction=instruction,
                original_code=original_code,
            )

    def log_status(
        self, session_id: str, role: str, status: str, content: Optional[str] = None
    ) -> None:
        """Persists a single orchestration step/log to the database."""
        with db.atomic():
            OrchestrationLog.create(
                session=session_id,
                role=role,
                status=status,
                content=content,
            )

    def mark_as_halted(self, id: str) -> None:
        """Updates session status to Halted."""
        with db.atomic():
            RefactorHistory.update(status="Halted").where(RefactorHistory.id == id).execute()

    def complete_session(
        self,
        id: str,
        refactored_code: str,
        insights: str,
        complexity: Optional[int],
        performance_metrics: Dict[str, float],
    ) -> None:
        """Updates an existing session record with final results."""
        with db.atomic():
            query = RefactorHistory.update(
                status="Completed",
                refactored_code=refactored_code,
                insights=insights,
                complexity=complexity,
                avg_gpu_utilization=performance_metrics.get("avg_gpu_utilization"),
                avg_gpu_memory=performance_metrics.get("avg_gpu_memory"),
                avg_gpu_memory_used=performance_metrics.get("avg_gpu_memory_used"),
                inference_time=performance_metrics.get("inference_time"),
            ).where(RefactorHistory.id == id)
            query.execute()

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Fetches all record IDs and instructions from the refactor history.
        Ordered by the most recent first.
        """
        query = RefactorHistory.select(
            RefactorHistory.id, RefactorHistory.user_instruction
        ).order_by(RefactorHistory.created_at.desc())

        return [
            {"id": str(record.id), "user_instruction": record.user_instruction}
            for record in query
        ]

    def get_history_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a single history record by its UUID, including its orchestration logs.
        Returns a dictionary or None if not found.
        """
        try:
            record = RefactorHistory.get(RefactorHistory.id == id)
            data = model_to_dict(record)

            # Explicitly bundle logs to ensure they are returned
            data["logs"] = []
            for log in record.logs.order_by(OrchestrationLog.created_at.asc()):
                # Use recurse=False to prevent expanding the parent 'session' record redundantly
                log_dict = model_to_dict(log, recurse=False)
                # Convert datetime objects to ISO strings for reliable JSON serialization
                if log_dict.get("created_at"):
                    log_dict["created_at"] = log_dict["created_at"].isoformat()
                data["logs"].append(log_dict)

            # Also ensure the parent record's timestamp is serialized
            if data.get("created_at"):
                data["created_at"] = data["created_at"].isoformat()

            return data
        except RefactorHistory.DoesNotExist:
            return None

    def delete_history_by_id(self, id: str) -> bool:
        """
        Deletes a single history record by its UUID.
        Returns True if deleted, False if not found.
        """
        with db.atomic():
            query = RefactorHistory.delete().where(RefactorHistory.id == id)
            rows_deleted = query.execute()
            return rows_deleted > 0
