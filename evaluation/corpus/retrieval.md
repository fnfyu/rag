# 检索策略

Evidence RAG 对同一问题保留四种可比较的检索策略。vector 使用 embedding 计算语义相似候选；bm25 使用中文分词后的关键词相关性；rrf 将两路候选按 Reciprocal Rank Fusion 融合并按片段 ID 稳定打破并列；rerank 在 RRF 候选上运行 Cross-Encoder。评测时四种策略都使用相同的 child 片段和 cutoff，避免把 parent expansion 的影响混入召回指标。
