# 实施任务

## 1. 运行配置与数据层
- **Files:** `config.py`, `utils.py`, `.env.example`, `scripts/init_db.sql`, `.gitignore`
- **Verify:** `py -3 -m compileall -q config.py utils.py`
- **Done when:** 服务不含真实凭据；数据库、模型与存储路径均可从环境变量配置。

## 2. RAG 服务与 API 契约
- **Files:** `backend.py`, `conversation.py`, `upload.py`, `search.py`, `starter.py`
- **Verify:** `py -3 -m compileall -q backend.py conversation.py upload.py search.py starter.py`
- **Done when:** 模型延迟加载；空知识库可预期响应；上传、会话、来源与健康检查接口有一致的结构。

## 3. 两阶段检索与评测
- **Files:** `retrieval.py`, `backend.py`, `evaluation.py`, `evaluation/`, `scripts/evaluate_retrieval.py`, `scripts/index_evaluation_corpus.py`, `scripts/evaluation.example.json`
- **Verify:** `py -3 -m compileall -q retrieval.py evaluation.py scripts/evaluate_retrieval.py scripts/index_evaluation_corpus.py` and `py -3 -m unittest discover -s tests`
- **Done when:** 向量/BM25 候选经 RRF 融合，可选 Cross-Encoder 重排；同一自建 child-qrels 集能输出四路 Recall@K、MRR、graded nDCG@K、fingerprint、逐题结果和降级 trace。

## 4. 上下文理解、引用校验与索引链路
- **Files:** `backend.py`, `retrieval.py`, `citations.py`, `security.py`, `search.py`, `upload.py`, `utils.py`, `conversation.py`, `scripts/init_db.sql`, `my-web/src/App.vue`, `my-web/src/style.css`, `.env.example`
- **Verify:** `py -3 -m compileall -q backend.py retrieval.py citations.py search.py upload.py` and `npm run build`（在 `my-web`）
- **Done when:** 多轮问题可选改写，子 chunk 命中后恢复父 chunk，回答完成后发送引用完整性和检索轨迹；上传展示真实阶段、事件和失败降级。

## 5. 评测 API 与演示工作台
- **Files:** `evaluation_api.py`, `starter.py`, `my-web/src/App.vue`, `my-web/src/style.css`, `my-web/index.html`, `my-web/vite.config.js`
- **Verify:** `py -3 -m compileall -q evaluation_api.py starter.py` and `npm run build`（在 `my-web`）
- **Done when:** 页面适配桌面和移动端，展示健康状态、资料状态、流式回答、检索轨迹、可展开引用来源和真实/未运行评测状态。

## 6. 交付材料
- **Files:** `README.md`, `README.en.md`, `docs/architecture.md`
- **Verify:** `git diff --check`
- **Done when:** 新环境能按文档初始化，且有可直接复用的简历项目亮点。
