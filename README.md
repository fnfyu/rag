# Evidence RAG：可追溯的知识库问答工作台

> 面向企业内部文档、项目资料与个人知识库的 RAG 应用。它将上传文件拆分并索引，通过 **向量召回 + BM25 关键词检索 + RRF 融合 + 可选 Cross-Encoder Rerank** 生成流式回答，并把每段回答关联到可展开的来源元数据。

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![Vue](https://img.shields.io/badge/Vue-3-42B883?logo=vuedotjs&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white) ![RAG](https://img.shields.io/badge/RAG-Hybrid%20Retrieval-2563EB)

## 项目亮点

- **两阶段混合检索**：向量与中文 BM25 各召回候选片段，经 Reciprocal Rank Fusion（RRF）去重融合；配置 `RERANKER_MODEL` 后再用 Cross-Encoder 重排，最终仅将高相关片段送入 LLM。
- **可追溯回答与可评测性**：提示词强制使用 `[S#]` 引用，并在前端展示文件名、页码/行号、片段 ID 与排序策略；提供 Recall@K、MRR、nDCG@K 评测脚本和引用完整性校验。
- **上下文感知检索**：多轮追问先经过 Query Rewrite；子 chunk 负责精确召回，命中后扩展到父 chunk，避免把过碎片段直接交给模型。
- **延迟初始化与可观测降级**：模型、向量库、记录管理器均按需初始化；`/health` 只检查配置，不会下载或加载本地模型，适合无模型开发环境。
- **可靠的文档索引链路**：上传端校验文件类型、文件名与大小，使用后台任务完成解析、切分与按会话/文件名增量更新，并提供 `queued → processing → completed/failed` 状态查询。
- **配置与数据边界清晰**：数据库、模型、Ollama、CORS、API key 与存储路径均来自环境变量；生产模式强制 API key，提供 SQL 初始化脚本，真实凭据不会写入仓库。
- **面向演示的 Vue 工作台**：包含知识库会话、资料统计、流式响应、引用来源抽屉、空状态与移动端布局，前端通过同源 `/api` 代理避免开发环境跨域耦合。

## 架构

```text
Vue 3 / Element Plus
        │  /api (Vite proxy)
        ▼
FastAPI ── 会话与文档元数据 ── PostgreSQL
   │
   ├── 上传任务 → 解析/切分 → 增量索引
   ├── Query Rewrite → Chroma 子 chunk Top 20 ─┐
   ├── BM25 子 chunk Top 20 ─┼→ RRF → Rerank → 父 chunk → Ollama → SSE
   └── 来源元数据 + 引用校验 ─┘                       │
                                               ▼
                                         带 [S#] 的可校验回答
```

更多职责边界见 [`docs/architecture.md`](docs/architecture.md)，领域术语见 [`CONTEXT.md`](CONTEXT.md)，完整录制与部署顺序见 [`docs/demo-script.md`](docs/demo-script.md)。

## 快速开始

### 1. 前置条件

- Python 3.11+、Node.js 20+、PostgreSQL 15+
- [Ollama](https://ollama.com/)（实际问答时需要，例如 `ollama pull qwen2.5:7b`）
- 一个本地 embedding 模型目录，或可下载的 Hugging Face 模型 ID

### 2. 配置数据库与环境变量

```powershell
# 创建数据库后执行表结构脚本
psql -U postgres -d evidence_rag -f scripts/init_db.sql

Copy-Item .env.example .env
```

编辑 `.env`，至少设置：

```dotenv
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/evidence_rag
EMBEDDING_MODEL=./models/bge-small-zh-v1.5
OLLAMA_MODEL=qwen2.5:7b
# 可选：启用 Cross-Encoder 二阶段重排
# RERANKER_MODEL=./models/bge-reranker-v2-m3
QUERY_REWRITE_ENABLED=true
PARENT_CHILD_ENABLED=true
# 本地开发可在 my-web/.env.local 设置 VITE_API_KEY；生产不要把长期 API_KEY 注入浏览器，改由同源 HttpOnly 会话或反向代理注入
```

> `EMBEDDING_MODEL` 可以是本地路径，也可以是模型标识（如 `BAAI/bge-small-zh-v1.5`）。模型仅在首次上传或提问时加载；没有模型时，服务仍可启动并通过 `/health` 告知缺失配置。

### 3. 运行后端

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python starter.py
```

API 文档：<http://127.0.0.1:8000/docs>

健康检查：<http://127.0.0.1:8000/health>

### 4. 运行前端

```powershell
cd my-web
npm install
npm run dev
```

访问 <http://127.0.0.1:5173>。开发服务器把 `/api` 代理到后端；如需修改目标，设置 `VITE_BACKEND_TARGET`。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 配置级健康状态，不加载模型 |
| `POST` | `/conversations` | 创建知识库会话 |
| `GET` | `/conversations` | 获取会话列表 |
| `GET` | `/conversations/{id}/messages` | 获取消息与来源 |
| `GET` | `/conversations/{id}/documents` | 获取已索引文档 |
| `POST` | `/uploads` | 上传并异步索引文档 |
| `GET` | `/uploads/{id}` | 获取索引任务阶段、事件与失败原因 |
| `GET` | `/uploads?conversation_id=...` | 恢复当前进程内任务列表 |
| `POST` | `/chat/{id}` | 返回 SSE 流式问答、检索轨迹与来源事件 |
| `GET` | `/evaluations/retrieval/dataset` | 获取标注集 fingerprint 与元数据 |
| `GET` | `/evaluations/retrieval/latest` | 获取最新真实评测报告或 `not_run` |

支持 `.txt`、`.md`、`.pdf`、`.docx`、`.csv`、`.json`、`.py`、`.log`，默认单文件上限为 20 MB；解析后的文本默认上限为 200 万字符（可通过 `MAX_UPLOAD_SIZE_MB`、`MAX_EXTRACTED_CHARS` 调整）。

## 简历表述参考

> **Evidence RAG｜FastAPI · LangChain · Chroma · PostgreSQL · Vue 3**
>
> 设计并实现上下文感知的两阶段知识库问答平台：对多轮追问进行 Query Rewrite，使用向量/BM25 候选召回、RRF 融合与 Cross-Encoder Reranker 重排，再通过 Parent-Child Retrieval 恢复完整上下文；通过 SSE 输出并校验 `[S#]` 引用，补充 Recall@K、MRR、nDCG@K 离线评测。

## 检索评测

仓库内置一套自建中文标注问题集和固定 benchmark corpus：[`evaluation/dataset.json`](evaluation/dataset.json) 包含 19 条问题、graded qrels、数据集版本和 corpus snapshot；[`evaluation/corpus/`](evaluation/corpus/) 是可审阅的 8 份能力资料。评测固定以 child evidence ID 为单位，避免 parent expansion 改变四种策略的比较口径。

在已配置 embedding 模型的环境中运行：

```powershell
# 生成固定 corpus 的索引快照与 source/chunk manifest
py -3 scripts/index_evaluation_corpus.py

# 同一问题集比较 Vector / BM25 / RRF / Cross-Encoder Rerank
py -3 scripts/evaluate_retrieval.py evaluation/dataset.json `
  --methods vector,bm25,rrf,rerank `
  --cutoffs 1,3,5,10 `
  --output evaluation/runs/latest.json
```

脚本只执行检索，不调用 Ollama。输出包含每种策略在每个 cutoff 的 Recall@K、MRR、graded nDCG@K、逐题命中片段、数据集 fingerprint、模型/切分配置与降级 trace。`RERANKER_MODEL` 未配置或加载失败时，报告会标出 `effective_method=rrf`，不会把 RRF 成绩冒充 Cross-Encoder 成绩。没有模型时页面和 API 会明确显示“暂无真实评测结果”，不展示虚构百分比。完整标注约定见 [`evaluation/README.md`](evaluation/README.md)。

## 验证说明

本仓库将模型资源延迟到索引/问答请求才加载。即使本地模型已删除，仍可执行 Python 编译检查、前端生产构建和 `/health` 配置检查；完整检索与生成验证需要按上述步骤配置模型、PostgreSQL 与 Ollama。

## License

MIT，详见 [LICENSE](LICENSE)。
