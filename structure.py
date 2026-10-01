"""Structure-aware source spans; generated retrieval hints never change offsets."""
from __future__ import annotations

import json
import re
from langchain_core.documents import Document


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _pieces(text: str, start: int, end: int, size: int):
    """Prefer complete lines; split exceptionally long lines without inventing text."""
    while start < end:
        stop = min(end, start + max(1, size))
        if stop < end:
            newline = text.rfind("\n", start, stop)
            if newline > start:
                stop = newline + 1
        yield start, stop
        start = stop


def _blocks(text: str, markdown: bool):
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    hierarchy: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start = i
        heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", lines[i]) if markdown else None
        setext = markdown and i + 1 < len(lines) and re.match(r"^ {0,3}(=+|-+)\s*$", lines[i + 1])
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})", lines[i]) if markdown else None
        header = ""
        if heading or setext:
            level = len(heading[1]) if heading else (1 if lines[i + 1].lstrip().startswith("=") else 2)
            title = heading[2] if heading else lines[i].strip()
            hierarchy = [(depth, name) for depth, name in hierarchy if depth < level]
            hierarchy.append((level, title))
            kind = "heading"
            i += 1 if heading else 2
        elif fence:
            kind = "code"
            marker = fence[1]
            i += 1
            while i < len(lines):
                closing = re.match(r"^ {0,3}(" + re.escape(marker[0]) + r"{" + str(len(marker)) + r",})\s*$", lines[i])
                i += 1
                if closing:
                    break
        elif markdown and i + 1 < len(lines) and "|" in lines[i] and re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[i + 1]):
            kind = "table"
            header = lines[i] + lines[i + 1]
            i += 2
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                i += 1
        else:
            kind = "paragraph"
            i += 1
            while i < len(lines) and lines[i].strip():
                if markdown and (re.match(r"^ {0,3}(#{1,6})\s+", lines[i]) or re.match(r"^ {0,3}(`{3,}|~{3,})", lines[i])):
                    break
                if markdown and i + 1 < len(lines) and "|" in lines[i] and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
                    break
                i += 1
        yield offsets[start], offsets[i], kind, [name for _, name in hierarchy], header


def structure_parents(documents: list[Document], full_text: str | None, markdown: bool, parent_size: int) -> list[Document]:
    """Return raw parent spans with typed structure and source-relative locations."""
    parents: list[Document] = []
    if full_text is not None:
        base = dict(documents[0].metadata) if documents else {}
        for block_index, (start, end, kind, section, header) in enumerate(_blocks(full_text, markdown)):
            for part, (a, b) in enumerate(_pieces(full_text, start, end, parent_size)):
                raw = full_text[a:b]
                if not raw.strip():
                    continue
                metadata = dict(base)
                metadata.update(block_type=kind, block_index=block_index, block_part=part,
                                section=" > ".join(section), section_path=json.dumps(section, ensure_ascii=False),
                                start_char=a, end_char=b, start_line=_line(full_text, a),
                                end_line=_line(full_text, b - 1), location_scope="source")
                prefix = ("Section: " + " > ".join(section) + "\n") if section else ""
                if header:
                    metadata["table_header"] = header
                    metadata["table_header_start_char"] = start
                    metadata["table_header_end_char"] = start + len(header)
                    metadata["table_header_start_line"] = _line(full_text, start)
                    metadata["table_header_end_line"] = _line(full_text, start + len(header) - 1)
                    prefix += "Table columns:\n" + header
                metadata["retrieval_context_prefix"] = prefix
                parents.append(Document(page_content=raw, metadata=metadata))
        return parents
    section = ""
    for element_index, document in enumerate(documents):
        metadata = dict(document.metadata)
        category = str(metadata.get("category") or metadata.get("type") or "text")
        if metadata.get("parent_id") is not None:
            metadata["element_parent_id"] = metadata["parent_id"]
        if category.lower() == "title":
            section = document.page_content.strip()
        if metadata.get("page_number") is not None:
            metadata.setdefault("page", metadata["page_number"])
        metadata.update(block_type=category, block_index=element_index, section=section,
                        location_scope="element", element_index=element_index)
        metadata["retrieval_context_prefix"] = "Section: " + section + "\n" if section else ""
        for part, (a, b) in enumerate(_pieces(document.page_content, 0, len(document.page_content), parent_size)):
            part_metadata = dict(metadata, block_part=part, element_start_char=a, element_end_char=b)
            parents.append(Document(page_content=document.page_content[a:b], metadata=part_metadata))
    return parents


def structure_children(parent: Document, child_size: int) -> list[Document]:
    """Split within one structural block, keeping offsets relative to raw parent."""
    children = []
    raw = parent.page_content
    for a, b in _pieces(raw, 0, len(raw), child_size):
        if not raw[a:b].strip():
            continue
        metadata = dict(parent.metadata, child_start_char=a, child_end_char=b)
        if metadata.get("location_scope") == "source":
            metadata.update(start_char=parent.metadata["start_char"] + a,
                            end_char=parent.metadata["start_char"] + b,
                            start_line=parent.metadata["start_line"] + raw.count("\n", 0, a),
                            end_line=parent.metadata["start_line"] + raw.count("\n", 0, b - 1))
        else:
            metadata["element_start_char"] = parent.metadata.get("element_start_char", 0) + a
            metadata["element_end_char"] = parent.metadata.get("element_start_char", 0) + b
        children.append(Document(page_content=raw[a:b], metadata=metadata))
    return children
