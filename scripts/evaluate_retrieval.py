"""Compare retrieval strategies on a labeled dataset.

The evaluator runs retrieval only; it never calls the answer-generation LLM.
Dataset format is documented in ``scripts/evaluation.example.json`` and accepts
both the original ``relevant_chunk_ids`` list and graded ``relevance`` labels.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any
import uuid

# Allow ``py scripts/evaluate_retrieval.py ...`` from the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import get_rag_service
from evaluation import (
    DEFAULT_CUTOFFS,
    RETRIEVAL_VARIANTS,
    EvaluationCase,
    RetrievalResult,
    evaluate_dataset,
    load_dataset,
)


def _parse_csv(value: str, kind: str) -> list[str] | list[int]:
    entries = [item.strip() for item in value.split(",") if item.strip()]
    if kind == "methods":
        unknown = [entry for entry in entries if entry not in RETRIEVAL_VARIANTS]
        if unknown:
            raise argparse.ArgumentTypeError(f"unknown methods: {', '.join(unknown)}")
        return entries
    try:
        cutoffs = [int(entry) for entry in entries]
    except ValueError as error:
        raise argparse.ArgumentTypeError("cutoffs must be comma-separated integers") from error
    if any(cutoff < 1 for cutoff in cutoffs):
        raise argparse.ArgumentTypeError("cutoffs must be positive")
    return cutoffs


def _run_config(service: Any, dataset: Any, methods: list[str], cutoffs: list[int], manifest: Path) -> dict[str, Any]:
    settings = service.settings
    return {
        "methods": methods,
        "cutoffs": cutoffs,
        "candidate_k": settings.candidate_k,
        "final_context_k": settings.final_context_k,
        "rrf_k": settings.rrf_k,
        "embedding_model": settings.embedding_model,
        "embedding_device": settings.embedding_device,
        "reranker_model": settings.reranker_model,
        "parent_child_enabled": settings.parent_child_enabled,
        "judgment_unit": dataset.judgment_unit,
        "corpus_snapshot_id": dataset.corpus_snapshot_id,
        "manifest": str(manifest.name),
        "query_rewrite": "disabled_for_retrieval_benchmark",
    }


def _validate_manifest(dataset: Any, manifest_path: Path, service: Any) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid corpus manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError("corpus manifest must be an object")
    if dataset.judgment_unit != "child":
        raise ValueError("this evaluator only supports judgment_unit=child")
    if not dataset.qrels_exhaustive:
        raise ValueError("this evaluator requires qrels_exhaustive=true")
    if manifest.get("snapshot_id") != dataset.corpus_snapshot_id:
        raise ValueError("dataset corpus_snapshot_id does not match corpus manifest")
    collection_name = str(manifest.get("collection_name") or "")
    if not collection_name or {case.collection_name for case in dataset.cases} != {collection_name}:
        raise ValueError("dataset collections do not match the corpus manifest collection")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("corpus manifest has no files")
    corpus_value = str(manifest.get("corpus") or "")
    corpus_path = (ROOT / corpus_value).resolve() if not Path(corpus_value).is_absolute() else Path(corpus_value)
    expected_ids: set[str] = set()
    for record in files:
        if not isinstance(record, dict):
            raise ValueError("corpus manifest file entry is invalid")
        path = corpus_path / str(record.get("filename") or "")
        if not path.exists() or sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
            raise ValueError(f"corpus file hash mismatch: {path.name}")
        expected_ids.add(str(record.get("expected_first_chunk_id") or ""))
    missing_labels = [
        f"{case.case_id}:{chunk_id}"
        for case in dataset.cases
        for chunk_id in case.relevance
        if chunk_id not in expected_ids
    ]
    if missing_labels:
        raise ValueError(f"qrels reference IDs absent from manifest: {', '.join(missing_labels[:3])}")
    chunking = manifest.get("chunking") or {}
    settings = service.settings
    expected_chunking = {
        "parent_child_enabled": settings.parent_child_enabled,
        "parent_chunk_size": settings.parent_chunk_size,
        "parent_chunk_overlap": settings.parent_chunk_overlap,
        "child_chunk_size": settings.child_chunk_size,
        "child_chunk_overlap": settings.child_chunk_overlap,
    }
    for key, value in expected_chunking.items():
        if chunking.get(key) != value:
            raise ValueError(f"index settings differ from manifest: {key}")
    if not service.collection_has_documents(collection_name):
        raise ValueError(f"evaluation collection is empty: {collection_name}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Evidence RAG retrieval strategies")
    parser.add_argument("dataset", type=Path, help="JSON file containing labeled questions")
    parser.add_argument(
        "--methods",
        default=",".join(RETRIEVAL_VARIANTS),
        help="Comma-separated strategies: vector,bm25,rrf,rerank",
    )
    parser.add_argument(
        "--cutoffs",
        default=",".join(str(cutoff) for cutoff in DEFAULT_CUTOFFS),
        help="Comma-separated metric cutoffs, for example 1,3,5,10",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Backward-compatible alias for evaluating one cutoff",
    )
    parser.add_argument("--manifest", type=Path, default=ROOT / "evaluation" / "corpus-manifest.json", help="Indexed corpus manifest")
    parser.add_argument("--output", type=Path, default=None, help="Write the JSON report to this path")
    args = parser.parse_args()

    methods = _parse_csv(args.methods, "methods")
    cutoffs = [args.top_k] if args.top_k is not None else _parse_csv(args.cutoffs, "cutoffs")
    if not methods or not cutoffs or any(cutoff < 1 for cutoff in cutoffs):
        parser.error("at least one positive method and cutoff are required")

    try:
        dataset = load_dataset(args.dataset)
        service = get_rag_service()
    except Exception as error:
        parser.error(str(error))

    max_cutoff = max(cutoffs)
    if max_cutoff > service.settings.candidate_k:
        parser.error(f"largest cutoff must be <= CANDIDATE_K ({service.settings.candidate_k})")
    try:
        manifest = _validate_manifest(dataset, args.manifest, service)
    except ValueError as error:
        parser.error(str(error))

    def retrieve(case: EvaluationCase, method: str, limit: int) -> RetrievalResult:
        trace = service.retrieve_trace(
            case.query,
            case.collection_name,
            limit=limit,
            method=method,
            expand_parent=False,
        )
        return RetrievalResult(hits=trace.documents, trace=trace.to_public_dict())

    try:
        report = evaluate_dataset(
            dataset,
            retrieve,
            variants=methods,
            cutoffs=cutoffs,
            run_config={
                **_run_config(service, dataset, methods, cutoffs, args.manifest),
                "run_id": f"run_{uuid.uuid4().hex}",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as error:
        parser.error(f"retrieval evaluation failed; no report was written: {error}")

    report["run"]["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["run"]["retrieval_only"] = True

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            file.write(rendered + "\n")
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(args.output)
    print(rendered)
    if report["run"].get("status") != "completed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
