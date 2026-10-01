"""Budgeted evidence windows, independent of retrieval/model infrastructure.

The estimator is a UTF-8 byte heuristic, NOT a model tokenizer. Budgets cover
returned raw content plus a fixed 32-token document-envelope allowance; they do
not promise the same bound for a model's complete chat prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import math
from typing import Any
from langchain_core.documents import Document


@dataclass(frozen=True)
class ContextPack:
    documents: list[Document]
    stats: dict[str, Any]


def estimate_tokens(text: str) -> int:
    """Deterministic approximate count, deliberately not a model tokenizer."""
    return math.ceil(len(text.encode("utf-8")) / 3)


def _raw(document: Document) -> str:
    return str(document.metadata.get("original_content", document.page_content))


def _merge(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(set(windows)):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _span(metadata: dict, raw: str, a: int, b: int) -> dict[str, Any]:
    span: dict[str, Any] = {"start_char": a, "end_char": b, "content": raw[a:b], "offset_scope": "parent"}
    for key in ("page", "page_number", "section", "section_path", "block_type", "block_index", "element_index"):
        if metadata.get(key) is not None:
            span[key] = metadata[key]
    base_char = metadata.get("parent_start_char")
    base_line = metadata.get("parent_start_line")
    if base_char is not None:
        span.update(start_char=int(base_char) + a, end_char=int(base_char) + b, offset_scope="source")
    elif metadata.get("location_scope") == "element":
        base_element = int(metadata.get("parent_element_start_char") or 0)
        span.update(start_char=base_element + a, end_char=base_element + b, offset_scope="element")
    if base_line is not None:
        span.update(start_line=int(base_line) + raw.count("\n", 0, a),
                    end_line=int(base_line) + raw.count("\n", 0, max(a, b - 1)))
    span["start_offset"] = span["start_char"]
    span["end_offset"] = span["end_char"]
    span.setdefault("start_line", None)
    span.setdefault("end_line", None)
    return span


def compose_context(documents: list[Document], token_budget: int = 6000,
                    max_documents: int = 8, neighbor_chars: int = 240) -> ContextPack:
    """Merge same-parent hit windows, diversify sources and fit an estimated budget.

    Output ``page_content`` contains only original text (disjoint raw windows may
    be separated by blank lines). ``evidence_spans``/``context_windows`` describe
    each real window; no combined line range is asserted for disjoint windows.
    ``evidence`` retains each included child hit and ``child_chunk_ids`` its IDs.
    Old indexes without offsets use exact substring lookup, never invented page
    spans. Input documents and their metadata are not mutated.
    """
    token_budget = max(0, int(token_budget))
    max_documents = max(0, int(max_documents))
    neighbor_chars = max(0, int(neighbor_chars))
    groups: dict[tuple[str, str], dict] = {}
    seen: set[tuple[str, str, str]] = set()
    for rank, document in enumerate(documents):
        metadata = dict(document.metadata or {})
        raw_child = _raw(document)
        if not raw_child.strip():
            continue
        source = str(metadata.get("source") or metadata.get("filename") or "unknown")
        child_id = str(metadata.get("chunk_id") or sha1(raw_child.encode("utf-8")).hexdigest())
        unique = (source, child_id, raw_child)
        if unique in seen:
            continue
        seen.add(unique)
        parent_raw = metadata.get("parent_content")
        parent_key = str(metadata.get("parent_id") or child_id)
        raw = str(parent_raw) if parent_raw else raw_child
        a = metadata.get("child_start_char") if parent_raw else 0
        b = metadata.get("child_end_char") if parent_raw else len(raw_child)
        if not isinstance(a, int) or not isinstance(b, int) or raw[a:b] != raw_child:
            a = raw.find(raw_child)
            b = a + len(raw_child)
        if a < 0:
            # Never expand an unlocatable hit into unrelated parent text.
            raw, a, b, parent_key = raw_child, 0, len(raw_child), child_id
            parent_raw = None
        key = (source, parent_key)
        if key in groups and groups[key]["raw"] != raw:
            key = (source, parent_key + ":" + sha1(raw.encode("utf-8")).hexdigest())
        if not parent_raw:
            metadata["parent_start_char"] = metadata.get("start_char")
            metadata["parent_start_line"] = metadata.get("start_line")
            if metadata.get("location_scope") == "element":
                metadata["parent_element_start_char"] = metadata.get("element_start_char", 0)
        group = groups.setdefault(key, {"raw": raw, "metadata": metadata, "windows": [], "hits": [], "source": source, "rank": rank})
        group["windows"].append((max(0, a - neighbor_chars), min(len(raw), b + neighbor_chars)))
        hit = {key: metadata[key] for key in ("chunk_id", "source", "page", "page_number", "start_line", "end_line", "section", "section_path", "block_type", "block_index", "retrieval_method", "rrf_score", "rerank_score") if metadata.get(key) is not None}
        hit.update(child_chunk_id=child_id, content=raw_child, parent_start_char=a, parent_end_char=b)
        group["hits"].append(hit)
    # First round: best hit from each source; subsequent rounds preserve within-source ranking.
    queues: dict[str, list[dict]] = {}
    for group in groups.values():
        queues.setdefault(group["source"], []).append(group)
    ordered = []
    while any(queues.values()):
        for queue in queues.values():
            if queue:
                ordered.append(queue.pop(0))
    selected: list[Document] = []
    used = 0
    included_ids: set[tuple[str, str]] = set()
    # Do not reserve so many envelopes that a tiny budget skips the best hits.
    capacity = min(max_documents, max(1, token_budget // 64)) if token_budget > 32 else 0
    candidates = ordered[:capacity]
    for index, group in enumerate(candidates):
        raw, metadata = group["raw"], dict(group["metadata"])
        remaining_groups = len(candidates) - index
        allowance = (token_budget - used) // max(1, remaining_groups)
        if allowance <= 32:
            continue
        header = str(metadata.get("table_header") or "")
        header_base = metadata.get("table_header_start_char")
        parent_base = metadata.get("parent_start_char")
        separate_header = ""
        header_window = None
        if header and isinstance(header_base, int) and isinstance(parent_base, int):
            header_a = header_base - parent_base
            header_b = header_a + len(header)
            if 0 <= header_a < header_b <= len(raw) and raw[header_a:header_b] == header:
                header_window = (header_a, header_b)
            else:
                separate_header = header
        header_cost = estimate_tokens(separate_header + "\n\n") if separate_header else 0
        # Omit an unaffordable external header rather than exceed the budget.
        if header_cost + 32 >= allowance:
            separate_header, header_cost = "", 0
        allowance -= header_cost
        windows = _merge(group["windows"] + ([header_window] if header_window else []))
        # Prefer evidence over neighborhood when fair-share allocation is tight.
        if estimate_tokens("\n\n".join(raw[a:b] for a, b in windows)) + 32 > allowance:
            windows = _merge([(hit["parent_start_char"], hit["parent_end_char"]) for hit in group["hits"]])
        kept: list[tuple[int, int]] = []
        for a, b in windows:
            current = "\n\n".join(raw[x:y] for x, y in kept)
            available = allowance - 32 - estimate_tokens(current + ("\n\n" if kept else ""))
            if available <= 0:
                break
            if estimate_tokens(raw[a:b]) > available:
                low, high = a, b
                while low < high:
                    mid = (low + high + 1) // 2
                    if estimate_tokens(raw[a:mid]) <= available:
                        low = mid
                    else:
                        high = mid - 1
                b = low
            if b > a and raw[a:b].strip():
                kept.append((a, b))
        content = "\n\n".join(raw[a:b] for a, b in kept)
        if separate_header and content:
            content = separate_header + "\n\n" + content
        cost = estimate_tokens(content) + 32
        if not content.strip() or used + cost > token_budget:
            continue
        evidence = []
        for hit in group["hits"]:
            a, b = hit["parent_start_char"], hit["parent_end_char"]
            for x, y in kept:
                left, right = max(a, x), min(b, y)
                if left < right:
                    entry = dict(hit)
                    entry.update(_span(metadata, raw, left, right), parent_start_char=left, parent_end_char=right,
                                 truncated=left != a or right != b)
                    evidence.append(entry)
                    included_ids.add((group["source"], hit["child_chunk_id"]))
        if not evidence:
            continue
        for key in ("parent_content", "original_content", "retrieval_context_prefix", "table_header", "start_line", "end_line", "start_char", "end_char", "child_start_char", "child_end_char"):
            metadata.pop(key, None)
        spans = [_span(group["metadata"], raw, a, b) for a, b in kept]
        if separate_header:
            header_span = {"content": separate_header, "start_offset": metadata["table_header_start_char"],
                           "end_offset": metadata["table_header_end_char"], "offset_scope": "source",
                           "start_char": metadata["table_header_start_char"], "end_char": metadata["table_header_end_char"],
                           "start_line": metadata.get("table_header_start_line"),
                           "end_line": metadata.get("table_header_end_line"), "block_type": "table_header"}
            spans.insert(0, header_span)
        metadata.update(evidence=evidence, evidence_spans=spans, context_windows=spans,
                        child_chunk_ids=list(dict.fromkeys(hit["child_chunk_id"] for hit in evidence)),
                        context_composed=True, expanded_from_child=bool(group["metadata"].get("parent_content")),
                        estimated_tokens=cost)
        if len(spans) == 1:
            for key in ("start_line", "end_line", "start_char", "end_char"):
                if key in spans[0]:
                    metadata[key] = spans[0][key]
        selected.append(Document(page_content=content, metadata=metadata))
        used += cost
    return ContextPack(selected, {"estimated_tokens": used, "token_budget": token_budget,
                                 "input_count": len(documents), "selected_count": len(selected),
                                 "omitted_count": max(0, len(documents) - len(included_ids)),
                                 "estimator": "utf8_bytes_div_3_ceil_plus_32_per_document_not_model_tokenizer"})
