import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stats import compute_average, compute_variance


class TestStats(unittest.TestCase):
    def test_average_non_empty(self):
        self.assertEqual(compute_average([10.0, 20.0, 30.0]), 20.0)

    def test_average_empty(self):
        self.assertEqual(compute_average([]), 0.0)

    def test_variance(self):
        self.assertAlmostEqual(compute_variance([10.0, 20.0, 30.0]), 100.0)


if __name__ == "__main__":
    unittest.main()
