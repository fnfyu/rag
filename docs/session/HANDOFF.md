# HANDOFF

## 最新：V3 魂系游戏攻略与版本情报（尚未提交）

- 用户确定第三版专精为艾尔登法环、黑夜君临、黑魂1／2／3的攻略与版本情报，不是泛游戏策划或市场分析。
- 五独立game_id/发行版/补丁/DLC/模式档案；NR不移用ER自由加点或未建模负重。五类五章攻略提纲接V2交付，game上下文贯穿章节检索、生成和逐结论核验。
- [领域模块](<../../souls_domain.py>)、[明确输入计算](<../../souls_tools.py>)、[官方采集](<../../souls_sources.py>)、[补丁影响](<../../souls_impact.py>)、[游戏接口](<../../souls_api.py>)已整合；入口版本3.0.0。
- 迁移仅增加KB.game_profile/document_versions.domain_metadata；旧证据不自动标游戏。DB记录在推理时补入旧索引metadata，兼容源ID先约束vector/BM25/graph，空范围不回退全库。条件/来源标注改变时报告证据新编号追加，不改旧引用含义。
- 同作冲突对比可以引用不同edition/mode/platform历史资料但标比较专用/不可推荐；普通攻略仍过滤不兼容版本。官方捕获条件不继承玩家的DLC拥有情况或当前模式，manual标注始终user_declared。
- Source采集实际核实官方Steam App/发行商数据，滤外部媒体转载及明确跨游戏推广（DS3 feed确有Nightreign推广，不能仅认AppID）；preview选一篇再server重抓，digest/URI/date保留，不保证latest覆盖。
- [五游戏样板](<../../knowledge/souls/>)保存6份真实捕获及manifest；NR1.03.1公告2025-12-17、捕获2026-10-01，不冒充当前最新。产品介绍非完整攻略库。[导入脚本](<../../scripts/bootstrap_souls.py>)默认只plan，--apply创建/复用专库并索引，不自动生成攻略。
- [游戏前端](<../../my-web/src/components/SoulsWorkspace.vue>)含档案、任务模板、sources/updates/import status、补丁关联、明确值计算；App新增tab保留V1/V2。背景索引仍单进程BackgroundTasks，状态和原文在DB；重启待处理导入可重新选择同公告继续。
- NR仅显式值对照，其他游戏属性/负重/对照；属性全向量明确输入、无预设职业值或阈值、玩家quote未自动核验，非战斗伤害模拟器。
- V3必要集成 [脚本](<../../scripts/check_souls_integration.py>) 与统一前端production build已通过，fixture不当model/DB成绩。V2兼容检查沿用 [既有脚本](<../../scripts/check_workspace_integration.py>) 已通过；17模块编译与默认样板预览通过。CLI在重定向Windows stdout时明确UTF-8，默认plan不导入Ollama/向量客户端。
- 配置/使用/API详见 [V3说明](<../souls-workbench-v3.md>)；primary引用和版本标签见 [来源研究](<../souls-official-sources.md>)。requirements显式补beautifulsoup4（环境已装，不额外安装），旧PyMuPDF/视觉功能保留。
- 当前仍未提供DATABASE_URL/EMBEDDING_MODEL/OLLAMA_MODEL，不执行未知DB迁移、不填凭据、不启动替代服务器、不提交。检查NO_PROXY需在Python子进程内临时设置；外层pwsh的设置被子进程环境重注入覆盖，系统环境不改。
- 用户原有未跟踪frontend api/constants/utils、权限恢复记录及V1/V2修改保持。

## V2记录（上一轮，尚未提交）

- 本轮范围为总体三版中的第二版：独立知识库 / 多研究任务、可编辑提纲 / 分章报告 / 导出、核验驱动定向补查和段落修订、资料版本及适用条件、真实页区 / 视觉输入 / Decimal 表格计算。V3 领域专精不在本轮。
- 一知识库多会话、多任务；新资料版本独立索引，旧来源和旧集合不被迁移脚本改写。现有环境须先执行 [数据库脚本](<../../scripts/init_db.sql>)。
- 任务 context 持久保存逐章 checkpoint，重启后用户点击继续；执行器仍是单服务进程后台任务，不是分布式调度。
- 报告证据编号稳定追加，局部替换按核验结论原文位置定位段落，未选段落和其他章节保留。报告历史 append-only，恢复创建新版本。
- 资料差异来自实际原文，语义冲突 quote 必须锚定，关联可能需复核的报告章节 / 结论；不以上传顺序确定有效性。
- PDF 使用 PyMuPDF 真实 bbox / 页面 PNG / 表格；已在项目虚拟环境仅增加 PyMuPDF 依赖。`VISION_MODEL` 独立于文本模型，`VISION_INDEXING_ENABLED=true` 才自动索引机器视觉描述；caption 明确不是原始文字。
- 8 类 Decimal 运算返回实际行及公式，数值报告由模型选操作但由工具计算；CSV/Markdown 使用完整已选版本表格。
- 新接口已挂载，完整配置 / API / 使用见 [V2说明](<../research-workbench-v2.md>)；所有前端入口与V1问答/评测保留。
- 必要集成入口 [脚本](<../../scripts/check_workspace_integration.py>) 覆盖分章成果、版本范围、其他章保留、稳定引用、历史恢复差异导出、原文变化及关联结论、真实PDF区域/PNG/表格和0.3 Decimal结果。存储 / 模型采用受控fixture，不作为模型质量或PostgreSQL运行成绩。
- 后端15模块编译及/health、OpenAPI挂载检查完成；前端整合生产构建完成。首次fixture因unit_id键名写错已修正，整条集成检查通过。
- 当前数据库 / embedding / Ollama配置仍需用户提供；不代填凭据、不启动额外服务。子进程临时修正NO_PROXY，不修改系统环境。PyMuPDF会提示可选layout扩展，未安装该扩展。
- 保留已有未跟踪前端api/constants/utils和权限恢复记录，未重置、未提交。

## V1记录（以下为上一轮）

## 本轮：证据驱动研究升级（尚未提交）

- 已完成结构感知索引、预算化原文窗口、多跳研究、逐结论核验、明确关系图增强及前端整合，详见[升级说明](../research-upgrade.md)。
- 新模块：[structure.py](../../structure.py)、[context_composer.py](../../context_composer.py)、[research.py](../../research.py)、[graph_retrieval.py](../../graph_retrieval.py)、[claim_audit.py](../../claim_audit.py)。
- 研究和核验保存在现有 JSONB 字段内，不需要数据库 schema 迁移；旧资料重新上传才会获得新结构元数据。
- 原检索 benchmark 索引显式关闭结构切分，保留旧 child qrels 和快照哈希契约；新研究案例使用独立集合。
- 已执行后端编译、5 个离线研究案例和原文/表头/关系/预算检查、受控 FastAPI SSE 与嵌套历史载荷检查、前端生产构建。受控模型/持久化 adapter 不是实际 Ollama/PostgreSQL；不把离线报告当作模型质量成绩。
- 离线观察：简单问答1轮、跨资料比较1轮、多跳依赖2轮、版本冲突1轮、资料不足3轮按预算停止。规划与 judge 为脚本化fixture。
- 当前虚拟环境已有后端依赖；DATABASE_URL/EMBEDDING_MODEL/OLLAMA_MODEL 未配置，11434端口拒绝连接。真实模型/数据库端到端、PDF实际解析和浏览器渲染尚未验证。
- 本机 NO_PROXY 中 IPv6 条目会导致已装 httpx/Ollama 导入失败；验证仅在子进程临时设为 localhost,127.0.0.1，未改系统环境。
- 未安装依赖、未启动替代服务器、未提交。已有未跟踪前端 api/constants/utils 与权限恢复记录保留。

## 之前轮次记录（历史状态）

Evidence RAG 作品集项目（`D:\fnfyu\projects\RAG`）。功能 arc `portfolio-grade-rag` 已提交（`c1f5274`），
本轮按 skill 符合度审阅报告完成整改，改动**尚未提交**。

## 本轮改了什么（关键路径）

- 仓库边界：`job.docx` 出库并忽略（文件仍保留在工作区）；删除 Vite 模板残留
  `my-web/src/components/HelloWorld.vue`、`my-web/public/vite.svg`、`my-web/src/assets/vue.svg`；
  重写 `my-web/README.md`，`my-web/package.json` + lock 改名为 `evidence-rag-web@1.0.0`。
- 配置：`.env.example` 补 `APP_HOST`/`APP_PORT`/`CHROMA_PATH`/`UPLOAD_DIR`/`RECORD_MANAGER_DB`，
  模型路径改为仓库根目录布局；`config.py` 新增 `app_host`/`app_port`；`starter.py` 不再硬编码绑定地址；
  `.gitignore` 覆盖 `models/`、`bge-reranker-v2-m3/`、`job.docx`。
- 检索与评测：删除无调用方的 `rewrite_query` / `rank` / `retrieve`；`HybridRetriever` 构造收敛到
  `RAGService._hybrid_retriever`；`search.py` 复用 `citations.VALIDATOR_VERSION`；trace 阶段耗时不再被
  整段耗时回填；`evaluation.py` 在 `run.effective_strategies` 与 `summary.<method>` 暴露实际生效策略与
  降级/失败题数（`evaluation_api.py` 已放行新字段）；`upload.py` 任务按阶段记录 `stage_timestamps`。
- 前端：字体改为系统栈（不再依赖 Google Fonts）、补齐 `--space-*`/`--radius-*`/`--color-muted*` 令牌并映射
  Element Plus 主色、小字统一 ≥12px、修正低对比灰字、主题化滚动条、扩大 `prefers-reduced-motion`、
  视图 tabs 补齐 ARIA 与方向键/Home/End、SSE 追加改用 rAF 跟随底部、阶段状态中文化。
- 文档：`design-system/evidence-rag/MASTER.md` 增加"实现偏差记录"；`evaluation/README.md` 补标注约定
  （未列出的 child evidence 视为 grade 0）；`docs/changes/portfolio-grade-rag/{spec-delta,tasks}.md` 增加
  MODIFIED 需求与任务 7。

## 验证状态（本轮实测）

- `py -3 -m compileall -q *.py scripts` → 通过
- `py -3 -m unittest discover -s tests` → 6 通过 / 1 跳过（`test_upload_stages` 需要未安装的 fastapi/langchain）
- `npm run build`（`my-web`）→ 通过（仍提示单 chunk >500 kB）
- 交付文案检查 `check-delivery-copy.py` → 无残留

## 未完成 / 注意

- 本机没有任何解释器安装了后端依赖（`fastapi`、`chromadb`、`langchain` 均缺失），因此 `/health`、
  上传链路、检索与评测 CLI 都**未做运行时验证**；装好 `requirements.txt` 后应补跑。
- 前端仅做静态审查 + 构建，未做浏览器渲染、对比度实测、375/768/1440 响应式实测。
- 有意保留未改：`utils.py` 六处连接骨架、评测兼容旧标注格式、重排退避与评测 API 的 stale 判定
  （删除属行为变更，需单独决策）。
- 未提交：工作区改动等待确认后再 commit。
