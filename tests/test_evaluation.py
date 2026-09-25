from __future__ import annotations

import unittest

from citations import validate_citations
from evaluation import (
    EvaluationDataError,
    EvaluationDataset,
    RetrievalResult,
    evaluate_dataset,
    metric_at_k,
)


class EvaluationMetricTests(unittest.TestCase):
    def test_duplicate_hits_are_counted_once(self) -> None:
        metrics = metric_at_k(["gold", "gold", "noise"], {"gold": 1}, 3)
        self.assertEqual(metrics["recall@3"], 1.0)
        self.assertEqual(metrics["reciprocal_rank"], 1.0)

    def test_graded_ndcg_penalizes_relevant_item_in_wrong_order(self) -> None:
        ideal = metric_at_k(["high", "low"], {"high": 3, "low": 1}, 2)
        reversed_order = metric_at_k(["low", "high"], {"high": 3, "low": 1}, 2)
        self.assertEqual(ideal["ndcg@2"], 1.0)
        self.assertLess(reversed_order["ndcg@2"], 1.0)
        self.assertGreater(reversed_order["ndcg@2"], 0.0)

    def test_report_keeps_strategy_trace_and_aggregates_mrr_once(self) -> None:
        dataset = EvaluationDataset.from_mapping(
            {
                "dataset_id": "fixture",
                "version": "1",
                "cases": [
                    {
                        "id": "q1",
                        "query": "question",
                        "collection_name": "collection",
                        "relevance": [{"chunk_id": "gold", "grade": 3}],
                    }
                ],
            }
        )
        report = evaluate_dataset(
            dataset,
            lambda _case, method, _limit: RetrievalResult(
                hits=[{"chunk_id": "gold"}] if method == "vector" else [{"chunk_id": "noise"}],
                trace={"effective_method": method},
            ),
            variants=["vector", "bm25"],
            cutoffs=[1, 3],
        )
        self.assertEqual(report["summary"]["vector"]["mrr"], 1.0)
        self.assertEqual(report["summary"]["bm25"]["mrr"], 0.0)
        self.assertEqual(report["cases"][0]["strategies"]["vector"]["trace"]["effective_method"], "vector")

    def test_empty_labels_are_rejected(self) -> None:
        with self.assertRaises(EvaluationDataError):
            EvaluationDataset.from_mapping(
                [{"query": "question", "collection_name": "collection", "relevance": []}]
            )

    def test_citation_audit_distinguishes_no_sources(self) -> None:
        valid = validate_citations("结论 [S1]", [{"id": "S1"}])
        empty = validate_citations("没有证据", [])
        invalid = validate_citations("结论 [S9]", [{"id": "S1"}])
        self.assertEqual(valid["status"], "valid")
        self.assertEqual(valid["coverage"], 1.0)
        self.assertEqual(empty["status"], "no_sources")
        self.assertEqual(invalid["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
