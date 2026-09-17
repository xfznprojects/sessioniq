"""Retrieval metrics.

Every function takes a ranked list of retrieved file names and the set of file
names that are actually relevant for that question. Ranking is by descending
retrieval score; anything the retriever scored at zero is not counted as
retrieved at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


def _top_k(retrieved: list[str], k: int) -> list[str]:
    return retrieved[: max(k, 0)]


def hit_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """1.0 when at least one relevant file is in the top k, else 0.0."""
    if not relevant:
        return 0.0
    return 1.0 if set(_top_k(retrieved, k)) & relevant else 0.0


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Share of the relevant files that appear in the top k."""
    if not relevant:
        return 0.0
    return len(set(_top_k(retrieved, k)) & relevant) / len(relevant)


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Share of the top k slots that hold a relevant file.

    Divided by k rather than by the number of results actually returned, so the
    figure stays comparable between configurations that return different counts.
    """
    if k <= 0:
        return 0.0
    return len(set(_top_k(retrieved, k)) & relevant) / k


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """1 / rank of the first relevant file; 0.0 when none is retrieved."""
    if not relevant:
        return 0.0
    for rank, name in enumerate(retrieved, start=1):
        if name in relevant:
            return 1.0 / rank
    return 0.0


def percentile(values: list[float], fraction: float) -> float:
    """Linear-interpolated percentile of a sample, in the 0..1 range."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass
class CaseResult:
    question: str
    category: str
    expected: tuple[str, ...]
    retrieved: list[str]
    top_scores: list[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "category": self.category,
            "expected": list(self.expected),
            "retrieved": self.retrieved,
            "top_scores": [round(score, 6) for score in self.top_scores],
        }


@dataclass
class MetricSummary:
    cases: int
    hit: dict[int, float]
    recall: dict[int, float]
    precision: dict[int, float]
    mrr: float

    def as_dict(self) -> dict:
        return {
            "cases": self.cases,
            "hit_at_k": {str(k): round(v, 4) for k, v in self.hit.items()},
            "recall_at_k": {str(k): round(v, 4) for k, v in self.recall.items()},
            "precision_at_k": {str(k): round(v, 4) for k, v in self.precision.items()},
            "mrr": round(self.mrr, 4),
        }


def summarize(results: list[CaseResult], k_values: tuple[int, ...] = (1, 3, 5)) -> MetricSummary:
    """Average each metric across cases."""
    if not results:
        return MetricSummary(0, dict.fromkeys(k_values, 0.0), {}, {}, 0.0)  # type: ignore[arg-type]
    return MetricSummary(
        cases=len(results),
        hit={
            k: mean(hit_at_k(r.retrieved, set(r.expected), k) for r in results) for k in k_values
        },
        recall={
            k: mean(recall_at_k(r.retrieved, set(r.expected), k) for r in results) for k in k_values
        },
        precision={
            k: mean(precision_at_k(r.retrieved, set(r.expected), k) for r in results)
            for k in k_values
        },
        mrr=mean(reciprocal_rank(r.retrieved, set(r.expected)) for r in results),
    )
