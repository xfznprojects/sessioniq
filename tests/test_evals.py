"""Tests for the retrieval evaluation harness.

These cover the metric arithmetic and the integrity of the labeled sets. The
full evaluation needs a generated audio corpus, so it runs as a separate
command (``python evals/run.py``) rather than inside the unit suite.
"""

from __future__ import annotations

import pytest

from evals.golden_set import DEMO_CORPUS, GOLDEN_SET
from evals.harness import _effective_limit
from evals.metrics import (
    CaseResult,
    hit_at_k,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    summarize,
)
from evals.tool_set import TOOL_SET
from sessioniq.tools import FIELD_ACCESSORS

RETRIEVED = ["a.wav", "b.wav", "c.wav", "d.wav"]


class TestRankingMetrics:
    def test_hit_at_k_respects_the_window(self):
        assert hit_at_k(RETRIEVED, {"b.wav"}, 1) == 0.0
        assert hit_at_k(RETRIEVED, {"b.wav"}, 2) == 1.0
        assert hit_at_k(RETRIEVED, {"b.wav"}, 4) == 1.0

    def test_hit_is_zero_when_nothing_expected_is_retrieved(self):
        assert hit_at_k(RETRIEVED, {"z.wav"}, 4) == 0.0

    def test_recall_is_the_share_of_relevant_files_found(self):
        assert recall_at_k(RETRIEVED, {"a.wav", "z.wav"}, 4) == 0.5
        assert recall_at_k(RETRIEVED, {"a.wav", "b.wav"}, 2) == 1.0
        assert recall_at_k(RETRIEVED, {"c.wav", "d.wav"}, 1) == 0.0

    def test_precision_divides_by_k_not_by_result_count(self):
        # Only two results returned, one relevant, but k is 4.
        assert precision_at_k(["a.wav", "z.wav"], {"a.wav"}, 4) == 0.25

    def test_reciprocal_rank_uses_the_first_relevant_position(self):
        assert reciprocal_rank(RETRIEVED, {"a.wav"}) == 1.0
        assert reciprocal_rank(RETRIEVED, {"c.wav"}) == pytest.approx(1 / 3)

    def test_reciprocal_rank_is_zero_when_absent(self):
        assert reciprocal_rank(RETRIEVED, {"z.wav"}) == 0.0

    def test_empty_expectation_never_scores(self):
        assert hit_at_k(RETRIEVED, set(), 4) == 0.0
        assert recall_at_k(RETRIEVED, set(), 4) == 0.0
        assert reciprocal_rank(RETRIEVED, set()) == 0.0


class TestPercentile:
    def test_interpolates_between_neighbours(self):
        assert percentile([1, 2, 3, 4], 0.5) == pytest.approx(2.5)

    def test_returns_edges_for_extremes(self):
        assert percentile([1, 2, 3, 4], 0.0) == 1
        assert percentile([1, 2, 3, 4], 1.0) == 4

    def test_single_value_and_empty_input(self):
        assert percentile([7.0], 0.95) == 7.0
        assert percentile([], 0.5) == 0.0


class TestSummarize:
    def _case(self, retrieved, expected, category="x"):
        return CaseResult(
            question="q", category=category, expected=tuple(expected), retrieved=list(retrieved)
        )

    def test_averages_across_cases(self):
        results = [
            self._case(["a.wav"], ["a.wav"]),
            self._case(["z.wav"], ["a.wav"]),
        ]
        summary = summarize(results)
        assert summary.cases == 2
        assert summary.hit[1] == pytest.approx(0.5)
        assert summary.mrr == pytest.approx(0.5)

    def test_empty_result_set_summarizes_to_zero(self):
        summary = summarize([])
        assert summary.cases == 0
        assert summary.mrr == 0.0
        assert all(value == 0.0 for value in summary.hit.values())


class TestAggregateLimitExpansion:
    """`is_aggregate_query` widens the candidate window for whole-library questions."""

    def _candidates(self) -> list[str]:
        return ["a", "b", "c", "d", "e"]

    def test_aggregate_questions_widen_the_window(self):
        assert _effective_limit("list all the audio tracks", self._candidates(), 4) == 5

    def test_interrogatives_are_treated_as_aggregate(self):
        # "which" and "how" are aggregate hints, so ordinary-looking questions
        # also return every candidate that scored above zero.
        for question in ("which track is the loudest?", "how many tracks are there?"):
            assert _effective_limit(question, self._candidates(), 4) == 5

    def test_questions_without_hint_words_keep_the_requested_limit(self):
        assert _effective_limit("describe the sidechain on the pads", self._candidates(), 4) == 4


class TestGoldenSetIntegrity:
    def test_every_expected_file_is_in_the_demo_corpus(self):
        known = set(DEMO_CORPUS)
        unknown = {
            name for case in GOLDEN_SET for name in case.expected if name not in known
        }
        assert not unknown, f"golden set names files the demo corpus does not create: {unknown}"

    def test_questions_are_unique(self):
        questions = [case.question for case in GOLDEN_SET]
        assert len(questions) == len(set(questions))

    def test_every_case_has_an_expectation_and_a_category(self):
        for case in GOLDEN_SET:
            assert case.expected, f"{case.question!r} has no expected files"
            assert case.category

    def test_project_scoped_cases_name_a_project_in_the_corpus(self):
        projects = {name.split("/")[0] for name in DEMO_CORPUS}
        for case in GOLDEN_SET:
            if case.project:
                assert case.project in projects, f"{case.question!r} targets {case.project}"

    def test_corpus_has_no_duplicate_entries(self):
        assert len(DEMO_CORPUS) == len(set(DEMO_CORPUS))


class TestToolSetIntegrity:
    def test_every_expected_file_is_in_the_demo_corpus(self):
        known = set(DEMO_CORPUS)
        unknown = {
            name for case in TOOL_SET for name in case.expected_any if name not in known
        }
        assert not unknown, f"tool set names files the demo corpus does not create: {unknown}"

    def test_fields_are_ones_the_toolbox_exposes(self):
        for case in TOOL_SET:
            assert case.field in FIELD_ACCESSORS

    def test_ops_are_comparable(self):
        for case in TOOL_SET:
            assert case.op in {"min", "max"}

    def test_arguments_match_the_case_metadata(self):
        for case in TOOL_SET:
            assert case.arguments["field"] == case.field
            assert case.arguments["op"] == case.op
