# Evidence RAG: Source-aware knowledge-base chat

Evidence RAG is a portfolio-ready Retrieval-Augmented Generation application for internal documents and personal knowledge bases. It combines semantic vector search and BM25 keyword retrieval with RRF fusion and an optional Cross-Encoder reranker, streams responses over SSE, and exposes supporting document metadata for every answer.

## Highlights

- Two-stage retrieval: independent vector/BM25 candidate recall, Reciprocal Rank Fusion, and optional Cross-Encoder reranking.
- A checked-in, self-built 19-query Chinese qrels set and corpus snapshot for credible comparison.
- Offline comparison of vector, BM25, RRF and Cross-Encoder rerank using Recall@K, MRR and graded nDCG@K.
- Contextual query rewriting, parent-child context expansion, and structural citation validation.
- Citation-aware prompt contract using `[S#]` source identifiers plus safe excerpts.
- Safe, observable background indexing with stage transitions and event history.
- Explicit retrieval traces: effective strategy, partial failures and reranker degradation are never hidden.
- Lazy model initialization and a configuration-only `/health` endpoint.
- Environment-based database, model, storage, Ollama and CORS configuration.
- Vue 3 / Element Plus knowledge-workspace UI with responsive layouts and source details.

## Run locally

1. Create a PostgreSQL database and run `scripts/init_db.sql`.
2. Copy `.env.example` to `.env`, then set `DATABASE_URL` and `EMBEDDING_MODEL`.
3. Install API dependencies: `pip install -r requirements.txt`.
4. Start the API: `python starter.py`.
5. Install and start the UI from `my-web`: `npm install` then `npm run dev`.

Ollama is required only for answering questions. Models are loaded lazily, so the API can start and `/health` can be inspected without local embedding or reranker models. Configure `RERANKER_MODEL` to enable the second-stage Cross-Encoder; otherwise RRF order is used.

For the checked-in benchmark, run `py -3 scripts/index_evaluation_corpus.py`, then `py -3 scripts/evaluate_retrieval.py evaluation/dataset.json --methods vector,bm25,rrf,rerank --cutoffs 1,3,5,10 --output evaluation/runs/latest.json`. The report is retrieval-only and records the dataset fingerprint, per-query hits, metrics and fallback traces. The UI shows an explicit `not_run` state instead of invented percentages when no report exists.

For the Chinese setup guide, architecture overview, API list and demo/deployment runbook, see [README.md](README.md), [docs/architecture.md](docs/architecture.md) and [docs/demo-script.md](docs/demo-script.md).
