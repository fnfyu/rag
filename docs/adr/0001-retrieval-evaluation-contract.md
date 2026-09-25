# 0001：以 child evidence ID 和版本化 qrels 作为检索评测契约

- 状态：已采用
- 日期：2026-02-01

## 背景

单看最终聊天上下文无法区分“候选没召回”与“重排丢失”，而 parent expansion 还会改变结果粒度。旧示例只使用 `relevant_chunk_ids`，没有记录数据集版本、相关性等级或索引快照，无法可靠比较 vector、BM25、RRF 和 rerank。

## 决策

离线评测固定以 child 片段为 judgment unit，使用稳定的 `source_id:parent_index:child_index` evidence ID；问题集使用 schema v1 的 `relevance` qrels（0–3 等级），同时兼容旧的二值 `relevant_chunk_ids`。每次评测运行记录数据集 fingerprint、corpus snapshot、切点、候选数、RRF 参数、embedding/reranker 配置和每个策略的降级轨迹。聊天生成可以扩展为 parent，但不把 parent 结果混入离线排序指标。

## 结果

- 四种策略可在相同问题、相同 cutoff 和相同 evidence 粒度下比较。
- nDCG 使用 graded gain，Recall/MRR 使用 `grade >= 1`。
- reranker 未配置或失败时，报告的 effective method 明确为 RRF，而不是伪装成 rerank。
- 片段切分参数变化会产生新的 corpus snapshot；标注集需要随快照更新，而不是静默复用旧 ID。

## 未解决

当前 benchmark corpus 的任务状态和最新报告仍是本地文件；多实例部署需要把评测运行与上传任务迁移到持久化 job table 或队列。
