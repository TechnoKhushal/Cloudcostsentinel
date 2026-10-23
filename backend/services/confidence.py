from __future__ import annotations

from collections.abc import Iterable


def normalized_confidence(probabilities: Iterable[float]) -> float:
    """Score the strongest choice relative to uniform probability, normalized to 0–1."""
    values = tuple(float(value) for value in probabilities)
    if not values:
        return 0.0
    if len(values) == 1:
        return 1.0
    score = (len(values) * max(values) - 1.0) / (len(values) - 1.0)
    return max(0.0, min(1.0, score))
