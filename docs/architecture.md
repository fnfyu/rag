# Evidence RAG architecture

## Design goals

1. **Evidence first**: retrieval results are labeled before generation so the model can cite `[S#]`; the client receives the same labels, excerpts and source locations.
2. **Evaluable by default**: a versioned child-evidence qrels set compares vector, BM25, RRF and rerank using Recall@K, MRR and graded nDCG@K without calling an LLM.
3. **Degrades visibly**: query rewrite, candidate retrieval and reranking failures produce a retrieval trace with an effective strategy instead of silently claiming success.
4. **Usable without a model at boot**: process startup should not fail because a developer has not downloaded an embedding model or started Ollama.
5. **Configurable by environment**: no machine-specific paths, ports, database credentials, or model names are embedded in application code.
6. **Bounded responsibility**: HTTP routers coordinate requests, `RAGService` owns model/vector resources, `HybridRetriever` owns strategy policy, `evaluation.py` owns the metric contract, and `utils.py` is the small PostgreSQL repository layer.

## Domain contract

- A **knowledge base** owns an isolated collection and its uploaded materials.
- A **child evidence** is the stable judgment unit for offline retrieval evaluation. Its ID is currently `source_id:parent_index:child_index`; a changed chunking configuration requires a new corpus snapshot.
- A **retrieval strategy** is one of `vector`, `bm25`, `rrf`, or `rerank`. `rerank` means RRF candidate fusion followed by Cross-Encoder scoring; it is not an independent recall source.
- A **retrieval trace** records original/retrieval query, candidate count, stage status, effective strategy, fallback reason, duration and safe error codes.
- A **citation audit** checks source-marker structure only. It cannot prove semantic entailment.

The full terminology is recorded in [`CONTEXT.md`](../CONTEXT.md); the evaluation trade-off is recorded in [`docs/adr/0001-retrieval-evaluation-contract.md`](adr/0001-retrieval-evaluation-contract.md).

## Request flow

### Upload and indexing

1. `POST /uploads` validates basename, extension and streaming byte count.
2. The file is saved under `data/uploads/<upload-id>.<ext>` rather than its user-controlled filename.
3. A FastAPI background task records `queued → parsing → chunking → embedding → persisting → ready` (or `error`) and exposes the current task plus recent events.
4. The indexing record manager uses `conversation_id + normalized filename` as a stable `source` identity, and derives stable logical chunk IDs from that source, so re-uploading a file with the same name refreshes its indexed chunks instead of accumulating duplicates.
5. PostgreSQL records document metadata; the client polls the in-process lifecycle. A multi-instance deployment must replace the registry with a durable task queue and job table.

### Chat and citations

1. `POST /chat/{conversation_id}` resolves the conversation's isolated Chroma collection.
2. Contextual follow-up questions are optionally rewritten by Ollama into a standalone retrieval query. Rewrite timeout/failure keeps the original query and records the outcome in the trace.
3. `RAGService.retrieve_trace` asks `HybridRetriever.retrieve_with_trace` for the default `rerank` plan. Vector and BM25 candidates are independently retrieved, fused with Reciprocal Rank Fusion, and optionally reranked. If one candidate source fails, the other remains usable; if reranking is absent or fails, `effective_method=rrf` is explicit.
4. The retriever expands selected child hits to unique parent chunks only for generation; every source retains `child_chunk_id`, `parent_id`, rank fields and safe excerpt metadata. Offline evaluation disables expansion and evaluates child IDs directly.
5. Retrieved parent chunks are formatted as `[S1]`, `[S2]`, etc. alongside a compact recent-turn history. After generation, `citations.py` checks every marker against the source list and emits `valid`, `missing`, `invalid`, `no_sources`, or `generation_failed`.
6. The stream sends `retrieval-trace`, `data-sources`, text deltas and `citation-validation` events. The client renders clickable citations, source details, stage outcomes and degradation reasons without receiving server file paths.
7. User and completed assistant turns, including source list, citation audit and retrieval trace, are persisted in PostgreSQL.

## Retrieval evaluation flow

1. `evaluation/dataset.json` contains 19 self-built Chinese questions, a corpus snapshot, exhaustive qrels and graded relevance labels.
2. `scripts/index_evaluation_corpus.py` indexes the checked-in corpus with deterministic `eval:<filename>:0:0` child IDs and writes a file-hash manifest.
3. `scripts/evaluate_retrieval.py` runs all requested strategies on the same cases and cutoffs. The metric module deduplicates hits, uses `grade >= 1` for Recall/MRR and `2^grade-1` gain for nDCG.
4. The JSON report contains dataset fingerprint, run configuration, per-strategy summaries, per-query ranked IDs and safe retrieval traces. `rerank` fallback is never presented as a real Cross-Encoder result.
5. `GET /evaluations/retrieval/dataset` exposes dataset provenance; `GET /evaluations/retrieval/latest` exposes the latest real report or an explicit `not_run` state. The Vue evaluation view refuses to invent percentages.

## Operational behavior

- `/health` reports configuration readiness, retrieval strategy and whether expensive resources were initialized. It never creates embeddings, loads the reranker or calls Ollama.
- `DATABASE_URL` and `EMBEDDING_MODEL` are required only when an endpoint actually needs them. Missing configuration produces a clear `503`, not an import-time failure.
- `scripts/init_db.sql` owns the schema so a new environment is explicit and reproducible, including `retrieval_trace` migration for existing installations.
- The frontend uses `/api` as its base URL; Vite config injects the local backend target only in development.

## Trade-offs

- Hybrid retrievers are cached per collection and invalidated after indexing. A multi-process deployment should move this cache to a shared lexical-index service.
- `UnstructuredFileLoader` maximizes format support but may add platform-specific parser dependencies for advanced PDF formats.
- RRF and Cross-Encoder are compared at the child evidence unit; parent context expansion is deliberately excluded from retrieval metrics so the four rows remain comparable.
- The Cross-Encoder and Query Rewrite are optional because they add model memory and latency. RRF, original-query retrieval and single-source candidate fallback remain deterministic degradation paths.
- Citation validation checks structural source integrity, not semantic entailment; answer faithfulness still requires a labeled answer set or a judge model.
- Data-bearing routers accept an opt-in `X-API-Key`; non-development startup refuses to run without `API_KEY`, preventing accidental unauthenticated shared deployments.
- Retrieved documents and history are explicitly delimited as untrusted prompt data. An extracted-character limit and streamed upload limit bound parser and parent-metadata amplification.
- Parent content is stored with child metadata for this single-node portfolio project, keeping expansion available after restart. A large production corpus should move parent chunks into a dedicated document store.
- The upload registry and latest evaluation report are local process/filesystem artifacts by design for this portfolio project; production multi-instance deployment needs durable job/report storage.
