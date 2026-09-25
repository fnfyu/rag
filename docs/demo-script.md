# 完整 Demo 录制与部署脚本

## 90 秒录制顺序

1. 打开工作台：展示健康状态、知识库会话和“可评测 · 可追溯”定位。
2. 上传 `evaluation/corpus/retrieval.md` 或一份真实项目资料：依次展示 `queued → parsing → chunking → embedding → persisting → ready`，强调没有虚假的处理中百分比。
3. 提问“RRF 如何融合向量和 BM25？”：展示流式回答、`[S1]` 可点击引用、文件定位和 excerpt。
4. 展开“检索轨迹”：展示向量/BM25 候选、RRF、Cross-Encoder；若未配置 reranker，展示 `effective_method=rrf` 的诚实降级。
5. 点击一个不存在或未引用的来源编号（可用测试提示模拟）：展示 `missing/invalid` citation audit，并说明它只做结构校验。
6. 打开“评测”：展示 19 条自建标注问题、dataset fingerprint、Vector/BM25/RRF/Rerank 的 Recall@K、MRR、nDCG@K 和逐题命中。
7. 最后打开 API `/health` 或 `/docs`，展示配置级健康检查和检索-only 评测说明。

## 部署前检查

- 设置 `APP_ENVIRONMENT=production`、`API_KEY`、`DATABASE_URL`、`EMBEDDING_MODEL`、`OLLAMA_MODEL` 和 `CORS_ORIGINS`。
- 执行 `scripts/init_db.sql`，确认 PostgreSQL、Chroma 持久目录和 Ollama 可访问。
- 先执行 benchmark corpus 索引和评测命令，把 `evaluation/runs/latest.json` 生成在部署实例可读的位置。
- 前端生产构建后，将静态产物交给同源反向代理；把 `/api` 转发到 FastAPI，避免把 API key 写进公开 bundle。
- 录制前刷新 `/evaluations/retrieval/latest`，确认页面显示的是本次 corpus snapshot 的真实报告，而不是 demo 数字。

当前仓库没有云账号、域名或录屏凭据，因此不伪造“已部署/已录制”状态；这份脚本保证拿到环境后可以按同一条路径复现。
