import unittest
import sys
from pathlib import Path

# Add parent directory to path so demo_repo modules import cleanly
sys.path.insert(0, str(Path(__file__).parent.parent))

from calculator import add, divide, DiscountCalculator


class TestCalculator(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-1, 1), 0)

    def test_divide(self):
        self.assertEqual(divide(10, 2), 5.0)
        with self.assertRaises(ValueError):
            divide(10, 0)

    def test_discount_calculator(self):
        calc = DiscountCalculator(default_tax_rate=0.10)
        # 100 with gold discount (20%) -> 80 * 1.10 = 88.0
        self.assertAlmostEqual(calc.calculate_final_price(100.0, "gold"), 88.0)


if __name__ == "__main__":
    unittest.main()
