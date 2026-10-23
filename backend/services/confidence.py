from __future__ import annotations

from collections.abc import Iterable


def mock_confidence(probabilities: Iterable[float]) -> float:
    """Use the mock adapter's highest simulated choice probability as its confidence."""
    values = tuple(float(value) for value in probabilities)
    if not values:
        return 0.0
    return max(0.0, min(1.0, max(values)))
