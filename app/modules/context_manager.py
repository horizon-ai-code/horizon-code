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
    id = peewee.UUIDField()
    user_instruction = peewee.TextField()
    original_code = peewee.TextField()
    refactored_code = peewee.TextField()
    insights = peewee.TextField()
    complexity = peewee.IntegerField()
    created_at = peewee.DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = db


# 3. Create the Context Manager
class DatabaseManager:
    def __init__(self):
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Safely creates the table when the app starts if it doesn't exist."""
        db.connect(reuse_if_open=True)
        db.create_tables([RefactorHistory], safe=True)
        db.close()

    def save_history(
        self,
        id: str,
        instruction: str,
        original: str,
        refactored: str,
        insights: str,
        complexity: int,
    ) -> None:
        """
        Saves a completed orchestration cycle to SQLite.
        db.atomic() acts as a context manager to ensure the transaction
        is safely committed, or rolled back if anything fails mid-write.
        """
        with db.atomic():
            RefactorHistory.create(
                id=id,
                user_instruction=instruction,
                original_code=original,
                refactored_code=refactored,
                insights=insights,
                complexity=complexity,
            )

    def get_history(self) -> List[str]:
        """
        Fetches all record IDs from the refactor history.
        """
        query = RefactorHistory.select(RefactorHistory.id)
        return [str(record.id) for record in query]


    def get_history_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a single history record by its UUID.
        Returns a dictionary or None if not found.
        """
        try:
            record = RefactorHistory.get(RefactorHistory.id == id)
            return model_to_dict(record)
        except RefactorHistory.DoesNotExist:
            return None
