## ADDED

### Requirement: Two-stage retrieval
- **WHEN** a knowledge-base question is received and the collection contains documents
- **THEN** vector and BM25 candidates are independently retrieved, fused with Reciprocal Rank Fusion, and reduced to the final context size
- **AND** when `RERANKER_MODEL` is configured, a Cross-Encoder reranks the fused candidates before generation
- **AND** when the reranker is absent or cannot load, the system falls back to RRF order without making the API unavailable

### Requirement: Contextual retrieval
- **WHEN** a question contains prior conversation context
- **THEN** the system may rewrite it into a standalone retrieval query, while preserving the original question for answer generation
- **AND** rewrite failure falls back to the original question
- **WHEN** child chunks are retrieved
- **THEN** the system expands them to unique parent context before generation

### Requirement: Citation validation
- **WHEN** generation completes
- **THEN** the system checks every `[S#]` marker against the source list sent to the model
- **AND** emits `valid`, `missing`, or `invalid` citation status without exposing server paths
- **AND** emits a distinct `generation_failed` status when the model cannot complete, without persisting the failure as a normal answer

### Requirement: Retrieval evaluation
- **WHEN** an evaluation JSON dataset is passed to `scripts/evaluate_retrieval.py`
- **THEN** the script compares `vector`, `bm25`, `rrf`, and `rerank` on the same child-evidence judgment unit
- **AND** it reports Recall@K, MRR, graded nDCG@K and per-query retrieved chunk IDs without calling the LLM
- **AND** it records dataset fingerprint, corpus snapshot, cutoff, model configuration and effective strategy
- **AND** if reranking is unavailable, the run reports an explicit RRF fallback rather than labeling the output rerank

### Requirement: Retrieval trace
- **WHEN** a chat request performs rewrite, candidate recall, fusion or reranking
- **THEN** the SSE stream emits stage status, candidate/result counts, effective strategy and safe fallback codes
- **AND** the client can distinguish an empty knowledge base, a partial degradation and a retrieval failure

### Requirement: Indexing lifecycle
- **WHEN** a document is uploaded
- **THEN** the task exposes queued, parsing, chunking, embedding, persisting and ready/error stages with timestamps
- **AND** the client never presents an invented processing percentage when the backend has no measured progress
