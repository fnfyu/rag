# V2：从证据问答到研究交付

本版围绕完整交付链路组织：**独立知识库 → 多研究任务 → 用户确认提纲 → 分章查证 → 局部修订 → 版本适用性 → 图文及数值证据**。V1 的问答、多跳检索、关系证据和核验继续保留；V3 领域专精不包含在本轮。

## 先升级，再开始研究

1. 创建 / 配置 PostgreSQL，执行 [数据库脚本](<../scripts/init_db.sql>)。已有 V1 安装也重新执行同一脚本；迁移把旧会话对应的资料集合转为知识库，保留集合名、旧来源 ID 和原有消息，不重建向量索引。
2. 安装 [后端依赖](<../requirements.txt>)，PDF 使用 PyMuPDF 实际解析文字区域、页面图和表格。
3. 配置 [环境模板](<../.env.example>) 中的数据库、embedding 和文本 Ollama 模型，启动后端与前端。服务入口和启动步骤见 [README](<../README.md>)。
4. 如需视觉研究，配置并启动**实际支持图像输入**的 Ollama 模型；页面预览 / 文本 / 表格解析不依赖视觉模型。

```dotenv
# 视觉问答；模型名称按实际安装选择
VISION_MODEL=qwen2.5vl:7b
# 将 PDF/图片的机器描述也加入检索索引
VISION_INDEXING_ENABLED=true
VISION_MAX_PAGES=8
VISION_TIMEOUT_SECONDS=60
PDF_PAGE_RENDER_ENABLED=true
ASSET_DIR=data/assets
REPORT_MAX_SECTIONS=8
REPORT_WORKER_TIMEOUT_SECONDS=1200
```

PNG/JPG/JPEG/WEBP 索引需要视觉模型及索引开关。PDF 默认保留原文文字、实际布局和页面预览；扫描页没有可提取文字时不会生成假原文，可配置视觉描述补充检索。默认视觉索引只处理前 8 页，按资料规模调整。若本机环境里的 IPv6 `NO_PROXY` 条目导致 `httpx.InvalidURL`，可在启动服务的当前终端临时设 `$env:NO_PROXY='localhost,127.0.0.1'`，不必修改系统代理配置。

## 1. 一个知识库，多份独立研究成果

知识库拥有隔离资料集合，问答会话只保存交互记录。新建第二个会话无需再次上传；同一知识库的多个研究任务共享资料，但各自有目标、提纲、研究条件、证据和报告历史。

“研究交付”页创建任务时填写研究目标，也可以选择实际资料版本、填写部署 / 时间 / 版本等适用条件。不选择版本表示研究该知识库全部版本，并非自动只用最近上传的资料。选择版本后，**向量、BM25 和关系图召回都在检索前受相同来源范围约束**。

任务持久保存，刷新页面会恢复其状态。研究在当前服务进程后台执行，每章保存 checkpoint；离开页面不会撤销后台任务。服务重启后点击“继续研究”，同一提纲和范围内已完成章节会被保留，未完成章节继续处理。它不是分布式调度器或保证跨进程自动执行的队列。

## 2. 确认提纲后按章研究

可以让文本模型生成提纲，再修改章节标题、问题、顺序和启用状态；也可以完全手工编写。确认保存后再开始研究，也可以只选择部分章节。

每章独立执行：

1. 拆解需要查证的问题，执行 V1 的多轮混合检索与关系扩展。
2. 根据实际进入上下文的证据判断覆盖范围，记录不足和停止原因。
3. 编写该章正文，引用报告范围内稳定的 `[S#]`，不在每章重新从 `[S1]` 编号。
4. 核验结论、连续 quote 与来源编号；保存正文、来源、轨迹、缺口和核验。
5. 交付不可变报告快照，导出 Markdown / HTML / JSON。

来源保留版本标签、发布日期、适用条件、页码/行号、原文窗口和页区信息。没有依据的章节呈现缺口，不以“研究完成”掩盖资料不足。

导出文件包括章节与引用来源。HTML 是自包含、可打开和打印的报告；正文按纯文本安全输出并提供引用跳转。JSON 保留结构化证据和核验，方便后续领域系统使用。

## 3. 核验驱动定向补查，不推倒重写

针对一个章节选择矛盾 / 证据不足的结论，或输入修订要求后点击“补查修订”。系统使用原问题、问题结论及理由检索新证据。存在选定 / 问题结论时按其原文位置只替换对应段落，其他段落由程序逐字保留；没有具体问题结论的章节级要求则生成该章节的修订版。其他章节正文和已有引用编号保持不变。

也可以直接人工编辑章节，系统保存新快照及核验。历史页面支持原文预览、章节级差异和恢复；“恢复”创建新报告版本，不覆盖之前的历史。

改变提纲问题、研究目标或选用版本后，旧章节不再被当作同范围的已完成成果。只修一章时，其他章仍被保留，但如果范围已变化会提示需确认；继续整个任务可补齐其余章节。

## 4. 同名资料演进与冲突定位

同一知识库内同名资料形成资料系列，每次不同内容或不同版本描述保留为独立版本。相同内容及相同版本标签 / 日期 / 条件可复用已有记录，避免无意义重复。

“资料版本”页明确选择左、右版本：

- 展示原文增删改与行位置；差异来自实际内容，不依赖生成模型。
- 文本模型辅助说明冲突、变更和条件，每个展示的版本 quote 必须真实存在于对应原文。
- 关联引用这些版本的报告章节和具体结论，供用户定向重新核验。
- 发布日期或部署条件未知时明确需要确认；上传时间不能决定哪一版本正确，也不会自动宣告旧结论失效。

可用 V1 的虚构 Orion 资料演示 16GB / 24GB 冲突。作为“资料系列”演示时应以同一显示文件名上传两个版本，并分别标明版本标签；不同文件名是不同系列，不会被擅自认定为同一资料。

## 5. 页面区域、图像问答与可复算表格

### 实际页区

PDF 文字块和表格附带页码与 `bbox=[x0,y0,x1,y1]`。页面预览去除旋转，坐标使用 MuPDF 未旋转页面点；前端框选 / 键盘选择区域并读取对应内容，来源抽屉可以直接打开引用的页区。上传图片使用像素坐标。

页面或区域视觉问答会把**实际图像**发送给独立视觉模型，不是对文本上下文假装看图。索引中的 `visual_description` 是机器解读，标记 `is_literal=false`；它不冒充资料原始文字，也不证明图像事实真实。

普通 Markdown / CSV 的工具页标记为“文本资料（无分页）”，仅用于展示表格和文字，不声称存在实际第 1 页。

### 数值工具

支持 Markdown、CSV（含多行单元格）和 PDF 提取表格。用户明确选择表格、列、运算、筛选与分组，后端使用 Decimal 计算：

| 操作 | 含义 |
|---|---|
| `sum / mean` | 求和 / 平均 |
| `min / max / count` | 最小值 / 最大值 / 行数 |
| `difference / ratio` | 两行的差值 / 比值 |
| `group_sum` | 按指定列分组求和 |

两行运算可以指定 0 基 `row_a`、`row_b`，按 A−B / A÷B 计算。筛选可使用等值对象，或 `[{"column":"列名","op":"eq|ne|gt|ge|lt|le","value":"值"}]`。

结果返回实际使用的来源行、原始单元格、单位及公式。例如 `0.1 + 0.2` 得到 Decimal `0.3`。混合单位、无法识别的数字和零分母不会被模型猜补；不自动做单位换算。

报告中的数值问题由模型选择受限表格操作，由上述工具执行，不运行模型生成代码。对 CSV / Markdown 计算会读取已选版本的完整表格，而不是把命中的局部窗口当成整张表。计算结果作为派生证据，并保留来源行和公式。

## API 摘要

所有数据接口沿用 `X-API-Key` / 同源部署鉴权，不向浏览器传出服务器原始文件路径。

- `GET/POST /knowledge-bases`：知识库。
- `GET/POST /knowledge-bases/{id}/conversations`：共享资料的会话。
- `GET/POST /knowledge-bases/{id}/tasks`：任务列表与创建。
- `GET /knowledge-bases/{id}/documents`：系列及历史版本。
- `GET/PATCH /research-tasks/{id}`：任务状态、提纲和条件。
- `POST /research-tasks/{id}/outline`：生成建议提纲。
- `POST /research-tasks/{id}/run`：`{section_ids?, resume:true}`。
- `POST /research-tasks/{id}/revise`：`{section_id,instruction,claim_ids?}`。
- `POST /research-tasks/{id}/sections/{section_id}/edit`：`{content}`。
- `GET /research-tasks/{id}/versions` / `versions/{revision}`：不可变报告快照。
- `GET /research-tasks/{id}/diff?from_revision=1&to_revision=2`：章节内容变化。
- `POST /research-tasks/{id}/restore/{revision}`：恢复为新版本及对应研究范围。
- `GET /research-tasks/{id}/export?format=markdown|html|json&revision=...`：下载。
- `GET /documents/series/{id}/compare?left_version=...&right_version=...`：原文差异 / 条件 / 关联结论。
- `GET /documents/versions/{id}/pages`：真实页面区域与表格，非分页资料标记虚拟分组。
- `POST /documents/versions/{id}/pages/{page}/analyze`：`{question,bbox?}`。
- `POST /documents/versions/{id}/tables/calculate`：`{table_id,operation,column,filters?,group_by?,row_a?,row_b?}`。
- `GET /documents/assets/{key}`：鉴权页面 PNG。

旧 `/conversations`、`/chat/{conversation_id}`、消息回放及检索评测接口保留。上传 Form 现在支持 `knowledge_base_id`，可附 `conversation_id`、`version_label`、`release_date`、`applicability`。

## 核心模块与轻量集成入口

- [workspace_store.py](<../workspace_store.py>)：知识库、任务、资料版本、报告快照事务。
- [reporting.py](<../reporting.py>)：分章研究、范围约束、checkpoint、稳定来源和局部修订。
- [report_api.py](<../report_api.py>)：任务、报告编辑 / 历史 / 恢复 / 下载接口。
- [version_analysis.py](<../version_analysis.py>)：可定位差异、原文锚定冲突、关联章节和结论。
- [multimodal.py](<../multimodal.py>) / [document_api.py](<../document_api.py>)：页区、实际图像输入和预览。
- [table_analysis.py](<../table_analysis.py>) / [table_tools.py](<../table_tools.py>)：解析、Decimal、受限模型操作选择。
- [evidence.py](<../evidence.py>)：问答和报告共用的证据表示。

[集成入口](<../scripts/check_workspace_integration.py>) 使用内存存储 / 脚本模型检查任务与修订契约，使用实际 PDF 和 Decimal 检查页区与计算，不输出模型质量分数或向量排名成绩：

```powershell
.\.venv\Scripts\python.exe scripts/check_workspace_integration.py
```

## 技术参考

- [PyMuPDF 页面与表格 API](https://pymupdf.readthedocs.io/en/latest/page.html)
- [Ollama 实际视觉输入](https://docs.ollama.com/capabilities/vision)
- [ChatOllama 集成](https://docs.langchain.com/oss/python/integrations/chat/ollama)
- [Vue watchers](https://vuejs.org/guide/essentials/watchers.html)
