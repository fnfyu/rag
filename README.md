# Evidence RAG：证据驱动的复杂文档研究工作台

> **V3 魂系攻略与版本情报工作台**：艾尔登法环、黑夜君临、黑魂1／2／3 独立游戏条件 → 官方公告与攻略资料 → Boss / 构筑 / 路线专用报告 → 补丁影响与攻略冲突复核。保留 V2 知识库、分章报告、局部修订、版本历史与图文表格研究，以及 V1 多跳、关系证据和混合检索底座。

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![Vue](https://img.shields.io/badge/Vue-3-42B883?logo=vuedotjs&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white) ![RAG](https://img.shields.io/badge/RAG-Hybrid%20Retrieval-2563EB)

## 项目亮点

- **五款魂系游戏专精**：游戏、发行版、补丁、DLC、平台与玩法条件显式隔离；黑夜君临使用角色、遗物和远征语境，不借用法环自由加点或未经建立的负重模型。
- **可追溯版本情报**：官方来源预览与明确文章导入，保留原始链接、公告日期、抓取日期与内容哈希；排除Steam媒体转载和明确跨游戏推广，不假装已经覆盖全部最新补丁。
- **攻略依赖与数值工具**：五类五章专用提纲、补丁到旧章节/结论的复核候选，明确输入的属性预算、负重及数值对照；阈值与真实伤害公式缺证据时不编造。
- **知识库与研究任务分离**：一个资料集合支持多个会话和可续接研究任务，提纲、分章成果、证据、问题与报告历史持久保存。
- **研究交付与局部修订**：用户编辑确认提纲后逐章研究，形成引用报告；核验发现的矛盾或证据缺口可以定向补查，只修改选定章节，并比较、恢复和导出报告版本。
- **资料演进与适用条件**：同名上传保留为独立版本，比较可定位的原文差异与冲突，关联可能需要重新核验的旧报告章节和结论，不把上传顺序当作有效性优先级。
- **图文与数值研究**：PDF 实际页面预览、文字/表格区域坐标和页区引用；可选视觉模型进行图像问答及索引描述；表格使用 Decimal 运算并返回公式、单位和使用的来源行。
- **两阶段混合检索**：向量与中文 BM25 各召回候选片段，经 Reciprocal Rank Fusion（RRF）去重融合；配置 `RERANKER_MODEL` 后再用 Cross-Encoder 重排，最终仅将高相关片段送入 LLM。
- **可追溯回答与可评测性**：提示词强制使用 `[S#]` 引用，并在前端展示文件名、页码/行号、片段 ID 与排序策略；提供 Recall@K、MRR、nDCG@K 评测脚本和引用完整性校验。
- **结构感知与预算化上下文**：Markdown 标题、段落、代码和表格保持结构；检索前缀与原文分开，长表恢复列头，多命中窗口合并并按来源轮转。在可配置的估算 token 预算内选取证据，不把离散窗口标成连续原文。
- **自适应多跳研究**：自动 / 快速 / 深度研究三种入口；复杂问题拆解为有依赖的子问题，每轮判断实际选入上下文的证据缺口，补检并按充分性、新增证据、轮次、时间或规划成本停止。
- **证据关系增强**：从明确的主体—关系—客体表格和箭头陈述构图，遍历最多两跳并跟进新实体；每条关系保留实际原文与 child ID，不从共同出现推断关系，不冒充完整 GraphRAG。
- **逐结论语义核验**：抽取事实性结论，按本句引用检查支持 / 矛盾 / 证据不足，核验原文 quote 是否真实连续存在。使用配置的 Ollama 模型辅助判断，不证明真实性，也不自动改写回答。
- **延迟初始化与可观测降级**：模型、向量库、记录管理器均按需初始化；`/health` 只检查配置，不会下载或加载本地模型，适合无模型开发环境。
- **版本化文档索引链路**：后台完成解析、切分与按资料版本独立索引，旧版本仍可引用；相同内容及版本描述可复用已有版本，并提供 `queued → processing → completed/failed` 状态查询。
- **配置与数据边界清晰**：数据库、模型、Ollama、CORS、API key 与存储路径均来自环境变量；生产模式强制 API key，提供 SQL 初始化脚本，真实凭据不会写入仓库。
- **面向演示的 Vue 工作台**：包含知识库会话、资料统计、流式响应、引用来源抽屉、空状态与移动端布局，前端通过同源 `/api` 代理避免开发环境跨域耦合。

## 架构

```text
Vue 3 / Element Plus
        │  /api (Vite proxy)
        ▼
FastAPI ── 会话与文档元数据 ── PostgreSQL
   │
   ├── 上传 → 结构解析 → 原文 + 检索上下文前缀 → 增量索引
   ├── Query Rewrite → 自动路由 / 快速 / 深度研究
   │                        │
   │      子问题 → 向量 + BM25 → RRF → Rerank ─┐
   │                明确关系图 → 关系证据 ─────┤
   │                        ▲                 ▼
   │                        └── 证据缺口 ← 预算化原文窗口
   │                                          │
   └── SSE 研究轨迹 ← 带 [S#] 回答 ← Ollama ───┘
                           │
                     逐结论核验 + 原文 quote
                           │
                     PostgreSQL 历史回放
```

更多职责边界见 [`docs/architecture.md`](docs/architecture.md)，领域术语见 [`CONTEXT.md`](CONTEXT.md)，完整录制与部署顺序见 [`docs/demo-script.md`](docs/demo-script.md)。

## 使用第三版游戏工作台

1. 进入「游戏攻略」，选择五款中的一款并创建独立游戏知识库，确认发行版、实际补丁、平台、玩法、DLC、进度与剧透范围。
2. 预览官方渠道，明确选择一篇文章导入；上传社区攻略、装备表或截图时注明适用条件与来源。
3. 选择 Boss、构筑、路线、补丁影响或攻略冲突模板，填写具体目标，确认五章提纲后进入研究交付。
4. 查看补丁关联的旧章节与结论，定向补查、局部修订并比较/导出历史报告。

首批资料含五游戏官方产品介绍与黑夜君临1.03.1实际补丁捕获；是研究样板，不是最新性保证或完整攻略库。配置数据库与模型后运行 `python scripts/bootstrap_souls.py --apply` 可导入专属样板库；不加 `--apply` 只预览。

从 V2 升级先重新执行 [数据库脚本](<scripts/init_db.sql>) 并更新依赖；旧库/索引不删除、旧资料不自动变成游戏资料。完整使用与接口见 [第三版说明](<docs/souls-workbench-v3.md>)，原始依据见 [官方来源研究](<docs/souls-official-sources.md>)。

## 通用研究交付工作台（V2能力保留）

1. 创建知识库并上传资料，可标明版本标签、发布日期和适用条件。同一知识库内的多个会话共享资料。
2. 打开“研究交付”，创建目标；生成或手工编写提纲，编辑确认各章节、选用的资料版本与研究条件。
3. 开始研究：按章保存证据、正文、核验与缺口。离开页面不丢成果；服务重启后可点击“继续研究”续接已有章节。
4. 对问题结论选择“补查修订”，或直接编辑章节；查看前后差异、恢复旧快照，导出 Markdown / HTML / JSON 引用报告。
5. 在“资料版本”比较同系列两个版本，回查受影响报告；通过页面区域查看实际文字、图表与来源行，运行图像问答或确定性表格计算。

**从 V1 升级**：重新执行 [数据库脚本](<scripts/init_db.sql>)，旧集合和来源标识保持不变；再安装更新的依赖。视觉研究需要实际支持图像输入的 `VISION_MODEL`，自动图文索引另设 `VISION_INDEXING_ENABLED=true`，仅配置文本模型不会获得视觉能力。

完整通用工作流和接口见 [第二版说明](<docs/research-workbench-v2.md>)。三版主线为 V1 证据研究、V2 研究交付、V3 魂系游戏攻略与版本情报专精。

## 使用第一版研究底座

聊天输入区选择 **自动 / 快速问答 / 深度研究**，可分别关闭关系增强与逐结论核验。

- 自动入口使用可解释的比较 / 依赖等关键词路由，并非训练出的分类器；简单问题仅单轮检索。
- 深度研究最多默认 3 轮，展示子问题依赖、逐轮查询、实际选入上下文的证据缺口和停止原因；没有新增证据时不会无限循环。
- 关系图目前只抽取明确的三列表格与 `Orion --依赖--> RelayMesh` 这类箭头陈述，不自动从任意自然语言创造关系。普通文本仍可通过混合检索召回。
- 语义核验最多抽取 12 个结论，使用同一配置模型的独立两阶段调用，不等于独立模型复核；结论截断、模型不可用会明确展示。
- 已上传的旧资料可以继续问答；要获得新章节、表格和准确窗口定位，请重新上传。原有检索 benchmark 固定使用旧切分口径，不混入新研究案例。

[研究升级说明](docs/research-upgrade.md)包含接口、配置、演示顺序和实现边界。[能力案例](evaluation/research/cases.json)覆盖跨资料比较、多跳依赖、版本冲突与资料不足。

```powershell
# 不需要 PostgreSQL/Ollama，使用真实 BM25/结构/关系代码 + 明确标注的脚本化模型决策。
.\.venv\Scripts\python.exe scripts/run_research_cases.py --mode offline

# 配好 EMBEDDING_MODEL、OLLAMA_MODEL 并启动 Ollama 后，运行真实链路。
# CLI 使用独立研究集合，不需要创建 PostgreSQL 会话。
.\.venv\Scripts\python.exe scripts/run_research_cases.py --mode live --case dependency-multihop
```

离线报告不是模型质量成绩；默认写入 `data/research-capabilities.json`，真实模型模式才生成实际回答和真实 judge 输出。

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
EMBEDDING_MODEL=./bge-small-zh-v1.5
OLLAMA_MODEL=qwen2.5:7b
# 可选：启用 Cross-Encoder 二阶段重排
# RERANKER_MODEL=./bge-reranker-v2-m3
CHROMA_PATH=data/chroma
UPLOAD_DIR=data/uploads
QUERY_REWRITE_ENABLED=true
PARENT_CHILD_ENABLED=true
# 本地开发可在 my-web/.env.local 设置 VITE_API_KEY；生产不要把长期 API_KEY 注入浏览器，改由同源 HttpOnly 会话或反向代理注入
```

> `EMBEDDING_MODEL` 可以是本地路径，也可以是模型标识（如 `BAAI/bge-small-zh-v1.5`）。本地权重目录放在仓库根目录（已被 `.gitignore` 排除），例如 `./bge-small-zh-v1.5`。模型仅在首次上传或提问时加载；没有模型时，服务仍可启动并通过 `/health` 告知缺失配置。

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
| `GET / POST` | `/knowledge-bases` | 列出 / 创建独立知识库 |
| `GET / POST` | `/knowledge-bases/{id}/tasks` | 列出 / 创建可续接研究任务 |
| `POST` | `/research-tasks/{id}/outline` | 生成用户可编辑的报告提纲 |
| `POST` | `/research-tasks/{id}/run` | 分章研究、保存进度、续接成果 |
| `POST` | `/research-tasks/{id}/revise` | 对选定章节和问题结论定向补查修订 |
| `GET` | `/research-tasks/{id}/versions` | 报告不可变版本与差异历史 |
| `GET` | `/research-tasks/{id}/export` | 导出 Markdown / HTML / JSON |
| `GET` | `/documents/series/{id}/compare` | 原文版本差异、适用性与影响范围 |
| `GET` | `/documents/versions/{id}/pages` | 页面预览、真实区域与表格 |
| `POST` | `/documents/versions/{id}/pages/{page}/analyze` | 实际页面 / 区域视觉问答 |
| `POST` | `/documents/versions/{id}/tables/calculate` | 确定性运算与来源行 |
| `POST` | `/conversations` | 在知识库内创建会话（兼容旧客户端） |
| `GET` | `/conversations` | 获取会话列表 |
| `GET` | `/conversations/{id}/messages` | 获取消息与来源 |
| `GET` | `/conversations/{id}/documents` | 获取已索引文档 |
| `POST` | `/uploads` | 上传并异步索引文档 |
| `GET` | `/uploads/{id}` | 获取索引任务阶段、事件与失败原因 |
| `GET` | `/uploads?conversation_id=...` | 恢复当前进程内任务列表 |
| `POST` | `/chat/{id}` | 返回 SSE 流式问答、检索轨迹与来源事件 |
| `GET` | `/evaluations/retrieval/dataset` | 获取标注集 fingerprint 与元数据 |
| `GET` | `/evaluations/retrieval/latest` | 获取最新真实评测报告或 `not_run` |

支持 `.txt`、`.md`、`.pdf`、`.docx`、`.csv`、`.json`、`.py`、`.log` 和 `.png`、`.jpg`、`.jpeg`、`.webp`（图片索引需要视觉模型和视觉索引开关），默认单文件上限为 20 MB；解析后的文本默认上限为 200 万字符（可通过 `MAX_UPLOAD_SIZE_MB`、`MAX_EXTRACTED_CHARS` 调整）。

## 简历表述参考

> **Evidence RAG｜FastAPI · LangChain · Chroma · PostgreSQL · Vue 3**
>
> 设计并实现证据驱动的复杂文档研究平台：以结构感知索引和预算化原文窗口支撑混合检索，将复杂问题拆解为有依赖的子问题，依据证据缺口进行多轮补检；通过可溯源实体关系扩展召回，并以逐结论语义审计对齐回答与引用原文。SSE 展示计划、轮次、停止原因与成本，保留独立 child 口径的 Recall@K、MRR、nDCG@K 检索评测。

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
