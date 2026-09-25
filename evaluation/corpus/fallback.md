# 检索降级

检索轨迹会区分成功、空知识库、部分降级和失败。向量候选失败但 BM25 可用时，系统保留可用候选并标记 partial_candidate_failure；reranker 未配置、加载失败或超时会明确 effective_method=rrf，而不会把 RRF 结果伪装成 rerank。两路都不可用时回答只说明检索暂时不可用，不补充外部事实。
