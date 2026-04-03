import datetime
from typing import Any, Dict, List

import peewee
from playhouse.shortcuts import model_to_dict

from app.utils.paths import DB_DIR, DB_PATH

# 1. Initialize the SQLite database connection
# WAL mode (Write-Ahead Logging) is excellent for handling concurrent WebSocket requests]

DB_DIR.mkdir(parents=True, exist_ok=True)

db = peewee.SqliteDatabase(DB_PATH, pragmas={"journal_mode": "wal"})


# 2. Define the Database Schema
class RefactorHistory(peewee.Model):
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
                user_instruction=instruction,
                original_code=original,
                refactored_code=refactored,
                insights=insights,
                complexity=complexity,
            )

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Fetches all history for a specific session ID and converts it to dictionaries
        so FastAPI can instantly serialize it to JSON.
        """
        query = RefactorHistory.select()

        # model_to_dict automatically strips Peewee metadata and returns raw Python dicts
        return [model_to_dict(record) for record in query]
