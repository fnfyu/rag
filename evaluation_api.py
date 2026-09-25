"""Read-only API for the checked-in benchmark and the latest safe report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from config import settings
from evaluation import EvaluationDataError, load_dataset
from security import require_api_key

router = APIRouter(prefix="/evaluations/retrieval", tags=["evaluations"], dependencies=[Depends(require_api_key)])


def _safe_model_reference(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    # Model IDs are useful in a report; local paths are reduced to a basename.
    if ":\\" in text or "\\" in text or text.startswith(("/", "~", ".")):
        return Path(text).name or "local-model"
    return text


def _safe_corpus_label(value: Any) -> str:
    text = str(value or "")
    if Path(text).is_absolute():
        return "local benchmark corpus"
    return text or "checked-in benchmark corpus"


def _dataset_summary() -> dict[str, Any]:
    try:
        dataset = load_dataset(settings.evaluation_dataset_path)
    except EvaluationDataError as error:
        raise HTTPException(status_code=500, detail=f"评测数据集不可用：{error}") from error
    return {
        "id": dataset.dataset_id,
        "version": dataset.version,
        "schema_version": dataset.schema_version,
        "fingerprint": dataset.fingerprint,
        "description": dataset.description,
        "corpus": _safe_corpus_label(dataset.corpus),
        "corpus_snapshot_id": dataset.corpus_snapshot_id,
        "judgment_unit": dataset.judgment_unit,
        "qrels_exhaustive": dataset.qrels_exhaustive,
        "queries": len(dataset.cases),
        "tags": sorted({tag for case in dataset.cases for tag in case.tags}),
    }


def _public_trace(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        "status": raw.get("status"),
        "requested_method": raw.get("requested_method"),
        "effective_method": raw.get("effective_method"),
        "fallback_reason": raw.get("fallback_reason"),
        "fallback_reasons": [str(reason) for reason in raw.get("fallback_reasons", []) if str(reason)],
        "candidate_count": raw.get("candidate_count", 0),
        "result_count": raw.get("result_count", 0),
        "duration_ms": raw.get("duration_ms", 0),
        "retryable": bool(raw.get("retryable")),
        "stages": raw.get("stages") if isinstance(raw.get("stages"), dict) else {},
        "errors": [str(error) for error in (raw.get("errors") if isinstance(raw.get("errors"), list) else []) if str(error)],
    }


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    """Whitelist report fields so paths, qrels and local config never leak."""
    raw_dataset = report.get("dataset") or {}
    raw_run = report.get("run") or {}
    raw_config = raw_run.get("config") if isinstance(raw_run.get("config"), dict) else {}
    safe_config = {
        key: raw_config.get(key)
        for key in ("candidate_k", "final_context_k", "rrf_k", "embedding_device", "judgment_unit", "query_rewrite")
        if key in raw_config
    }
    for key in ("embedding_model", "reranker_model"):
        if key in raw_config:
            safe_config[key] = _safe_model_reference(raw_config.get(key))

    safe_cases = []
    for raw_case in report.get("cases", []):
        if not isinstance(raw_case, dict):
            continue
        strategies = {}
        raw_strategies = raw_case.get("strategies") if isinstance(raw_case.get("strategies"), dict) else {}
        for method, raw_strategy in raw_strategies.items():
            if not isinstance(raw_strategy, dict):
                continue
            raw_ids = raw_strategy.get("retrieved_chunk_ids") if isinstance(raw_strategy.get("retrieved_chunk_ids"), list) else []
            strategies[str(method)] = {
                "retrieved_chunk_ids": [str(chunk_id) for chunk_id in raw_ids],
                "metrics": raw_strategy.get("metrics") if isinstance(raw_strategy.get("metrics"), dict) else {},
                "trace": _public_trace(raw_strategy.get("trace")),
            }
        safe_cases.append(
            {
                "id": raw_case.get("id"),
                "query": raw_case.get("query"),
                "strategies": strategies,
            }
        )
    return {
        "schema_version": report.get("schema_version"),
        "dataset": {
            "id": raw_dataset.get("id"),
            "version": raw_dataset.get("version"),
            "schema_version": raw_dataset.get("schema_version"),
            "fingerprint": raw_dataset.get("fingerprint"),
            "corpus_snapshot_id": raw_dataset.get("corpus_snapshot_id"),
            "judgment_unit": raw_dataset.get("judgment_unit"),
            "queries": raw_dataset.get("queries"),
        },
        "run": {
            "status": raw_run.get("status"),
            "variants": raw_run.get("variants") if isinstance(raw_run.get("variants"), list) else [],
            "cutoffs": raw_run.get("cutoffs") if isinstance(raw_run.get("cutoffs"), list) else [],
            "config": safe_config,
            "failures": raw_run.get("failures") if isinstance(raw_run.get("failures"), list) else [],
        },
        "summary": report.get("summary") if isinstance(report.get("summary"), dict) else {},
        "cases": safe_cases,
    }


def _report_identity_matches(report: dict[str, Any], dataset: dict[str, Any]) -> bool:
    report_dataset = report.get("dataset")
    if not isinstance(report_dataset, dict):
        return False
    return all(report_dataset.get(key) == dataset.get(key) for key in ("id", "version", "schema_version", "fingerprint", "corpus_snapshot_id"))


def _report_is_complete(report: dict[str, Any]) -> bool:
    run = report.get("run")
    summary = report.get("summary")
    cases = report.get("cases")
    variants = run.get("variants") if isinstance(run, dict) else None
    cutoffs = run.get("cutoffs") if isinstance(run, dict) else None
    return (
        isinstance(run, dict)
        and run.get("status") == "completed"
        and isinstance(variants, list)
        and bool(variants)
        and isinstance(cutoffs, list)
        and all(isinstance(cutoff, int) and cutoff > 0 for cutoff in cutoffs)
        and isinstance(summary, dict)
        and all(variant in summary for variant in variants)
        and isinstance(cases, list)
        and bool(cases)
        and all(isinstance(case, dict) and isinstance(case.get("strategies"), dict) and bool(case.get("strategies")) for case in cases)
    )


@router.get("/dataset")
async def evaluation_dataset() -> dict[str, Any]:
    """Return dataset provenance without exposing server paths or qrels."""
    return {"status": "ready", "dataset": _dataset_summary()}


@router.get("/latest")
async def latest_evaluation() -> dict[str, Any]:
    """Return the latest CLI-produced report, or an honest not-run state."""
    dataset = _dataset_summary()
    report_path: Path = settings.evaluation_report_path
    if not report_path.exists():
        return {"status": "not_run", "dataset": dataset, "report": None}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail=f"最新评测报告不可读取：{error}") from error
    if not isinstance(report, dict):
        raise HTTPException(status_code=500, detail="最新评测报告格式无效")
    if not _report_identity_matches(report, dataset):
        raw_dataset = report.get("dataset") if isinstance(report.get("dataset"), dict) else {}
        return {
            "status": "stale",
            "dataset": dataset,
            "report": None,
            "stale_report": {
                "id": raw_dataset.get("id"),
                "version": raw_dataset.get("version"),
                "fingerprint": raw_dataset.get("fingerprint"),
                "corpus_snapshot_id": raw_dataset.get("corpus_snapshot_id"),
            },
            "warning": "最新报告的 dataset identity 与当前 benchmark 不一致，已拒绝混入当前结果。",
        }
    if not _report_is_complete(report):
        return {
            "status": "incomplete" if (report.get("run") or {}).get("status") != "invalid" else "invalid",
            "dataset": dataset,
            "report": None,
            "failures": (report.get("run") or {}).get("failures") or [],
            "warning": "最新评测报告未完整生成，指标不会作为可信结果展示。",
        }
    return {"status": "completed", "dataset": dataset, "report": _public_report(report)}
