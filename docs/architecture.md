# Evidence RAG architecture

## Design goals

1. **Evidence first**: retrieval results are labeled before generation so the model can cite `[S#]`; the client receives the same labels, excerpts and source locations.
2. **Evaluable by default**: a versioned child-evidence qrels set compares vector, BM25, RRF and rerank using Recall@K, MRR and graded nDCG@K without calling an LLM.
3. **Degrades visibly**: query rewrite, candidate retrieval and reranking failures produce a retrieval trace with an effective strategy instead of silently claiming success.
4. **Usable without a model at boot**: process startup should not fail because a developer has not downloaded an embedding model or started Ollama.
5. **Configurable by environment**: no machine-specific paths, ports, database credentials, or model names are embedded in application code.
6. **Bounded responsibility**: routers coordinate requests; `RAGService` owns model/vector resources; `HybridRetriever` owns strategy policy; [reporting.py](<../reporting.py>) owns chapter research, checkpoints, stable evidence IDs and local paragraph revisions; [workspace_store.py](<../workspace_store.py>) owns workspace/version transactions; [evaluation.py](<../evaluation.py>) owns the ranking metric contract.

## Domain contract

- A **knowledge base** owns an isolated collection and its uploaded materials.
- A **child evidence** is the stable judgment unit for offline retrieval evaluation. Its ID is currently `source_id:parent_index:child_index`; a changed chunking configuration requires a new corpus snapshot.
- A **retrieval strategy** is one of `vector`, `bm25`, `rrf`, or `rerank`. `rerank` means RRF candidate fusion followed by Cross-Encoder scoring; it is not an independent recall source.
- A **retrieval trace** records original/retrieval query, candidate count, stage status, effective strategy, fallback reason, duration and safe error codes.
- A **citation audit** checks source-marker structure only. It cannot prove semantic entailment.

The full terminology is recorded in [`CONTEXT.md`](../CONTEXT.md); the evaluation trade-off is recorded in [`docs/adr/0001-retrieval-evaluation-contract.md`](adr/0001-retrieval-evaluation-contract.md).

## V3 Souls specialization

- [souls_domain.py](<../souls_domain.py>) supplies five distinct game catalogs, literal edition/patch conditions and five-chapter guide drafts. Nightreign is not an Elden Ring DLC or free-stat build system.
- [souls_sources.py](<../souls_sources.py>) captures registered primary sources and genuine publisher Steam announcements; external partner feeds and explicit cross-game promotions are excluded. Actual source/publication/capture time and content hashes are preserved, without claiming latestness.
- [souls_api.py](<../souls_api.py>) previews sources, re-fetches a selected article and persists/indexes its independent version; identical semantic captures reuse versions. Conditions are the captured source's, not silently borrowed from the player's current ownership/mode.
- PostgreSQL adds `knowledge_bases.game_profile` and `document_versions.domain_metadata`; old evidence remains unclassified. User annotations are `user_declared`, not a verified publisher capture. Existing indexed metadata is enriched from current database version records before use.
- `ScopedEvidence` constrains vector, scoped BM25 and graph snapshots by compatible source IDs before recall. An empty game scope stays empty rather than falling back to the full collection. Explicit guide comparisons can retain same-game incompatible conditions as comparison-only, never as current recommendations.
- Chapter retrieval includes the actual goal and game context; generation and claim audits receive source/player conditions. Evidence IDs include source conditions so annotations do not change the meaning of unchanged citations or archived reports.
- [souls_impact.py](<../souls_impact.py>) anchors change lines and associates existing report references/entities; optional semantic candidates must point to real change and claim IDs. Results are `needs_confirmation`, never automatic invalidation.
- [souls_tools.py](<../souls_tools.py>) performs Decimal player/table arithmetic, not invented damage simulation. Nightreign exposes explicit value comparison rather than a borrowed stat/weight model.
- [SoulsWorkspace.vue](<../my-web/src/components/SoulsWorkspace.vue>) connects catalogs, conditions, official captures, guide drafts, impact candidates and calculations to the existing research/document views.

Operational details and authentic starter corpus: [V3 guide](<souls-workbench-v3.md>) and [source research](<souls-official-sources.md>). Background execution remains in-process FastAPI with persistent document/task checkpoints, not distributed scheduling.

## Request flow

### Upload and indexing

1. `POST /uploads` validates basename, extension and streaming byte count.
2. The file is saved under `data/uploads/<upload-id>.<ext>` rather than its user-controlled filename.
3. A FastAPI background task records `queued → parsing → chunking → embedding → persisting → ready` (or `error`) and exposes the current task plus recent events.
4. Each document version owns an independent `source=version_id`; same-name materials share a document series but retain separate indexed evidence. Identical bytes and version description may reuse a ready version. The migration preserves legacy `conversation_id + normalized filename` source IDs and existing collections without reindexing.
5. PostgreSQL records document metadata; the client polls the in-process lifecycle. A multi-instance deployment must replace the registry with a durable task queue and job table.

### Chat and citations

1. `POST /chat/{conversation_id}` resolves the conversation's knowledge-base collection; multiple conversations share one knowledge base's materials.
2. Contextual follow-up questions are optionally rewritten by Ollama into a standalone retrieval query. Rewrite timeout/failure keeps the original query and records the outcome in the trace.
3. `RAGService.retrieve_trace` asks `HybridRetriever.retrieve_with_trace` for the default `rerank` plan. Vector and BM25 candidates are independently retrieved, fused with Reciprocal Rank Fusion, and optionally reranked. If one candidate source fails, the other remains usable; if reranking is absent or fails, `effective_method=rrf` is explicit.
4. `ResearchEngine` routes auto/quick/research requests. Research plans dependent subquestions, retrieves raw child evidence, deduplicates/interleaves task results, optionally traverses explicit evidence relations, and assesses gaps against evidence that actually fits the composed answer context. It stops for sufficiency, lack of new evidence, or bounded rounds/time/estimated planning tokens. Progress snapshots are observable actions, never hidden chain-of-thought.
5. `context_composer.compose_context` merges same-parent hit windows, retains multiple child IDs, restores original table-header windows, diversifies sources, and fits the declared approximate evidence budget. Disjoint windows have separate locations; no false combined line interval is asserted. Offline retrieval evaluation continues to use unexpanded child IDs.
6. Composed raw windows receive `[S1]`, `[S2]`, etc. `citations.py` checks numbering structure; `claim_audit.audit_answer` separately extracts facts and batch-judges support/contradiction/insufficiency using exact source quotes. The configured Ollama model is reused, not an independent truth oracle, and the answer is not automatically rewritten.
7. SSE sends `research-progress`, `retrieval-trace`, `data-sources`, text deltas, `claim-audit-start`, `claim-audit`, and `citation-validation`. Source payloads include the complete supplied evidence and independently located windows, not filesystem paths. Retrieval/generation failures after streaming begins are explicit stream errors.
8. User and completed assistant turns are persisted. Research resides inside `retrieval_trace.research`; semantic audit resides inside `citation_validation.semantic_audit`, so existing JSONB columns support history without a new SQL migration. Conversation responses also expose `researchTrace` and `claimAudit` convenience fields.

## V2 research delivery flow

1. A knowledge base owns its collection and document series; conversations and persistent research tasks refer to it. The PostgreSQL migration retains old identities. See [ownership decision](<adr/0002-workspace-versioned-evidence.md>).
2. Users confirm editable outlines and version/applicability scope. [reporting.py](<../reporting.py>) uses the same scoped sources for vector, BM25 and graph recall before composing chapter evidence.
3. Each chapter uses the V1 research engine, generation and audit; its draft, evidence, issues and progress are checkpointed in the task context. Restart means explicit resume, not distributed automatic job recovery. Completed chapters with matching goal/outline/scope signatures can be retained.
4. A report-wide evidence pool allocates stable `[S#]` IDs. Local revisions append evidence instead of relabeling unchanged chapters. Selected/problem claim offsets determine paragraph replacements, and non-target paragraphs are preserved literally; general chapter requests stay chapter-scoped.
5. Saving a report appends an immutable report version and updates the current task report in one transaction. Compare, export and restore do not mutate previous snapshots; restore appends a new version and restores its research scope.
6. [version_analysis.py](<../version_analysis.py>) compares literal original text and anchors every displayed semantic conflict quote to its version; it links potentially affected report sections/claims. Upload order never chooses truth or applicability.
7. [multimodal.py](<../multimodal.py>) uses PyMuPDF's actual text geometry, page PNG and extracted tables. The independent vision model receives actual image data. Captions are `visual_description`, not literal source text; evidence serialization and claim audit retain this distinction.
8. [table_tools.py](<../table_tools.py>) asks the model only to choose bounded operations; [table_analysis.py](<../table_analysis.py>) calculates with Decimal and records source rows/formulas. CSV/Markdown operations read full pinned tables rather than assuming a retrieved excerpt is the entire table.

Full workflow/API/configuration: [V2 guide](<research-workbench-v2.md>).

## Retrieval evaluation flow

1. `evaluation/dataset.json` contains 19 self-built Chinese questions, a corpus snapshot, exhaustive qrels and graded relevance labels.
2. `scripts/index_evaluation_corpus.py` indexes the checked-in corpus with deterministic `eval:<filename>:0:0` child IDs and writes a file-hash manifest.
3. `scripts/evaluate_retrieval.py` runs all requested strategies on the same cases and cutoffs. The metric module deduplicates hits, uses `grade >= 1` for Recall/MRR and `2^grade-1` gain for nDCG.
4. The JSON report contains dataset fingerprint, run configuration, per-strategy summaries, per-query ranked IDs and safe retrieval traces. Each requested method also carries the strategy that actually produced its results (`run.effective_strategies` plus `summary.<method>.effective_method`, `degraded_cases`, `failed_cases`), so `rerank` fallback is never presented as a real Cross-Encoder result.
5. `GET /evaluations/retrieval/dataset` exposes dataset provenance; `GET /evaluations/retrieval/latest` exposes the latest real report or an explicit `not_run` state. The Vue evaluation view refuses to invent percentages.

## Operational behavior

- `/health` reports configuration readiness, retrieval strategy and whether expensive resources were initialized. It never creates embeddings, loads the reranker or calls Ollama.
- `DATABASE_URL` and `EMBEDDING_MODEL` are required only when an operation needs them. Missing database configuration is an HTTP `503`; model/retrieval failures after chat streaming starts become explicit SSE errors rather than import-time resource initialization.
- `scripts/init_db.sql` owns the schema so a new environment is explicit and reproducible, including `retrieval_trace` migration for existing installations.
- The frontend uses `/api` as its base URL; Vite config injects the local backend target only in development.

## Trade-offs

- Hybrid retrievers are cached per collection and invalidated after indexing. A multi-process deployment should move this cache to a shared lexical-index service.
- `UnstructuredFileLoader` maximizes format support but may add platform-specific parser dependencies for advanced PDF formats.
- RRF and Cross-Encoder are compared at the child evidence unit; parent context expansion is deliberately excluded from retrieval metrics so the four rows remain comparable.
- The Cross-Encoder and Query Rewrite are optional because they add model memory and latency. RRF, original-query retrieval and single-source candidate fallback remain deterministic degradation paths.
- Numbering validation checks structure only. The optional claim judge checks answer/source consistency with the same configured model and can be wrong; neither validates the truth of the source itself.
- Structure-aware Markdown/text indexing is enabled by default. PDF uses PyMuPDF blocks, real geometry, tables and page previews; optional vision captions supplement indexing but are not native image-vector embeddings or literal OCR. DOCX/other loaders retain their fallback path. Reupload legacy materials to gain structural/page metadata. The fixed retrieval benchmark explicitly opts out of structure indexing.
- GraphCache derives a graph from explicit subject/relation/object tables and arrow statements in the actual collection snapshot. Every edge retains an exact source quote; co-occurrence is not a relation. Traversal is an evidence-discovery operation, not logical inference or a full community-summary GraphRAG implementation.
- Evidence budgets use a UTF-8-byte heuristic plus envelope allowance. Planning budgets use a character heuristic. Neither is a model tokenizer measurement or a guarantee about the complete chat prompt; generation and audit have separate time budgets.
- The research capability corpus is separate from ranking qrels. Offline capability runs use real BM25/structure/graph code but scripted planner/judge fixtures and never claim real-model performance.
- Data-bearing routers accept an opt-in `X-API-Key`; non-development startup refuses to run without `API_KEY`, preventing accidental unauthenticated shared deployments.
- Retrieved documents and history are explicitly delimited as untrusted prompt data. An extracted-character limit and streamed upload limit bound parser and parent-metadata amplification.
- Parent content is stored with child metadata for this single-node portfolio project, keeping expansion available after restart. A large production corpus should move parent chunks into a dedicated document store.
- The upload registry and latest evaluation report are local process/filesystem artifacts by design for this portfolio project; production multi-instance deployment needs durable job/report storage.
