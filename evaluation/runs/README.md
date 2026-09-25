# 评测运行产物

将 `scripts/evaluate_retrieval.py` 的 `--output` 指向本目录即可生成 `latest.json`。报告包含数据集 fingerprint、四种检索策略、每个 cutoff 的 Recall/MRR/nDCG、逐题命中片段和降级 trace。

仓库不提交没有在当前索引快照上实际运行的百分比；前端在报告不存在时明确显示“暂无真实评测结果”。
