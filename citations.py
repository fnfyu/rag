"""Structural citation checks for generated answers."""

from __future__ import annotations

import re
from typing import Any

_CITATION_PATTERN = re.compile(r"\[S(\d+)\]")
VALIDATOR_VERSION = "1.1"


def validate_citations(answer: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Check that source markers map to evidence sent to the model.

    This is a structural guard, not a claim of semantic truth. Entailment still
    needs a labeled evaluation set or a separate judge model.  ``no_sources``
    is intentionally distinct from ``valid`` so an empty retrieval cannot look
    like a successful citation audit.
    """
    cited_ids = sorted({f"S{number}" for number in _CITATION_PATTERN.findall(answer or "")})
    known_ids = {str(source.get("id")) for source in sources}
    unknown_ids = [citation_id for citation_id in cited_ids if citation_id not in known_ids]
    cited_source_count = len(set(cited_ids) & known_ids)
    missing_citations = bool(sources) and not cited_ids
    if not sources:
        status = "no_sources"
    elif unknown_ids:
        status = "invalid"
    elif missing_citations:
        status = "missing"
    else:
        status = "valid"

    warnings: list[str] = []
    if status == "no_sources":
        warnings.append("没有检索到可引用证据")
    elif status == "missing":
        warnings.append("回答未包含可识别的来源编号")
    elif status == "invalid":
        warnings.append("回答包含未发送给模型的来源编号")

    return {
        "status": status,
        "validator_version": VALIDATOR_VERSION,
        "cited_ids": cited_ids,
        "unknown_ids": unknown_ids,
        "source_count": len(sources),
        "cited_source_count": cited_source_count,
        "coverage": cited_source_count / len(sources) if sources else 0.0,
        "warnings": warnings,
    }
