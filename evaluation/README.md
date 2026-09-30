# Evidence RAG 标注问题集

这里是项目自建的、可版本化的中文核心能力 benchmark，而不是从公开数据集复制的样例。

- `dataset.json`：19 条带 qrels 的问题，覆盖 exact keyword、语义改写、混合检索、引用、降级、索引链路、父子片段和安全边界。
- `corpus/`：8 份与项目能力对应的短资料，每份在默认切分配置下产生一个 child evidence。
- `corpus-manifest.json`：运行索引脚本后生成，记录 corpus 文件 hash 和预期 evidence ID。
- `runs/latest.json`：运行评测 CLI 后生成，默认不提交虚构结果。

## 标注约定

- 判定单元是 child evidence ID（`source_id:parent_index:child_index`），parent 扩展不参与指标。
- `relevance` 数组只列出**已判定为相关**的片段，等级 1–3；未列出的 child evidence 视为等级 0（不相关），因此 `qrels_exhaustive: true` 表示当前 8 个 child evidence 都已过判断，而不是"只标注了正例"。
- 改变切分配置会改变 evidence ID，必须重新生成 `corpus-manifest.json` 并提升数据集版本。
- 报告汇总里 `summary.<strategy>.effective_method` / `degraded_cases` / `failed_cases` 与 `run.effective_strategies` 记录每个策略**实际**用了哪条排序路径：`rerank` 未配置或加载失败时该值是 `rrf`，不会把 RRF 成绩呈现为 Cross-Encoder 成绩。

## 可复现运行

```powershell
# 先配置 EMBEDDING_MODEL、CHROMA_PATH 等环境变量
py -3 scripts/index_evaluation_corpus.py
py -3 scripts/evaluate_retrieval.py evaluation/dataset.json `
  --methods vector,bm25,rrf,rerank `
  --cutoffs 1,3,5,10 `
  --output evaluation/runs/latest.json
```

评测只调用检索，不调用 Ollama。`rerank` 未配置或加载失败时，报告中的每题 trace 会把 `effective_method` 标为 `rrf`，因此不能把降级结果当成 Cross-Encoder 的真实成绩。
