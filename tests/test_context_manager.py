import unittest
import uuid
import peewee
import sys
from unittest.mock import patch, MagicMock

# Create an in-memory database for testing
test_db = peewee.SqliteDatabase(':memory:')

# Mock DB_PATH to avoid creating history.db in tests
with patch('app.modules.context_manager.db', test_db):
    from app.modules.context_manager import DatabaseManager, RefactorHistory, OrchestrationLog

class TestContextManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Bind models to the test database
        RefactorHistory._meta.database = test_db
        OrchestrationLog._meta.database = test_db
        test_db.connect(reuse_if_open=True)
        test_db.create_tables([RefactorHistory, OrchestrationLog], safe=True)

    def setUp(self):
        self.db_manager = DatabaseManager()
        # Ensure we start with a clean slate for each test
        RefactorHistory.delete().execute()
        OrchestrationLog.delete().execute()

    def test_session_status_default_processing(self):
        """Test that a newly created session has status 'Processing'."""
        session_id = str(uuid.uuid4())
        self.db_manager.create_session(session_id, "instruction", "original code")
        
        session = RefactorHistory.get(RefactorHistory.id == session_id)
        self.assertTrue(hasattr(session, 'status'), "RefactorHistory model should have a 'status' field")
        self.assertEqual(session.status, "Processing")

    def test_mark_as_halted(self):
        """Test that mark_as_halted updates status to 'Halted'."""
        session_id = str(uuid.uuid4())
        self.db_manager.create_session(session_id, "instruction", "original code")
        
        # This method should be implemented in Task 1
        self.assertTrue(hasattr(self.db_manager, 'mark_as_halted'), "DatabaseManager should have 'mark_as_halted' method")
        self.db_manager.mark_as_halted(session_id)
        
        session = RefactorHistory.get(RefactorHistory.id == session_id)
        self.assertEqual(session.status, "Halted")

    def test_complete_session_updates_status(self):
        """Test that complete_session updates status to 'Completed'."""
        session_id = str(uuid.uuid4())
        self.db_manager.create_session(session_id, "instruction", "original code")
        
        self.db_manager.complete_session(session_id, "refactored", "insights", 10, {})
        
        session = RefactorHistory.get(RefactorHistory.id == session_id)
        self.assertEqual(session.status, "Completed")
        self.assertEqual(session.refactored_code, "refactored")

if __name__ == '__main__':
    unittest.main()
