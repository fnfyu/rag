"""Run focused capability cases, with an explicitly scripted offline mode.

Offline exercises real structure/BM25/graph/composition/orchestration and exact
quote anchoring, but NOT LLM quality. Live uses configured embeddings and Ollama
without requiring a PostgreSQL conversation. Never label offline output as a
model benchmark or answer-quality score.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
import jieba

from backend import get_rag_service
from claim_audit import audit_answer
from config import Settings
from context_composer import compose_context
from graph_retrieval import EvidenceGraph, extract_relations
from research import ResearchEngine
from retrieval import CrossEncoderReranker, HybridRetriever
from search import PROMPT, _build_sources, _format_context
from structure import structure_children, structure_parents
from langchain_core.output_parsers import StrOutputParser

CASES_PATH = ROOT / "evaluation" / "research" / "cases.json"
CORPUS = CASES_PATH.parent / "corpus"
COLLECTION = "research_capabilities_v1"


class ScriptedResearchModel:
    """Annotated control-flow fixture. Does not infer or measure model quality."""

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case

    def bind(self, **kwargs: Any) -> ScriptedResearchModel:
        return self

    async def ainvoke(self, messages: list[tuple[str, str]]) -> Any:
        instruction, payload = messages[0][1], json.loads(messages[1][1])
        if instruction.startswith("拆解"):
            result = {"tasks": [{key: item[key] for key in ("id", "question", "depends_on")} for item in self.case["tasks"]]}
        else:
            evidence = payload["evidence"]
            text = "\n".join(item["content"] for item in evidence)
            coverage, missing = [], []
            for task in self.case["tasks"]:
                if all(required in text for required in task["required"]):
                    ids = [item["id"] for item in evidence if any(required in item["content"] for required in task["required"])]
                    coverage.append({"task_id": task["id"], "evidence_ids": ids})
                else:
                    missing.append({"task_id": task["id"], "query": task["followup"], "reason": "离线标注条件尚未覆盖（非模型判断）"})
            result = {"coverage": coverage, "missing": missing, "sufficient": not missing}
        return SimpleNamespace(content=json.dumps(result, ensure_ascii=False))


class ScriptedAuditModel:
    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = fixture

    def bind(self, **kwargs: Any) -> ScriptedAuditModel:
        return self

    async def ainvoke(self, messages: list[tuple[str, str]]) -> Any:
        payload = json.loads(messages[1][1])
        if "units" in payload:
            claims = []
            for unit in payload["units"]:
                text = re.split(r"\[S\d+\]", unit["text"])[0].rstrip()
                if text:
                    claims.append({"unit_id": unit["unit_id"], "text": text,
                                   "answer_start": unit["answer_start"], "answer_end": unit["answer_start"] + len(text)})
        else:
            claims = [{"id": item["id"], "verdict": self.fixture["expected_verdict"],
                       "reason": "离线预置语义结果，仅用于验证原文锚定与状态传递",
                       "evidence": [{"source_id": "S1", "quote": self.fixture["quote"]}] if self.fixture["quote"] else []}
                      for item in payload["claims"]]
        return SimpleNamespace(content=json.dumps({"claims": claims}, ensure_ascii=False))


class MemoryCollection:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents

    def get(self, **kwargs: Any) -> dict[str, Any]:
        return {"documents": [document.page_content for document in self.documents],
                "metadatas": [document.metadata for document in self.documents]}


class OfflineEvidence:
    def __init__(self, documents: list[Document], case: dict[str, Any]) -> None:
        self.settings = Settings(_env_file=None, final_context_k=2, context_token_budget=3000,
                                 context_max_documents=8, research_max_rounds=3,
                                 research_time_budget_seconds=30, research_planning_token_budget=24000)
        self.llm = ScriptedResearchModel(case)
        self.raw = MemoryCollection(documents)
        self.client = SimpleNamespace(get_or_create_collection=lambda _: self.raw)
        lexical = BM25Retriever.from_documents(documents, preprocess_func=lambda text: jieba.lcut(text.casefold()))
        lexical.k = 2
        self.retriever = HybridRetriever(None, lexical, 20, 2, 60, CrossEncoderReranker(None, 2), True)

    def retrieve_trace(self, query: str, collection_name: str, **kwargs: Any) -> Any:
        return self.retriever.retrieve_with_trace(query, method="bm25", **kwargs)

    def compose_context(self, documents: list[Document]) -> Any:
        return compose_context(documents, self.settings.context_token_budget, self.settings.context_max_documents,
                               self.settings.context_neighbor_chars)


def offline_documents() -> list[Document]:
    documents = []
    for path in sorted(CORPUS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        parents = structure_parents([Document(page_content=text)], text, True, 1800)
        for parent_index, parent in enumerate(parents):
            for child_index, child in enumerate(structure_children(parent, 800)):
                metadata = dict(child.metadata, source=f"research:{path.name}", filename=path.name,
                                chunk_id=f"research:{path.name}:{parent_index}:{child_index}",
                                parent_id=f"research:{path.name}:parent:{parent_index}", parent_content=parent.page_content,
                                original_content=child.page_content,
                                parent_start_char=parent.metadata["start_char"], parent_start_line=parent.metadata["start_line"])
                prefix = metadata.get("retrieval_context_prefix", "")
                documents.append(Document(page_content=prefix + "\n" + child.page_content if prefix else child.page_content,
                                          metadata=metadata))
    return documents


def structure_and_graph_checks(documents: list[Document]) -> dict[str, Any]:
    raw = [Document(page_content=document.metadata["original_content"], metadata=document.metadata) for document in documents]
    graph = EvidenceGraph(raw)
    expansion = graph.expand("Orion", [], max_hops=2)
    edges = expansion.trace["matched_edges"]
    assert any(edge["subject"] == "RelayMesh" and edge["object"] == "AtlasQueue" for edge in edges)
    assert not any(edge.subject == "Polaris" and edge.object == "AtlasQueue" for edge in graph.edges)
    for edge in graph.edges:
        assert edge.quote in graph.documents[edge.evidence_id].page_content
    pack = compose_context(raw, token_budget=900, max_documents=6)
    assert pack.stats["estimated_tokens"] <= 900
    for document in pack.documents:
        for window in document.metadata["context_windows"]:
            source_text = (CORPUS / document.metadata["filename"]).read_text(encoding="utf-8")
            assert source_text[window["start_offset"]:window["end_offset"]] == window["content"]
    # Header restoration for long-table row-only children, including graph extraction.
    table = "| 主体 | 关系 | 客体 |\n| --- | --- | --- |\n" + "".join(f"| 模块{i} | 依赖 | 队列{i} |\n" for i in range(30))
    parents = structure_parents([Document(page_content=table)], table, True, 120)
    children = []
    for pi, parent in enumerate(parents):
        for ci, child in enumerate(structure_children(parent, 90)):
            child.metadata.update(source="long-table", chunk_id=f"table:{pi}:{ci}", parent_id=f"table-parent:{pi}",
                                  parent_content=parent.page_content, original_content=child.page_content,
                                  parent_start_char=parent.metadata["start_char"], parent_start_line=parent.metadata["start_line"])
            children.append(child)
    last = children[-1]
    assert extract_relations(last), "row-only table child lost its original header for relation extraction"
    table_pack = compose_context([last], token_budget=300)
    assert table_pack.documents and "| 主体 | 关系 | 客体 |" in table_pack.documents[0].page_content
    for window in table_pack.documents[0].metadata["context_windows"]:
        assert table[window["start_offset"]:window["end_offset"]] == window["content"]
    return {"budget_estimate_within_limit": True, "windows_exactly_located": True,
            "relation_quotes_anchored": True, "cooccurrence_not_an_edge": True,
            "long_table_header_restored": True, "two_hop_path_found": True,
            "node_count": len(graph.adjacency), "edge_count": len(graph.edges)}


async def main(args: argparse.Namespace) -> None:
    dataset = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = [case for case in dataset["cases"] if not args.case or case["id"] == args.case]
    if not cases:
        raise ValueError(f"unknown case: {args.case}")
    documents = offline_documents()
    report: dict[str, Any] = {"dataset": dataset["id"], "mode": args.mode,
                              "is_model_quality_benchmark": False,
                              "provenance": dataset["provenance"], "cases": []}
    service = None
    if args.mode == "live":
        service = get_rag_service()
        if not service.settings.embedding_model or not service.settings.ollama_model:
            raise RuntimeError("Live mode requires EMBEDDING_MODEL and OLLAMA_MODEL; no fabricated model results are produced.")
        for path in sorted(CORPUS.glob("*.md")):
            await asyncio.to_thread(service.index_document, path, COLLECTION, f"research:{path.name}", path.name)
        report["model"] = service.settings.ollama_model
    else:
        report["model"] = "scripted_fixture_not_a_real_llm"
        report["checks"] = structure_and_graph_checks(documents)
    for case in cases:
        active = service if service is not None else OfflineEvidence(documents, case)
        engine = ResearchEngine(active)
        result = None
        async for event in engine.run(case["question"], COLLECTION, mode=case["mode"], graph_enabled=True):
            if event.kind == "result":
                result = event.data
        if result is None:
            raise RuntimeError("research engine returned no result")
        sources = _build_sources(result.documents)
        item = {"id": case["id"], "question": case["question"], "expected_behavior": case["expected_behavior"],
                "trace": result.trace, "sources": sources}
        if service is not None:
            chain = PROMPT | service.llm | StrOutputParser()
            async with asyncio.timeout(service.settings.generation_timeout_seconds):
                answer = await chain.ainvoke({"context": _format_context(result.documents), "history": "（无）",
                                             "research_status": json.dumps(result.trace["research"], ensure_ascii=False), "query": case["question"]})
            item["answer"] = answer
            item["semantic_audit"] = await audit_answer(answer, sources, service.llm,
                                                        timeout_seconds=service.settings.claim_audit_timeout_seconds)
        report["cases"].append(item)
        state = result.trace["research"]
        print(f"{case['id']}: {state['effective_mode']} / {len(state['rounds'])} rounds / {state['stop_reason']} / {len(sources)} sources")
    report["semantic_fixtures"] = []
    for fixture in dataset["semantic_fixtures"]:
        content = fixture["content"]
        sources = [{"id": "S1", "filename": "literal-fixture", "content": content,
                    "context_windows": [{"content": content, "start_line": 1, "end_line": 1}]}]
        llm = service.llm if service is not None else ScriptedAuditModel(fixture)
        audit = await audit_answer(fixture["answer"], sources, llm)
        if args.mode == "offline":
            assert audit["claims"] and audit["claims"][0]["verdict"] == fixture["expected_verdict"]
            for claim in audit["claims"]:
                assert fixture["answer"][claim["answer_start"]:claim["answer_end"]] == claim["text"]
                for evidence in claim["evidence"]:
                    assert evidence["quote"] in content
        report["semantic_fixtures"].append({**fixture, "audit": audit})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {args.output}")
    if args.mode == "offline":
        print("Offline uses scripted model decisions: proves feature wiring and exact anchors, NOT real-model answer quality.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--case", help="run a single named case")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "research-capabilities.json")
    asyncio.run(main(parser.parse_args()))
