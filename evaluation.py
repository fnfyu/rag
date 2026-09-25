"""Versioned retrieval-evaluation domain model and metric engine.

The module deliberately has no LangChain, vector-store, or model dependency.  The
retrieval implementation crosses one small seam: a callback receives an
:class:`EvaluationCase`, a strategy name, and a cutoff, then returns ordered hits.
That keeps the metric contract reusable in tests, the CLI, and a future evaluation
API without loading an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

RETRIEVAL_VARIANTS = ("vector", "bm25", "rrf", "rerank")
DEFAULT_CUTOFFS = (1, 3, 5, 10)


class EvaluationDataError(ValueError):
    """Raised when a labeled evaluation dataset is malformed."""


@dataclass(frozen=True)
class EvaluationCase:
    """One labeled question in a versioned benchmark.

    ``relevance`` maps stable chunk IDs to integer grades.  Grade zero is kept
    in the input contract for explicit negative labels, while metrics treat only
    positive grades as relevant.
    """

    case_id: str
    query: str
    collection_name: str
    relevance: Mapping[str, int]
    tags: tuple[str, ...] = ()
    notes: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], index: int = 0) -> "EvaluationCase":
        if not isinstance(raw, Mapping):
            raise EvaluationDataError(f"case {index + 1} must be an object")
        query = str(raw.get("query") or "").strip()
        collection_name = str(raw.get("collection_name") or "").strip()
        if not query:
            raise EvaluationDataError(f"case {index + 1} is missing query")
        if not collection_name:
            raise EvaluationDataError(f"case {index + 1} is missing collection_name")

        raw_relevance = raw.get("relevance")
        relevance: dict[str, int] = {}
        if isinstance(raw_relevance, Mapping):
            for chunk_id, grade in raw_relevance.items():
                relevance[_require_chunk_id(chunk_id, index)] = _parse_grade(grade, index)
        elif isinstance(raw_relevance, Sequence) and not isinstance(raw_relevance, (str, bytes)):
            for label in raw_relevance:
                if not isinstance(label, Mapping):
                    raise EvaluationDataError(f"case {index + 1} relevance entries must be objects")
                chunk_id = _require_chunk_id(label.get("chunk_id") or label.get("id"), index)
                if chunk_id in relevance:
                    raise EvaluationDataError(f"case {index + 1} contains duplicate chunk ID {chunk_id}")
                relevance[chunk_id] = _parse_grade(label.get("grade", 1), index)
        else:
            # Keep the original prototype format readable and backwards-compatible.
            ids = raw.get("relevant_chunk_ids") or []
            if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
                raise EvaluationDataError(f"case {index + 1} relevant_chunk_ids must be an array")
            for chunk_id in ids:
                normalized_id = _require_chunk_id(chunk_id, index)
                if normalized_id in relevance:
                    raise EvaluationDataError(f"case {index + 1} contains duplicate chunk ID {normalized_id}")
                relevance[normalized_id] = 1
            graded = raw.get("graded_relevance") or {}
            if graded:
                if not isinstance(graded, Mapping):
                    raise EvaluationDataError(f"case {index + 1} graded_relevance must be an object")
                for chunk_id, grade in graded.items():
                    normalized_id = _require_chunk_id(chunk_id, index)
                    if normalized_id in relevance:
                        raise EvaluationDataError(f"case {index + 1} contains duplicate chunk ID {normalized_id}")
                    relevance[normalized_id] = _parse_grade(grade, index)

        if not relevance or not any(grade > 0 for grade in relevance.values()):
            raise EvaluationDataError(f"case {index + 1} must label at least one positive chunk")
        case_id = str(raw.get("id") or raw.get("case_id") or f"case-{index + 1:03d}").strip()
        tags = raw.get("tags") or []
        if isinstance(tags, (str, bytes)) or not isinstance(tags, Sequence):
            raise EvaluationDataError(f"case {index + 1} tags must be an array")
        return cls(
            case_id=case_id,
            query=query,
            collection_name=collection_name,
            relevance=relevance,
            tags=tuple(str(tag) for tag in tags),
            notes=str(raw.get("notes") or "").strip(),
        )

    @property
    def relevant_ids(self) -> frozenset[str]:
        return frozenset(chunk_id for chunk_id, grade in self.relevance.items() if grade > 0)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "query": self.query,
            "collection_name": self.collection_name,
            "relevance": [
                {"chunk_id": chunk_id, "grade": grade}
                for chunk_id, grade in self.relevance.items()
            ],
            **({"tags": list(self.tags)} if self.tags else {}),
            **({"notes": self.notes} if self.notes else {}),
        }


@dataclass(frozen=True)
class EvaluationDataset:
    """A labeled dataset plus the provenance needed to reproduce a run."""

    dataset_id: str
    version: str
    cases: tuple[EvaluationCase, ...]
    description: str = ""
    corpus: str = ""
    schema_version: str = "1.0"
    corpus_snapshot_id: str = ""
    judgment_unit: str = "child"
    qrels_exhaustive: bool = True
    annotator: str = ""

    @classmethod
    def from_mapping(cls, raw: Any, source_name: str = "dataset") -> "EvaluationDataset":
        if isinstance(raw, list):
            metadata: Mapping[str, Any] = {}
            raw_cases = raw
        elif isinstance(raw, Mapping):
            metadata = raw
            raw_cases = raw.get("cases") or raw.get("questions")
        else:
            raise EvaluationDataError(f"{source_name} must be an array or an object with cases")
        if not isinstance(raw_cases, list) or not raw_cases:
            raise EvaluationDataError(f"{source_name} must contain at least one case")
        cases = tuple(EvaluationCase.from_mapping(case, index) for index, case in enumerate(raw_cases))
        dataset_id = str(metadata.get("dataset_id") or metadata.get("id") or Path(source_name).stem or "evaluation")
        version = str(metadata.get("version") or "1.0")
        return cls(
            dataset_id=dataset_id,
            version=version,
            cases=cases,
            description=str(metadata.get("description") or "").strip(),
            corpus=str(metadata.get("corpus") or "").strip(),
            schema_version=str(metadata.get("schema_version") or "1.0"),
            corpus_snapshot_id=str(metadata.get("corpus_snapshot_id") or ""),
            judgment_unit=str(metadata.get("judgment_unit") or "child"),
            qrels_exhaustive=_parse_bool(metadata.get("qrels_exhaustive", True), source_name),
            annotator=str(metadata.get("annotator") or ""),
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "corpus_snapshot_id": self.corpus_snapshot_id,
            "judgment_unit": self.judgment_unit,
            "qrels_exhaustive": self.qrels_exhaustive,
            "cases": [case.to_mapping() for case in self.cases],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "description": self.description,
            "corpus": self.corpus,
            "corpus_snapshot_id": self.corpus_snapshot_id,
            "judgment_unit": self.judgment_unit,
            "qrels_exhaustive": self.qrels_exhaustive,
            "annotator": self.annotator,
            "cases": [case.to_mapping() for case in self.cases],
        }


@dataclass(frozen=True)
class RetrievalHit:
    """The small hit shape required by the evaluation seam."""

    chunk_id: str
    score: float | None = None
    metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_any(cls, hit: Any) -> "RetrievalHit":
        if isinstance(hit, cls):
            return hit
        if isinstance(hit, str):
            return cls(chunk_id=hit)
        if isinstance(hit, Mapping):
            metadata = hit.get("metadata") if isinstance(hit.get("metadata"), Mapping) else hit
            chunk_id = _hit_id(metadata)
            score = hit.get("score")
            return cls(chunk_id=chunk_id, score=_optional_float(score), metadata=metadata)
        metadata = getattr(hit, "metadata", None) or {}
        chunk_id = _hit_id(metadata)
        score = getattr(hit, "score", None)
        return cls(chunk_id=chunk_id, score=_optional_float(score), metadata=metadata)


@dataclass(frozen=True)
class RetrievalResult:
    """Optional trace metadata returned alongside ordered evaluation hits."""

    hits: Sequence[Any]
    trace: Mapping[str, Any] | None = None


def load_dataset(path: str | Path) -> EvaluationDataset:
    dataset_path = Path(path)
    try:
        raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EvaluationDataError(f"unable to read dataset {dataset_path}: {error}") from error
    except json.JSONDecodeError as error:
        raise EvaluationDataError(f"dataset {dataset_path} is not valid JSON: {error}") from error
    return EvaluationDataset.from_mapping(raw, str(dataset_path))


def metric_at_k(
    retrieved_ids: Sequence[str],
    relevance: Mapping[str, int],
    cutoff: int,
) -> dict[str, float]:
    """Calculate Recall@K, reciprocal rank and graded nDCG@K for one query."""
    if cutoff < 1:
        raise ValueError("cutoff must be positive")
    ids = _unique_non_empty(retrieved_ids)[:cutoff]
    gains = [max(0, int(relevance.get(chunk_id, 0))) for chunk_id in ids]
    relevant_count = sum(1 for grade in relevance.values() if int(grade) > 0)
    hit_count = sum(1 for gain in gains if gain > 0)
    recall = hit_count / relevant_count if relevant_count else 0.0
    reciprocal_rank = next(
        (1.0 / (index + 1) for index, gain in enumerate(gains) if gain > 0),
        0.0,
    )
    dcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal_gains = sorted((max(0, int(grade)) for grade in relevance.values()), reverse=True)[:cutoff]
    ideal_dcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(ideal_gains))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return {
        f"recall@{cutoff}": recall,
        "reciprocal_rank": reciprocal_rank,
        f"ndcg@{cutoff}": ndcg,
    }


def evaluate_dataset(
    dataset: EvaluationDataset,
    retrieve: Callable[[EvaluationCase, str, int], Any],
    *,
    variants: Iterable[str] = RETRIEVAL_VARIANTS,
    cutoffs: Iterable[int] = DEFAULT_CUTOFFS,
    run_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate every strategy through a retrieval callback and return JSON data.

    The callback is the only adapter the metric engine needs.  It must return
    results in descending rank order; the engine owns deduplication, relevance
    matching, metric calculation, aggregation, and the reproducibility record.
    """
    normalized_variants = _normalize_variants(variants)
    normalized_cutoffs = _normalize_cutoffs(cutoffs)
    max_cutoff = max(normalized_cutoffs)
    case_results: list[dict[str, Any]] = []
    aggregate: dict[str, dict[str, float]] = {
        variant: _empty_summary(normalized_cutoffs) for variant in normalized_variants
    }
    failures: list[dict[str, str]] = []

    for case in dataset.cases:
        result: dict[str, Any] = {
            "id": case.case_id,
            "query": case.query,
            "collection_name": case.collection_name,
            "relevant_chunk_ids": sorted(case.relevant_ids),
            "strategies": {},
        }
        for variant in normalized_variants:
            raw_result = retrieve(case, variant, max_cutoff)
            trace: Mapping[str, Any] | None = None
            if isinstance(raw_result, RetrievalResult):
                raw_hits = raw_result.hits
                trace = raw_result.trace
            else:
                raw_hits = raw_result
            hits = [RetrievalHit.from_any(hit) for hit in raw_hits]
            retrieved_ids = _unique_non_empty(hit.chunk_id for hit in hits)
            strategy_result: dict[str, Any] = {
                "retrieved_chunk_ids": retrieved_ids[:max_cutoff],
                "metrics": {},
            }
            if trace is not None:
                strategy_result["trace"] = dict(trace)
                if trace.get("status") == "failed":
                    failures.append(
                        {
                            "case_id": case.case_id,
                            "variant": variant,
                            "reason": ",".join(str(error) for error in trace.get("errors", [])) or "retrieval_failed",
                        }
                    )
            for cutoff in normalized_cutoffs:
                metrics = metric_at_k(retrieved_ids, case.relevance, cutoff)
                strategy_result["metrics"][str(cutoff)] = metrics
                for key, value in metrics.items():
                    # MRR is a single run-level metric.  Aggregate the value at
                    # the largest cutoff instead of counting it once per K.
                    if key == "reciprocal_rank" and cutoff != max_cutoff:
                        continue
                    summary_key = "mrr" if key == "reciprocal_rank" else key
                    aggregate[variant][summary_key] += value
            result["strategies"][variant] = strategy_result
        case_results.append(result)

    denominator = len(dataset.cases) or 1
    summary = {
        variant: {key: round(value / denominator, 6) for key, value in metrics.items()}
        for variant, metrics in aggregate.items()
    }
    return {
        "schema_version": "1.0",
        "dataset": {
            "id": dataset.dataset_id,
            "version": dataset.version,
            "fingerprint": dataset.fingerprint,
            "description": dataset.description,
            "corpus": dataset.corpus,
            "corpus_snapshot_id": dataset.corpus_snapshot_id,
            "schema_version": dataset.schema_version,
            "judgment_unit": dataset.judgment_unit,
            "qrels_exhaustive": dataset.qrels_exhaustive,
            "queries": len(dataset.cases),
        },
        "run": {
            "status": "incomplete" if failures else "completed",
            "variants": list(normalized_variants),
            "cutoffs": list(normalized_cutoffs),
            "config": dict(run_config or {}),
            "failures": failures,
        },
        "summary": summary,
        "cases": case_results,
    }


def _empty_summary(cutoffs: Sequence[int]) -> dict[str, float]:
    keys: dict[str, float] = {"mrr": 0.0}
    for cutoff in cutoffs:
        keys[f"recall@{cutoff}"] = 0.0
        keys[f"ndcg@{cutoff}"] = 0.0
    return keys


def _normalize_variants(variants: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(variant).strip().lower() for variant in variants if str(variant).strip()))
    unknown = [variant for variant in normalized if variant not in RETRIEVAL_VARIANTS]
    if unknown:
        raise ValueError(f"unsupported retrieval strategies: {', '.join(unknown)}")
    if not normalized:
        raise ValueError("at least one retrieval strategy is required")
    return normalized


def _normalize_cutoffs(cutoffs: Iterable[int]) -> tuple[int, ...]:
    normalized = tuple(sorted({int(cutoff) for cutoff in cutoffs}))
    if not normalized or normalized[0] < 1:
        raise ValueError("cutoffs must contain positive integers")
    return normalized


def _require_chunk_id(value: Any, index: int) -> str:
    chunk_id = str(value or "").strip()
    if not chunk_id:
        raise EvaluationDataError(f"case {index + 1} contains an empty chunk ID")
    return chunk_id


def _parse_bool(value: Any, source_name: str) -> bool:
    if not isinstance(value, bool):
        raise EvaluationDataError(f"{source_name} qrels_exhaustive must be boolean")
    return value


def _parse_grade(value: Any, index: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvaluationDataError(f"case {index + 1} has a non-integer relevance grade")
    if value < 0:
        raise EvaluationDataError(f"case {index + 1} has a negative relevance grade")
    return value


def _hit_id(metadata: Mapping[str, Any]) -> str:
    chunk_id = metadata.get("child_chunk_id") or metadata.get("chunk_id") or metadata.get("id")
    if not chunk_id:
        raise EvaluationDataError("retrieval hit has no chunk_id")
    return str(chunk_id)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique_non_empty(ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for raw_id in ids:
        chunk_id = str(raw_id or "").strip()
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            unique.append(chunk_id)
    return unique
