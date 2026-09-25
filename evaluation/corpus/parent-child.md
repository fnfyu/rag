# 父子片段

子片段用于精确召回，父片段用于提供生成上下文。检索轨迹和离线 benchmark 固定以 child evidence ID 计算 Recall、MRR、nDCG；聊天生成可以在 rerank 后把命中的 child 扩展为唯一 parent，并在来源中保留 child_chunk_id、parent_id 和 expanded_from_child，保证回答仍可回溯到命中位置。
