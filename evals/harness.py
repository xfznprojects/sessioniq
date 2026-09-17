"""Retrieval evaluation harness.

Loads the generated demo library into a retriever, runs every question in the
golden set, and reports retrieval quality plus latency.

The weight ablation re-scores candidates from the same component values the
production retriever computes, rather than calling ``search()`` once per
configuration. Before trusting those numbers the harness re-ranks the library
under the production weights and asserts the order matches what ``search()``
actually returns, so the ablation cannot silently drift away from the code it
claims to describe.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from evals.golden_set import GOLDEN_SET, GoldenCase
from evals.metrics import CaseResult, MetricSummary, percentile, summarize
from evals.tool_set import TOOL_SET
from sessioniq.models import ProjectAsset
from sessioniq.retrieval import (
    METADATA_NORM,
    InMemoryRetriever,
    _inverse_document_frequency,  # noqa: PLC2701 - internal harness, not shipped API
    _metadata_score,
    _weighted_cosine,
    content_tokens,
    expand_query_tokens,
    is_aggregate_query,
)
from sessioniq.tools import LibraryToolbox

K_VALUES = (1, 3, 5)
RANK_LIMIT = 10

# (name, lexical, metadata, vector)
WeightConfig = tuple[str, float, float, float]

BASELINE_LEXICAL_METADATA: WeightConfig = ("production (lexical+metadata)", 0.70, 0.30, 0.0)
BASELINE_WITH_VECTOR: WeightConfig = ("production (with vector)", 0.55, 0.25, 0.20)

ABLATION: tuple[WeightConfig, ...] = (
    ("lexical only", 1.00, 0.00, 0.00),
    ("metadata only", 0.00, 1.00, 0.00),
    ("lexical heavy", 0.85, 0.15, 0.00),
    BASELINE_LEXICAL_METADATA,
    ("balanced", 0.60, 0.40, 0.00),
    ("metadata heavy", 0.40, 0.60, 0.00),
)


def qualified(asset: ProjectAsset) -> str:
    """Project-qualified file name, unique across the demo corpus."""
    return f"{asset.project_name}/{asset.file_name}"


@dataclass
class AblationRow:
    name: str
    summary: MetricSummary
    case_results: list[CaseResult] = field(default_factory=list)


@dataclass
class ToolCaseResult:
    question: str
    field: str
    op: str
    expected: tuple[str, ...]
    actual: str | None
    passed: bool


@dataclass
class EvalReport:
    corpus_size: int
    projects: int
    vector_enabled: bool
    baseline: MetricSummary
    by_category: dict[str, MetricSummary]
    ablation: list[AblationRow]
    latency_ms: dict[str, float]
    weak_cases: list[dict]
    unretrieved: int
    tool_results: list[ToolCaseResult]
    faithfulness_checked: int
    faithfulness_mismatches: list[str]


def _components(
    retriever: InMemoryRetriever,
    query: str,
    project_name: str | None,
) -> tuple[list[ProjectAsset], dict[str, tuple[float, float, float]]]:
    """Per-candidate (lexical, metadata, vector) values, as production computes them."""
    candidates = [
        asset
        for asset in retriever.assets
        if project_name is None
        or asset.project_name == project_name
        or asset.project_name.startswith(project_name + "/")
    ]
    if not candidates:
        return [], {}

    query_counts = expand_query_tokens(content_tokens(query))
    doc_counts = {
        asset.id: Counter(content_tokens(asset.cached_search_text())) for asset in candidates
    }
    idf = _inverse_document_frequency(doc_counts.values())
    semantic = retriever._semantic_scores(query, candidates)

    values = {
        asset.id: (
            _weighted_cosine(query_counts, doc_counts[asset.id], idf),
            min(_metadata_score(query, asset) / METADATA_NORM, 1.0),
            semantic.get(asset.id, 0.0),
        )
        for asset in candidates
    }
    return candidates, values


def _rank(
    candidates: list[ProjectAsset],
    values: dict[str, tuple[float, float, float]],
    weights: tuple[float, float, float],
    limit: int,
) -> list[tuple[ProjectAsset, float]]:
    lexical_weight, metadata_weight, vector_weight = weights
    scored = []
    for asset in candidates:
        lexical, metadata, vector = values[asset.id]
        score = (
            lexical_weight * lexical + metadata_weight * metadata + vector_weight * vector
        )
        if score > 0:
            scored.append((asset, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def _effective_limit(query: str, candidates: list[ProjectAsset], limit: int) -> int:
    # Aggregate questions intentionally widen the candidate window in production.
    return max(limit, len(candidates)) if is_aggregate_query(query) else limit


def _run_case(
    retriever: InMemoryRetriever,
    case: GoldenCase,
    weights: tuple[float, float, float],
    limit: int,
) -> CaseResult:
    candidates, values = _components(retriever, case.question, case.project)
    effective = _effective_limit(case.question, candidates, limit)
    ranked = _rank(candidates, values, weights, effective)
    return CaseResult(
        question=case.question,
        category=case.category,
        expected=case.expected,
        retrieved=[qualified(asset) for asset, _ in ranked],
        top_scores=[score for _, score in ranked],
    )


def _check_faithfulness(
    retriever: InMemoryRetriever, weights: tuple[float, float, float]
) -> tuple[int, list[str]]:
    """The re-ranked order must match what search() returns under these weights."""
    checked = 0
    mismatches: list[str] = []
    for case in GOLDEN_SET:
        candidates, values = _components(retriever, case.question, case.project)
        if not candidates:
            continue
        effective = _effective_limit(case.question, candidates, RANK_LIMIT)
        mine = [qualified(asset) for asset, _ in _rank(candidates, values, weights, effective)]
        actual = [
            qualified(source.asset)
            for source in retriever.search(
                case.question, limit=RANK_LIMIT, project_name=case.project
            )
            if source.score > 0
        ][:effective]
        if mine:
            checked += 1
            if mine != actual:
                mismatches.append(f"{case.question!r}: harness={mine[:3]} search={actual[:3]}")
    return checked, mismatches


def _latency(retriever: InMemoryRetriever, repeats: int = 5) -> dict[str, float]:
    samples: list[float] = []
    for _ in range(repeats):
        for case in GOLDEN_SET:
            started = time.perf_counter()
            retriever.search(case.question, limit=RANK_LIMIT, project_name=case.project)
            samples.append((time.perf_counter() - started) * 1000)
    return {
        "calls": len(samples),
        "mean": round(sum(samples) / len(samples), 3),
        "p50": round(percentile(samples, 0.50), 3),
        "p95": round(percentile(samples, 0.95), 3),
        "max": round(max(samples), 3),
    }


def run_tool_eval(assets: list[ProjectAsset]) -> list[ToolCaseResult]:
    """Execute each computable question's tool call and check the winner."""
    toolbox = LibraryToolbox(assets)
    by_id = {asset.id: qualified(asset) for asset in assets}
    results: list[ToolCaseResult] = []
    for case in TOOL_SET:
        payload = json.loads(toolbox.execute(case.tool, dict(case.arguments)))
        winner = (payload.get("asset") or {}).get("asset_id")
        actual = by_id.get(winner) if winner else None
        results.append(
            ToolCaseResult(
                question=case.question,
                field=case.field,
                op=case.op,
                expected=case.expected_any,
                actual=actual,
                passed=actual in case.expected_any,
            )
        )
    return results


def run_eval(retriever: InMemoryRetriever, vector_enabled: bool) -> EvalReport:
    """Evaluate an already-populated retriever against the golden set."""
    baseline_weights = BASELINE_WITH_VECTOR if vector_enabled else BASELINE_LEXICAL_METADATA

    case_results = [
        _run_case(retriever, case, baseline_weights[1:], RANK_LIMIT) for case in GOLDEN_SET
    ]
    baseline = summarize(case_results, K_VALUES)

    grouped: dict[str, list[CaseResult]] = defaultdict(list)
    for result in case_results:
        grouped[result.category].append(result)
    by_category = {name: summarize(items, K_VALUES) for name, items in sorted(grouped.items())}

    rows: list[AblationRow] = []
    configs = list(ABLATION)
    if vector_enabled:
        configs.insert(0, BASELINE_WITH_VECTOR)
    for name, *weights in configs:
        if not vector_enabled and weights[2]:
            continue
        results = [_run_case(retriever, case, tuple(weights), RANK_LIMIT) for case in GOLDEN_SET]
        rows.append(
            AblationRow(name=name, summary=summarize(results, K_VALUES), case_results=results)
        )

    weak_cases = []
    unretrieved = 0
    for result in case_results:
        expected = set(result.expected)
        rank = next(
            (i for i, name in enumerate(result.retrieved, start=1) if name in expected),
            None,
        )
        if rank == 1:
            continue
        if rank is None:
            unretrieved += 1
        weak_cases.append(
            {
                "question": result.question,
                "category": result.category,
                "expected": list(result.expected),
                "retrieved": result.retrieved[:5],
                "first_relevant_rank": rank,
                "scores": [round(score, 4) for score in result.top_scores[:5]],
            }
        )

    checked, mismatches = _check_faithfulness(retriever, baseline_weights[1:])

    return EvalReport(
        corpus_size=len(retriever.assets),
        projects=len({asset.project_name for asset in retriever.assets}),
        vector_enabled=vector_enabled,
        baseline=baseline,
        by_category=by_category,
        ablation=rows,
        latency_ms=_latency(retriever),
        weak_cases=weak_cases,
        unretrieved=unretrieved,
        tool_results=run_tool_eval(retriever.assets),
        faithfulness_checked=checked,
        faithfulness_mismatches=mismatches,
    )
