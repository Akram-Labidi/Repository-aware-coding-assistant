"""Statistical computation module."""

def compute_average(numbers: list[float]) -> float:
    """Computes mean average of numbers list."""
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)

def compute_variance(numbers: list[float]) -> float:
    """Computes sample variance."""
    if len(numbers) <= 1:
        return 0.0
    avg = compute_average(numbers)
    return sum((x - avg) ** 2 for x in numbers) / (len(numbers) - 1)
