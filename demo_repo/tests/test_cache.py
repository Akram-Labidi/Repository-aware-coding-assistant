import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cache import SessionCache


class TestSessionCache(unittest.TestCase):
    def test_session_isolation(self):
        c = SessionCache()
        session1 = c.add_to_session("user1", "val1")
        session2 = c.add_to_session("user2", "val2")
        self.assertEqual(len(session2), 1, f"Expected session2 length 1, got {len(session2)} (cache leak!)")
        self.assertEqual(session2, [("user2", "val2")])


if __name__ == "__main__":
    unittest.main()
