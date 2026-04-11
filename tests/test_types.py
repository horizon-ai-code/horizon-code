import unittest
from pydantic import ValidationError
from app.utils.types import HaltRequest


class TestTypes(unittest.TestCase):
    def test_halt_request_valid(self):
        """Test that HaltRequest can be instantiated with valid data."""
        data = {"type": "halt"}
        halt_req = HaltRequest(**data)
        self.assertEqual(halt_req.type, "halt")

    def test_halt_request_invalid_type(self):
        """Test that HaltRequest fails with an invalid type."""
        data = {"type": "not_halt"}
        with self.assertRaises(ValidationError):
            HaltRequest(**data)

    def test_halt_request_missing_type(self):
        """Test that HaltRequest fails if 'type' is missing."""
        data = {}
        with self.assertRaises(ValidationError):
            HaltRequest(**data)


if __name__ == '__main__':
    unittest.main()
