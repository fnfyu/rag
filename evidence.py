"""Shared evidence serialization for chat, reports and page-region inspection."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote
from langchain_core.documents import Document


def metadata_value(value: Any, default: Any = None) -> Any:
    if isinstance(value, str) and value[:1] in {"[", "{"}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default if default is not None else value
    return value if value is not None else default


def build_sources(documents: list[Document]) -> list[dict[str, Any]]:
    sources = []
    for index, document in enumerate(documents, 1):
        metadata = document.metadata or {}
        windows = metadata_value(metadata.get("context_windows"), [])
        excerpt = " ".join(document.page_content.split())
        source = {
            "id": f"S{index}", "filename": metadata.get("filename", "未知文件"),
            "source_id": metadata.get("source"), "evidence_id": metadata.get("child_chunk_id") or metadata.get("chunk_id"),
            "excerpt": excerpt[:360] + ("…" if len(excerpt) > 360 else ""), "content": document.page_content,
            "section": metadata.get("section", ""), "section_path": metadata.get("section_path", ""),
            "block_type": metadata.get("block_type"), "context_windows": windows,
            "evidence": metadata_value(metadata.get("evidence"), []),
            "start_line": metadata.get("start_line") if len(windows) <= 1 else None,
            "end_line": metadata.get("end_line") if len(windows) <= 1 else None,
            "chunk_id": metadata.get("chunk_id"), "parent_id": metadata.get("parent_id"),
            "child_chunk_id": metadata.get("child_chunk_id"), "child_chunk_ids": metadata_value(metadata.get("child_chunk_ids"), []),
            "chunk_index": metadata.get("chunk_index"), "page_number": metadata.get("page_number") or metadata.get("page"),
            "final_rank": metadata.get("final_rank") or index,
            "retrieval_method": metadata.get("retrieval_method"), "candidate_origin": metadata.get("candidate_origin"),
            "expanded_from_child": metadata.get("expanded_from_child", False),
            "vector_rank": metadata.get("vector_rank"), "bm25_rank": metadata.get("bm25_rank"),
            "rrf_score": metadata.get("rrf_score"), "rerank_score": metadata.get("rerank_score"),
        }
        for key in ("knowledge_base_id", "document_series_id", "document_version_id", "version_label", "release_date",
                    "region_type", "evidence_modality", "is_literal", "page_width", "page_height", "asset_key"):
            if metadata.get(key) is not None:
                source[key] = metadata[key]
        for key in ("bbox", "table_json", "applicability"):
            if metadata.get(key) is not None:
                source[key] = metadata_value(metadata[key])
        domain = metadata_value(metadata.get("domain_metadata"), {})
        if isinstance(domain, dict) and domain:
            source["domain_metadata"] = domain
        for key in ("game_id", "edition", "patch", "mode", "platform", "source_kind", "source_tier", "source_url",
                    "provenance", "captured_at", "published_at", "content_sha256", "capture_sha256", "compatibility",
                    "historical", "recommendable", "requires_confirmation", "actualDLCAccess", "comparison_only", "out_of_scope_conditions"):
            value = metadata.get(key, domain.get(key) if isinstance(domain, dict) else None)
            if value is not None:
                source[key] = value
        for key in ("requires_dlc", "dlc"):
            value = metadata.get(key, domain.get(key) if isinstance(domain, dict) else None)
            if value is not None:
                source[key] = metadata_value(value)
        if metadata.get("asset_key"):
            source["asset_url"] = "/documents/assets/" + quote(str(metadata["asset_key"]), safe="/")
        sources.append(source)
    return sources


def format_sources(sources: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[{source['id']}] {source.get('filename', '')} / {source.get('section') or source.get('section_path', '')}"
        f" / 版本 {source.get('version_label') or '未指定'} / 适用条件 {source.get('applicability') or '未知'}"
        f" / 证据类型 {source.get('evidence_modality', 'text')}"
        + (f" / 游戏 {source.get('game_id')} / 发行版 {source.get('edition') or '未知'}"
           f" / 游戏补丁 {source.get('patch') or '未知'} / 模式 {source.get('mode') or '未知'}"
           f" / 来源 {source.get('source_tier') or '未知'}:{source.get('provenance') or '未核实'}"
           f" / URL {source.get('source_url') or '未提供'} / 历史 {source.get('historical', False)}"
           f" / 适用状态 {source.get('compatibility') or '未知'} / 可推荐 {source.get('recommendable', False)}"
           f" / DLC要求 {source.get('requires_dlc') or []} / 仅比较 {source.get('comparison_only', False)}"
           f" / 条件差异 {source.get('out_of_scope_conditions') or []}" if source.get('game_id') else '')
        + f"\n{source.get('content', '')}"
        for source in sources)


def format_context(documents: list[Document]) -> str:
    return format_sources(build_sources(documents))
