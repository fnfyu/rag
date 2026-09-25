"""Two-stage retrieval with explicit strategy and degradation traces."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
import time
from hashlib import sha1
from threading import RLock
from typing import Any, Callable, Literal

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

logger = logging.getLogger(__name__)
RetrievalMethod = Literal["vector", "bm25", "rrf", "rerank"]
RETRIEVAL_METHODS = ("vector", "bm25", "rrf", "rerank")


@dataclass(frozen=True)
class RerankOutcome:
    """A reranker result that makes fallback explicit to its caller."""

    documents: list[Document]
    effective_method: str
    status: str
    fallback_reason: str | None = None
    error_code: str | None = None


@dataclass
class RetrievalTrace:
    """The user-visible result of one retrieval attempt.

    The trace keeps documents for the chat adapter and exposes only a compact
    dictionary through :meth:`to_public_dict`; raw exceptions and server paths
    never cross that interface.
    """

    query: str
    requested_method: str
    effective_method: str = "none"
    documents: list[Document] = field(default_factory=list)
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    status: str = "empty"
    fallback_reason: str | None = None
    fallback_reasons: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    candidate_count: int = 0
    duration_ms: int = 0

    @property
    def result_count(self) -> int:
        return len(self.documents)

    @property
    def retryable(self) -> bool:
        return self.status == "failed" or any(
            stage.get("retryable") for stage in self.stages.values()
        )

    def to_public_dict(self) -> dict[str, Any]:
        """Return a safe summary suitable for SSE, persistence, and the UI."""
        return {
            "status": self.status,
            "requested_method": self.requested_method,
            "effective_method": self.effective_method,
            "fallback_reason": self.fallback_reason,
            "fallback_reasons": list(self.fallback_reasons),
            "candidate_count": self.candidate_count,
            "result_count": self.result_count,
            "duration_ms": self.duration_ms,
            "retryable": self.retryable,
            "stages": self.stages,
            "errors": list(self.errors),
        }


class CrossEncoderReranker:
    """Lazy, thread-safe adapter around ``sentence_transformers.CrossEncoder``.

    The adapter is optional: when no model is configured, callers get RRF
    ordering with an explicit ``reranker_not_configured`` fallback reason.
    Model failures use bounded retry backoff and temporarily fall back to RRF
    instead of disabling the request or pretending reranking happened.
    """

    def __init__(self, model_name: str | None, top_k: int, timeout_seconds: float = 20.0) -> None:
        self.model_name = model_name
        self.top_k = top_k
        self.timeout_seconds = timeout_seconds
        self._model: Any = None
        self._lock = RLock()
        self._retry_after = 0.0
        self._failure_count = 0
        self.last_error: str | None = None
        self.last_fallback_reason: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.model_name)

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def status(self) -> str:
        if not self.configured:
            return "disabled"
        if self.loaded:
            return "ready"
        if self.last_error:
            return "fallback"
        return "configured"

    def _load(self) -> Any:
        if self._model is None:
            if not self.model_name:
                raise RuntimeError("RERANKER_MODEL is not configured")
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, max_length=512)
        return self._model

    def rank_with_status(
        self,
        query: str,
        documents: list[Document],
        top_k: int | None = None,
    ) -> RerankOutcome:
        limit = top_k or self.top_k
        if not documents:
            self.last_fallback_reason = None
            return RerankOutcome([], "rrf", "empty")
        if not self.configured:
            self.last_fallback_reason = "reranker_not_configured"
            return RerankOutcome(
                documents[:limit],
                "rrf",
                "fallback",
                fallback_reason=self.last_fallback_reason,
                error_code="reranker_not_configured",
            )

        if not self._lock.acquire(timeout=self.timeout_seconds):
            self.last_fallback_reason = "reranker_lock_timeout"
            logger.warning("Cross-Encoder lock timed out; falling back to RRF")
            return RerankOutcome(
                documents[:limit],
                "rrf",
                "fallback",
                fallback_reason=self.last_fallback_reason,
                error_code="reranker_lock_timeout",
            )
        try:
            if time.monotonic() < self._retry_after:
                self.last_fallback_reason = "reranker_backoff"
                return RerankOutcome(
                    documents[:limit],
                    "rrf",
                    "fallback",
                    fallback_reason=self.last_fallback_reason,
                    error_code="reranker_backoff",
                )
            try:
                model = self._load()
                pairs = [(query, document.page_content) for document in documents]
                scores = list(model.predict(pairs, show_progress_bar=False))
                if len(scores) != len(documents):
                    raise ValueError("reranker returned an unexpected score count")
                ranked = []
                for document, score in zip(documents, scores):
                    score_value = float(score)
                    if not math.isfinite(score_value):
                        raise ValueError("reranker returned a non-finite score")
                    metadata = dict(document.metadata or {})
                    metadata["retrieval_method"] = "rerank"
                    metadata["rerank_score"] = round(score_value, 6)
                    ranked.append(Document(page_content=document.page_content, metadata=metadata))
                ranked.sort(
                    key=lambda document: document.metadata.get("rerank_score", float("-inf")),
                    reverse=True,
                )
                for rank, document in enumerate(ranked, start=1):
                    document.metadata["final_rank"] = rank
                self._failure_count = 0
                self._retry_after = 0.0
                self.last_error = None
                self.last_fallback_reason = None
                return RerankOutcome(ranked[:limit], "rerank", "success")
            except (ImportError, ModuleNotFoundError, OSError, ValueError) as error:
                self._record_failure(error, permanentish=True)
                return RerankOutcome(
                    documents[:limit],
                    "rrf",
                    "fallback",
                    fallback_reason="reranker_load_failed",
                    error_code="reranker_unavailable",
                )
            except Exception as error:
                self._record_failure(error, permanentish=False)
                return RerankOutcome(
                    documents[:limit],
                    "rrf",
                    "fallback",
                    fallback_reason="reranker_inference_failed",
                    error_code="reranker_failed",
                )
        finally:
            self._lock.release()

    def rank(self, query: str, documents: list[Document], top_k: int | None = None) -> list[Document]:
        """Backwards-compatible adapter returning only ranked documents."""
        return self.rank_with_status(query, documents, top_k).documents

    def _record_failure(self, error: Exception, permanentish: bool) -> None:
        self.last_error = str(error)
        self._failure_count += 1
        base_delay = 300 if permanentish else 15
        delay = min(900, base_delay * (2 ** min(self._failure_count - 1, 2)))
        self._retry_after = time.monotonic() + delay
        logger.warning("Cross-Encoder unavailable; falling back to RRF for %ss", delay, exc_info=True)


class HybridRetriever:
    """Small retrieval interface hiding vector, lexical, fusion and rerank policy.

    ``retrieve_with_trace`` is the public seam for chat and evaluation.  It
    returns one consistent evidence unit (child documents unless a caller asks
    for parent expansion) and records partial failures instead of making the
    caller infer them from missing metadata.
    """

    def __init__(
        self,
        vector_retriever: BaseRetriever | None,
        lexical_retriever: BaseRetriever | None,
        candidate_k: int,
        final_k: int,
        rrf_k: int,
        reranker: CrossEncoderReranker,
        parent_child_enabled: bool,
    ) -> None:
        self.vector_retriever = vector_retriever
        self.lexical_retriever = lexical_retriever
        self.candidate_k = candidate_k
        self.final_k = final_k
        self.rrf_k = rrf_k
        self.reranker = reranker
        self.parent_child_enabled = parent_child_enabled

    def retrieve(
        self,
        query: str,
        limit: int | None = None,
        method: RetrievalMethod = "rerank",
    ) -> list[Document]:
        """Compatibility interface returning final context documents."""
        return self.retrieve_with_trace(query, method=method, limit=limit, expand_parent=True).documents

    def retrieve_with_trace(
        self,
        query: str,
        *,
        method: RetrievalMethod = "rerank",
        limit: int | None = None,
        expand_parent: bool | None = None,
    ) -> RetrievalTrace:
        """Retrieve one strategy and expose its effective path and failures."""
        normalized_method = str(method).lower()
        if normalized_method not in RETRIEVAL_METHODS:
            raise ValueError(f"unknown retrieval method: {normalized_method}")
        if limit is not None and limit < 1:
            raise ValueError("retrieval limit must be positive")
        output_limit = min(limit or self.final_k, self.candidate_k)
        should_expand = self.parent_child_enabled if expand_parent is None else expand_parent
        started = time.perf_counter()
        trace = RetrievalTrace(query=query, requested_method=normalized_method)

        if normalized_method in ("vector", "bm25"):
            documents, stage = self._invoke_stage(normalized_method, query, output_limit)
            trace.stages[normalized_method] = stage
            trace.candidate_count = len(documents)
            trace.documents = self._tag_documents(documents, normalized_method)[:output_limit]
            trace.effective_method = normalized_method if trace.documents else "none"
            trace.status = "success" if trace.documents else ("failed" if stage["status"] == "failed" else "empty")
            if stage["status"] == "failed":
                trace.errors.append(stage["error_code"])
        else:
            vector_documents, vector_stage = self._invoke_stage("vector", query, self.candidate_k)
            lexical_documents, lexical_stage = self._invoke_stage("bm25", query, self.candidate_k)
            trace.stages["vector"] = vector_stage
            trace.stages["bm25"] = lexical_stage
            if vector_stage["status"] == "failed":
                trace.errors.append(vector_stage["error_code"])
            if lexical_stage["status"] == "failed":
                trace.errors.append(lexical_stage["error_code"])

            rrf_started = time.perf_counter()
            fused = self._rrf(vector_documents, lexical_documents)
            trace.stages["rrf"] = {
                "status": "success" if fused else ("failed" if trace.errors else "empty"),
                "count": len(fused),
                "duration_ms": max(0, round((time.perf_counter() - rrf_started) * 1000)),
                "retryable": bool(trace.errors),
                "error_code": None,
            }
            trace.candidate_count = len(fused)
            partial_failure = bool(trace.errors) and bool(fused)
            if partial_failure:
                trace.fallback_reason = "partial_candidate_failure"
                trace.fallback_reasons.append("partial_candidate_failure")

            if normalized_method == "rerank" and fused:
                rerank_started = time.perf_counter()
                outcome = self.reranker.rank_with_status(query, fused, top_k=self.candidate_k)
                trace.stages["rerank"] = {
                    "status": outcome.status,
                    "count": len(outcome.documents),
                    "duration_ms": max(0, round((time.perf_counter() - rerank_started) * 1000)),
                    "retryable": outcome.status == "fallback",
                    "error_code": outcome.error_code,
                }
                final_documents = outcome.documents
                trace.effective_method = outcome.effective_method
                if outcome.fallback_reason:
                    if not trace.fallback_reason:
                        trace.fallback_reason = outcome.fallback_reason
                    trace.fallback_reasons.append(outcome.fallback_reason)
                if outcome.error_code:
                    trace.errors.append(outcome.error_code)
            else:
                trace.stages["rerank"] = {
                    "status": "skipped" if normalized_method == "rrf" else "empty",
                    "count": 0,
                    "duration_ms": 0,
                    "retryable": False,
                    "error_code": None,
                }
                final_documents = fused
                trace.effective_method = "rrf" if fused else "none"

            trace.documents = final_documents[:output_limit]
            if trace.documents:
                trace.status = "fallback" if trace.fallback_reason or trace.errors else "success"
            else:
                trace.status = "failed" if trace.errors else "empty"

        if should_expand and trace.documents:
            trace.documents = self._expand_parent_context(trace.documents, output_limit)
        trace.duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        for stage in trace.stages.values():
            if stage.get("duration_ms") == 0:
                stage["duration_ms"] = trace.duration_ms
        return trace

    def _invoke_stage(
        self,
        stage_name: str,
        query: str,
        limit: int,
    ) -> tuple[list[Document], dict[str, Any]]:
        retriever = self.vector_retriever if stage_name == "vector" else self.lexical_retriever
        started = time.perf_counter()
        if retriever is None:
            return [], {
                "status": "failed",
                "count": 0,
                "duration_ms": 0,
                "retryable": False,
                "error_code": f"{stage_name}_unavailable",
            }
        try:
            documents = list(retriever.invoke(query) or [])[:limit]
            tagged = self._tag_documents(documents, stage_name)
            return tagged, {
                "status": "success" if tagged else "empty",
                "count": len(tagged),
                "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
                "retryable": False,
                "error_code": None,
            }
        except Exception:
            logger.exception("%s retrieval failed", stage_name)
            return [], {
                "status": "failed",
                "count": 0,
                "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
                "retryable": True,
                "error_code": f"{stage_name}_failed",
            }

    @staticmethod
    def _tag_documents(documents: list[Document], method: str) -> list[Document]:
        tagged: list[Document] = []
        for rank, document in enumerate(documents, start=1):
            metadata = dict(document.metadata or {})
            metadata["retrieval_method"] = method
            metadata[f"{method}_rank"] = rank
            metadata.setdefault("candidate_origin", method)
            tagged.append(Document(page_content=document.page_content, metadata=metadata))
        return tagged

    def _expand_parent_context(self, documents: list[Document], limit: int) -> list[Document]:
        """Replace child hits with unique parent context while preserving rank metadata."""
        parents: dict[str, Document] = {}
        for document in documents:
            metadata = dict(document.metadata or {})
            parent_id = metadata.get("parent_id")
            parent_content = metadata.get("parent_content")
            if not parent_id or not parent_content:
                parents.setdefault(self._document_key(document), document)
                continue
            if parent_id in parents:
                continue
            parent_metadata = {key: value for key, value in metadata.items() if key != "parent_content"}
            parent_metadata["chunk_id"] = parent_id
            parent_metadata["child_chunk_id"] = metadata.get("chunk_id")
            parent_metadata["expanded_from_child"] = True
            if metadata.get("parent_start_line") is not None:
                parent_metadata["start_line"] = metadata["parent_start_line"]
                parent_metadata["end_line"] = metadata.get("parent_end_line")
            parent_metadata["retrieval_method"] = f"{metadata.get('retrieval_method', 'rrf')}+parent"
            parents[parent_id] = Document(page_content=str(parent_content), metadata=parent_metadata)
        return list(parents.values())[:limit]

    def _rrf(self, *result_sets: list[Document]) -> list[Document]:
        scores: dict[str, float] = {}
        documents: dict[str, Document] = {}
        origins: dict[str, list[str]] = {}
        ranks: dict[str, dict[str, int]] = {}
        source_names = ("vector", "bm25")
        for source_index, result_set in enumerate(result_sets):
            source_name = source_names[source_index] if source_index < len(source_names) else f"source_{source_index}"
            for rank, document in enumerate(result_set[: self.candidate_k], start=1):
                key = self._document_key(document)
                scores[key] = scores.get(key, 0.0) + 1.0 / (self.rrf_k + rank)
                documents.setdefault(key, document)
                origins.setdefault(key, []).append(source_name)
                ranks.setdefault(key, {})[f"{source_name}_rank"] = rank

        fused: list[Document] = []
        ordered = sorted(
            scores.items(),
            key=lambda item: (-item[1], self._document_key(documents[item[0]])),
        )
        for final_rank, (key, document) in enumerate(ordered[: self.candidate_k], start=1):
            metadata = dict(document.metadata or {})
            metadata.update(ranks.get(key, {}))
            metadata["candidate_origin"] = "+".join(origins.get(key, []))
            metadata["retrieval_method"] = "rrf"
            metadata["rrf_score"] = round(scores[key], 6)
            metadata["final_rank"] = final_rank
            fused.append(Document(page_content=document.page_content, metadata=metadata))
        return fused

    @staticmethod
    def _document_key(document: Document) -> str:
        metadata = document.metadata or {}
        stable_id = metadata.get("chunk_id") or metadata.get("child_chunk_id")
        if stable_id:
            return str(stable_id)
        source = metadata.get("source")
        if source:
            return f"{source}:{sha1(document.page_content.encode('utf-8', errors='ignore')).hexdigest()}"
        return sha1(document.page_content.encode("utf-8", errors="ignore")).hexdigest()
