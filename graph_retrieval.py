"""Evidence-backed relation traversal; co-occurrence is never an edge.

The local graph is derived from explicit subject/relation/object Markdown tables
and explicit arrow statements. Each edge retains an exact quote and child ID.
It complements hybrid retrieval, not a community-summary GraphRAG pipeline.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Any

from langchain_core.documents import Document


@dataclass(frozen=True)
class Relation:
    subject: str
    predicate: str
    object: str
    evidence_id: str
    filename: str
    source_id: str
    quote: str

    def public(self) -> dict[str, str]:
        return dict(vars(self))


def evidence_key(document: Document) -> str:
    metadata = document.metadata or {}
    return str(metadata.get("chunk_id") or metadata.get("child_chunk_id") or
               sha256((str(metadata.get("source", "")) + document.page_content).encode()).hexdigest()[:24])


def original_document(content: str, metadata: dict[str, Any]) -> Document:
    return Document(page_content=str(metadata.get("original_content") or content), metadata=dict(metadata))


def _cells(line: str) -> list[str]:
    return [cell.strip().strip("`*") for cell in line.strip().strip("|").split("|")]


def _header_kind(value: str) -> str | None:
    value = value.casefold().replace(" ", "")
    groups = {
        "subject": {"主体", "主语", "实体", "subject", "head", "源实体"},
        "predicate": {"关系", "谓词", "predicate", "relation"},
        "object": {"客体", "宾语", "对象", "目标实体", "object", "tail"},
    }
    return next((kind for kind, values in groups.items() if value in values), None)


_ARROW = re.compile(r"^\s*(?:[-*]\s+)?(.{2,80}?)\s*(?:--\s*([^>\n]{1,32}?)\s*-->|—\s*([^→\n]{1,32}?)\s*→)\s*(.{2,80}?)\s*$")


def extract_relations(document: Document) -> list[Relation]:
    """Only parse explicitly named relations, preserving their literal source."""
    metadata = document.metadata or {}
    relations: list[Relation] = []
    columns: dict[str, int] = {}
    # Long-table children may contain only rows; their original header remains
    # metadata, while the quoted edge itself must still occur in child content.
    for header_line in str(metadata.get("table_header") or "").splitlines():
        candidate = {kind: index for index, value in enumerate(_cells(header_line))
                     if (kind := _header_kind(value))}
        if set(candidate) == {"subject", "predicate", "object"}:
            columns = candidate
            break
    for line in document.page_content.splitlines():
        if line.strip().startswith("|"):
            cells = _cells(line)
            candidate = {kind: index for index, value in enumerate(cells)
                         if (kind := _header_kind(value))}
            if set(candidate) == {"subject", "predicate", "object"}:
                columns = candidate
                continue
            if columns and len(cells) > max(columns.values()):
                if all(re.fullmatch(r"[:\-\s]+", value) for value in cells):
                    continue
                values = [cells[columns[k]] for k in ("subject", "predicate", "object")]
            else:
                continue
        else:
            columns = {}
            arrow = _ARROW.match(line)
            if not arrow:
                continue
            values = [arrow[1].strip("`* "), (arrow[2] or arrow[3]).strip(), arrow[4].strip("`* 。.")]
        if all(values) and all(len(value) <= 120 for value in values):
            relations.append(Relation(*values, evidence_key(document), str(metadata.get("filename", "未知资料")),
                                      str(metadata.get("source", "")), line))
    return relations


@dataclass
class GraphExpansion:
    documents: list[Document]
    trace: dict[str, Any]


class EvidenceGraph:
    """A small graph interface hides extraction, traversal and source restoration."""

    def __init__(self, documents: list[Document]) -> None:
        self.documents = {evidence_key(document): document for document in documents}
        self.edges: list[Relation] = []
        self.adjacency: dict[str, list[int]] = defaultdict(list)
        self.labels: dict[str, str] = {}
        seen: set[tuple[str, str, str, str]] = set()
        for document in documents:
            for relation in extract_relations(document):
                key = (relation.subject.casefold(), relation.predicate, relation.object.casefold(), relation.evidence_id)
                if key in seen:
                    continue
                seen.add(key)
                edge_index = len(self.edges)
                self.edges.append(relation)
                for label in (relation.subject, relation.object):
                    node = label.casefold()
                    self.labels.setdefault(node, label)
                    self.adjacency[node].append(edge_index)

    def expand(self, query: str, seeds: list[Document], *, max_hops: int = 2,
               max_queries: int = 3, max_edges: int = 24) -> GraphExpansion:
        normalized = query.casefold()
        anchors = [node for node in self.adjacency if len(node) >= 2 and node in normalized]
        seed_ids = {evidence_key(document) for document in seeds}
        # Edges present in already-retrieved evidence also provide grounded anchors.
        if not anchors:
            for relation in self.edges:
                if relation.evidence_id in seed_ids:
                    anchors.extend((relation.subject.casefold(), relation.object.casefold()))
        anchors = list(dict.fromkeys(anchors))[:12]
        queue = deque((anchor, 0, [self.labels[anchor]], []) for anchor in anchors)
        visited = set(anchors)
        chosen: dict[int, Relation] = {}
        paths: list[dict[str, Any]] = []
        while queue and len(chosen) < max_edges:
            node, depth, nodes, path_edges = queue.popleft()
            if depth >= max_hops:
                continue
            for index in self.adjacency[node]:
                relation = self.edges[index]
                if index not in chosen and len(chosen) >= max_edges:
                    break
                chosen[index] = relation
                other = relation.object.casefold() if relation.subject.casefold() == node else relation.subject.casefold()
                if other in visited:
                    continue
                visited.add(other)
                next_nodes = [*nodes, self.labels[other]]
                next_edges = [*path_edges, relation.public()]
                paths.append({"nodes": next_nodes, "edges": next_edges})
                queue.append((other, depth + 1, next_nodes, next_edges))
        documents: list[Document] = []
        added: set[str] = set()
        expansion_queries: list[str] = []
        for relation in chosen.values():
            if relation.evidence_id not in added:
                document = self.documents[relation.evidence_id]
                metadata = dict(document.metadata)
                metadata.update(candidate_origin="graph", retrieval_method="graph", graph_rank=len(documents) + 1)
                documents.append(Document(page_content=document.page_content, metadata=metadata))
                added.add(relation.evidence_id)
            # Follow discovered entities through ordinary text as well as structured relations.
            for label in (relation.object, relation.subject):
                if label.casefold() not in normalized and label not in expansion_queries:
                    expansion_queries.append(label)
        return GraphExpansion(documents, {
            "enabled": True, "node_count": len(self.adjacency), "edge_count": len(self.edges),
            "matched_edges": [relation.public() for relation in chosen.values()],
            "paths": paths[:max_edges], "expansion_queries": expansion_queries[:max_queries],
            "extraction_method": "explicit_relations", "max_hops": max_hops,
        })


class GraphCache:
    """Refresh a collection's graph whenever its actual evidence snapshot changes."""

    def __init__(self) -> None:
        self._graphs: dict[str, tuple[str, EvidenceGraph]] = {}

    def load(self, collection_name: str, raw_collection: Any) -> EvidenceGraph:
        stored = raw_collection.get(include=["documents", "metadatas"])
        documents = [original_document(content, metadata or {})
                     for content, metadata in zip(stored.get("documents") or [], stored.get("metadatas") or []) if content]
        snapshot = sha256("\n".join(sorted(
            evidence_key(document) + sha256(document.page_content.encode()).hexdigest()
            for document in documents)).encode()).hexdigest()
        existing = self._graphs.get(collection_name)
        if existing and existing[0] == snapshot:
            return existing[1]
        graph = EvidenceGraph(documents)
        self._graphs[collection_name] = snapshot, graph
        return graph


graph_cache = GraphCache()
