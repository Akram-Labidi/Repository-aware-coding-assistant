"""Benchmark tasks and test suites for evaluating repository-aware coding assistants.

Real bug scenarios covering algorithms, pagination, mutable defaults,
zero division, serialization, SQL injection, and authorization.
"""

from __future__ import annotations
from typing import Dict, List
from repocortex.core.types import BenchmarkTask


BENCHMARK_TASKS: List[BenchmarkTask] = [
    BenchmarkTask(
        id="TASK-001",
        name="Off-by-One Pagination Slice Boundary",
        category="Algorithms & Data",
        description="The paginator helper in pagination.py returns one item too many on each page due to an off-by-one slice calculation. Paginate with page_size=10 should return 10 items, but returns 11.",
        buggy_files={
            "pagination.py": '''"""Pagination utilities."""

def paginate_items(items, page=1, page_size=10):
    """Paginates a list of items for 1-indexed page number."""
    if page < 1:
        page = 1
    start = (page - 1) * page_size
    # Bug: end boundary includes + 1 causing page_size + 1 items
    end = start + page_size + 1
    return items[start:end]
'''
        },
        test_file_path="tests/test_pagination.py",
        test_code='''import unittest
from pagination import paginate_items

class TestPagination(unittest.TestCase):
    def test_page_size_exact(self):
        dataset = list(range(100))
        page1 = paginate_items(dataset, page=1, page_size=10)
        self.assertEqual(len(page1), 10, f"Expected 10 items, got {len(page1)}")
        self.assertEqual(page1, list(range(0, 10)))

    def test_page_two(self):
        dataset = list(range(100))
        page2 = paginate_items(dataset, page=2, page_size=5)
        self.assertEqual(len(page2), 5, f"Expected 5 items, got {len(page2)}")
        self.assertEqual(page2, [5, 6, 7, 8, 9])

if __name__ == "__main__":
    unittest.main()
''',
        expected_fix_files={
            "pagination.py": '''"""Pagination utilities."""

def paginate_items(items, page=1, page_size=10):
    """Paginates a list of items for 1-indexed page number."""
    if page < 1:
        page = 1
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end]
'''
        },
    ),
    BenchmarkTask(
        id="TASK-002",
        name="Mutable Default Argument Cache Leak",
        category="State & Concurrency",
        description="Session store in cache.py uses a mutable default argument items=[] which leaks session items across different user calls.",
        buggy_files={
            "cache.py": '''"""Session caching module."""

class SessionCache:
    def __init__(self):
        self.name = "default_cache"

    def add_to_session(self, key, value, items=[]):
        """Adds a key-value pair to user session list."""
        items.append((key, value))
        return items
'''
        },
        test_file_path="tests/test_cache.py",
        test_code='''import unittest
from cache import SessionCache

class TestSessionCache(unittest.TestCase):
    def test_session_isolation(self):
        c = SessionCache()
        session1 = c.add_to_session("user1", "val1")
        session2 = c.add_to_session("user2", "val2")
        self.assertEqual(len(session2), 1, f"Expected isolated session of length 1, got {len(session2)}")
        self.assertEqual(session2, [("user2", "val2")])

if __name__ == "__main__":
    unittest.main()
''',
        expected_fix_files={
            "cache.py": '''"""Session caching module."""

class SessionCache:
    def __init__(self):
        self.name = "default_cache"

    def add_to_session(self, key, value, items=None):
        """Adds a key-value pair to user session list."""
        if items is None:
            items = []
        items.append((key, value))
        return items
'''
        },
    ),
    BenchmarkTask(
        id="TASK-003",
        name="Zero Division on Empty Dataset Aggregation",
        category="Numerical & Math",
        description="Statistical calculator in stats.py crashes with ZeroDivisionError when compute_average is passed an empty list.",
        buggy_files={
            "stats.py": '''"""Statistical utilities."""

def compute_average(numbers):
    """Computes mean average of numbers list."""
    return sum(numbers) / len(numbers)
'''
        },
        test_file_path="tests/test_stats.py",
        test_code='''import unittest
from stats import compute_average

class TestStats(unittest.TestCase):
    def test_average_non_empty(self):
        self.assertEqual(compute_average([10, 20, 30]), 20.0)

    def test_average_empty(self):
        self.assertEqual(compute_average([]), 0.0)

if __name__ == "__main__":
    unittest.main()
''',
        expected_fix_files={
            "stats.py": '''"""Statistical utilities."""

def compute_average(numbers):
    """Computes mean average of numbers list."""
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)
'''
        },
    ),
    BenchmarkTask(
        id="TASK-004",
        name="Datetime JSON Serialization TypeError",
        category="API & Serialization",
        description="Serializer in serializer.py crashes when serializing objects containing datetime instances because json.dumps lacks default=str.",
        buggy_files={
            "serializer.py": '''"""JSON serialization helpers."""
import json

def serialize_payload(data):
    """Serializes data dictionary into JSON string."""
    return json.dumps(data)
'''
        },
        test_file_path="tests/test_serializer.py",
        test_code='''import unittest
import json
from datetime import datetime
from serializer import serialize_payload

class TestSerializer(unittest.TestCase):
    def test_serialize_with_datetime(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        payload = {"timestamp": now, "status": "ok"}
        out = serialize_payload(payload)
        parsed = json.loads(out)
        self.assertIn("2026", parsed["timestamp"])

if __name__ == "__main__":
    unittest.main()
''',
        expected_fix_files={
            "serializer.py": '''"""JSON serialization helpers."""
import json

def serialize_payload(data):
    """Serializes data dictionary into JSON string."""
    return json.dumps(data, default=str)
'''
        },
    ),
    BenchmarkTask(
        id="TASK-005",
        name="Exponential Retry Backoff Overflow",
        category="Resilience & Networking",
        description="Retry calculation in retry.py calculates delay = base_delay * (2 ** attempt) without a maximum delay cap, leading to massive delays.",
        buggy_files={
            "retry.py": '''"""Retry backoff calculator."""

def calculate_backoff(attempt, base_delay=1.0, max_delay=60.0):
    """Calculates exponential backoff delay."""
    delay = base_delay * (2 ** attempt)
    return delay
'''
        },
        test_file_path="tests/test_retry.py",
        test_code='''import unittest
from retry import calculate_backoff

class TestRetry(unittest.TestCase):
    def test_small_attempt(self):
        self.assertEqual(calculate_backoff(2, base_delay=1.0, max_delay=60.0), 4.0)

    def test_capped_at_max(self):
        self.assertEqual(calculate_backoff(10, base_delay=1.0, max_delay=60.0), 60.0)

if __name__ == "__main__":
    unittest.main()
''',
        expected_fix_files={
            "retry.py": '''"""Retry backoff calculator."""

def calculate_backoff(attempt, base_delay=1.0, max_delay=60.0):
    """Calculates exponential backoff delay."""
    delay = min(max_delay, base_delay * (2 ** attempt))
    return delay
'''
        },
    ),
    BenchmarkTask(
        id="TASK-006",
        name="Role-based Authorization Bypass Flaw",
        category="Security & Access Control",
        description="Authorization check in auth.py allows non-admin users to access admin resources because it checks user.role != 'guest' instead of user.role == 'admin'.",
        buggy_files={
            "auth.py": '''"""Authorization service."""

class User:
    def __init__(self, role):
        self.role = role

def can_access_admin_panel(user):
    """Checks if user has permission to access administration settings."""
    if user.role != 'guest':
        return True
    return False
'''
        },
        test_file_path="tests/test_auth.py",
        test_code='''import unittest
from auth import User, can_access_admin_panel

class TestAuth(unittest.TestCase):
    def test_admin_access(self):
        self.assertTrue(can_access_admin_panel(User("admin")))

    def test_member_denied(self):
        self.assertFalse(can_access_admin_panel(User("member")))

    def test_guest_denied(self):
        self.assertFalse(can_access_admin_panel(User("guest")))

if __name__ == "__main__":
    unittest.main()
''',
        expected_fix_files={
            "auth.py": '''"""Authorization service."""

class User:
    def __init__(self, role):
        self.role = role

def can_access_admin_panel(user):
    """Checks if user has permission to access administration settings."""
    if user.role == 'admin':
        return True
    return False
'''
        },
    ),
]
