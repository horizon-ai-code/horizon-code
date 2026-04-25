import datetime
from typing import Any, Dict, List, Optional

import peewee
from playhouse.shortcuts import model_to_dict

from app.utils.paths import DB_DIR, DB_PATH

# 1. Initialize the SQLite database connection
db = peewee.SqliteDatabase(DB_PATH, pragmas={"journal_mode": "wal", "foreign_keys": 1})


# 2. Define the Database Schema
class RefactorHistory(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    status = peewee.CharField(default="Processing")
    exit_status = peewee.CharField(null=True) # SUCCESS, ABORT_STRATEGY, etc.
    user_instruction = peewee.TextField()
    original_code = peewee.TextField()
    refactored_code = peewee.TextField(null=True)
    insights = peewee.TextField(null=True)
    final_intent = peewee.TextField(null=True) # Stores JSON
    final_plan = peewee.TextField(null=True) # Stores JSON
    total_outer_loops = peewee.IntegerField(default=0)
    total_inner_loops = peewee.IntegerField(default=0)
    original_complexity = peewee.IntegerField(null=True)
    refactored_complexity = peewee.IntegerField(null=True)
    planner_model = peewee.CharField(null=True)
    generator_model = peewee.CharField(null=True)
    judge_model = peewee.CharField(null=True)
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
    content = peewee.TextField(null=True) # Standardized to hold JSON payloads
    phase = peewee.IntegerField(null=True)
    outer_loop = peewee.IntegerField(default=0)
    inner_loop = peewee.IntegerField(default=0)
    created_at = peewee.DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = db


# 3. Create the Context Manager
class DatabaseManager:
    def __init__(self):
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Safely creates the tables and adds missing columns if they don't exist."""
        db.connect(reuse_if_open=True)
        db.create_tables([RefactorHistory, OrchestrationLog], safe=True)
        
        # Simple migration for SQLite to add new columns
        columns = {
            "refactorhistory": ["exit_status", "final_intent", "final_plan", "total_outer_loops", "total_inner_loops"],
            "orchestrationlog": ["phase", "outer_loop", "inner_loop"]
        }
        
        for table, cols in columns.items():
            existing_cols = [c.name for c in db.get_columns(table)]
            for col in cols:
                if col not in existing_cols:
                    print(f"Adding column {col} to table {table}...")
                    if col in ["total_outer_loops", "total_inner_loops", "outer_loop", "inner_loop", "phase"]:
                        db.execute_sql(f'ALTER TABLE {table} ADD COLUMN {col} INTEGER DEFAULT 0')
                    else:
                        db.execute_sql(f'ALTER TABLE {table} ADD COLUMN {col} TEXT')
        
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
        self, 
        session_id: str, 
        role: str, 
        status: str, 
        content: Optional[str] = None,
        phase: Optional[int] = None,
        outer_loop: int = 0,
        inner_loop: int = 0
    ) -> None:
        """Persists a single orchestration step/log to the database."""
        with db.atomic():
            OrchestrationLog.create(
                session=session_id,
                role=role,
                status=status,
                content=content,
                phase=phase,
                outer_loop=outer_loop,
                inner_loop=inner_loop
            )

    def mark_as_halted(self, id: str) -> None:
        """Updates session status to Halted."""
        with db.atomic():
            RefactorHistory.update(status="Halted", exit_status="ABORTED").where(
                RefactorHistory.id == id
            ).execute()

    def complete_session(
        self,
        id: str,
        refactored_code: str,
        insights: str,
        original_complexity: Optional[int],
        refactored_complexity: Optional[int],
        performance_metrics: Dict[str, float],
        exit_status: str = "SUCCESS",
        final_intent: Optional[str] = None,
        final_plan: Optional[str] = None,
        outer_loops: int = 0,
        inner_loops: int = 0,
        planner_model: Optional[str] = None,
        generator_model: Optional[str] = None,
        judge_model: Optional[str] = None,
    ) -> None:
        """Updates an existing session record with final results."""
        with db.atomic():
            query = RefactorHistory.update(
                status="Completed",
                exit_status=exit_status,
                refactored_code=refactored_code,
                insights=insights,
                final_intent=final_intent,
                final_plan=final_plan,
                total_outer_loops=outer_loops,
                total_inner_loops=inner_loops,
                original_complexity=original_complexity,
                refactored_complexity=refactored_complexity,
                planner_model=planner_model,
                generator_model=generator_model,
                judge_model=judge_model,
                avg_gpu_utilization=performance_metrics.get("avg_gpu_utilization"),
                avg_gpu_memory=performance_metrics.get("avg_gpu_memory"),
                avg_gpu_memory_used=performance_metrics.get("avg_gpu_memory_used"),
                inference_time=performance_metrics.get("inference_time"),
            ).where(RefactorHistory.id == id)
            query.execute()

    def get_history(self) -> List[Dict[str, Any]]:
        """Fetches all history stubs."""
        query = RefactorHistory.select().order_by(RefactorHistory.created_at.desc())
        return [model_to_dict(h) for h in query]

    def get_history_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Fetches detailed history for a session."""
        try:
            h = RefactorHistory.get(RefactorHistory.id == id)
            return model_to_dict(h, backrefs=True)
        except RefactorHistory.DoesNotExist:
            return None

    def delete_history_by_id(self, id: str) -> bool:
        """
        Deletes a history record and its associated logs.
        Returns True if deleted, False if not found.
        """
        with db.atomic():
            query = RefactorHistory.delete().where(RefactorHistory.id == id)
            rows_deleted = query.execute()
            return rows_deleted > 0
