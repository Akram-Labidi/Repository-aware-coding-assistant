"""Sample calculator module for demoing RepoCortex."""

def add(a: float, b: float) -> float:
    """Adds two numbers."""
    return a + b

def divide(a: float, b: float) -> float:
    """Divides a by b with safe zero checking."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

class DiscountCalculator:
    """Calculates customer discounts based on loyalty tier."""

    TIERS = {
        "bronze": 0.05,
        "silver": 0.10,
        "gold": 0.20,
    }

    def __init__(self, default_tax_rate: float = 0.08):
        self.tax_rate = default_tax_rate

    def calculate_final_price(self, original_price: float, tier: str) -> float:
        discount = self.TIERS.get(tier.lower(), 0.0)
        discounted = original_price * (1.0 - discount)
        return discounted * (1.0 + self.tax_rate)
