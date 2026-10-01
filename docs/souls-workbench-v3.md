# 第三版：魂系攻略与版本情报工作台

本版以《艾尔登法环》《艾尔登法环黑夜君临》《黑暗之魂1／2／3》为独立研究对象，把第二版的证据研究与报告交付能力落到具体游戏条件。不是把五款游戏资料混进一个聊天提示词。

## 核心用法

1. 进入「游戏攻略」，选择游戏，创建专属知识库。
2. 确认发行版、实际补丁、平台、PVE/PVP/合作、周目、玩家进度和剧透范围。未知可明确保留；DLC未声明和明确没有DLC不同。
3. 在「官方版本情报」选择真实渠道，预览文章并导入明确的一篇。上传社区攻略、玩家装备表或页面截图时标注游戏条件与来源类型。
4. 选择 Boss、构筑、路线、补丁影响或攻略冲突模板，填写具体目标与玩家资料，创建攻略任务；确认提纲后进入研究交付运行。
5. 使用补丁影响候选定位旧报告章节，进入任务选择结论、补查并局部修订。历史报告和原有引用不会被悄悄覆盖。

### 五款游戏的独立语境

| 游戏 | 特别处理 |
|---|---|
| 艾尔登法环 | 玩家明确属性起点/目标、装备重量与资源条件；基础与扩展内容按资料和拥有条件判断。 |
| 黑夜君临 | 角色、遗物、远征和队伍，不移用法环式自由属性加点。项目未建立传统最大负重模型，提供明确数值对照而非搬用别作负重阈值。 |
| 黑魂1 | `original` / `remastered` 分开，原版 PC Prepare To Die介绍不证明全部原版主机情况；重制版官方资料单独标注。 |
| 黑魂2 | `standard` / `scholar` 分开，Steam DX9 / DX11 的购买包名不能替代真实产品身份，平台还需具体确认。 |
| 黑魂3 | 独立规则及内容条件；公告里的黑夜君临推广不当成本作补丁。 |

游戏档案是玩家声明，不是游戏事实证明。现有任务保留创建时条件快照，知识库默认条件变化不会自动重写旧攻略。游戏更换须另建知识库，不能给已有资料整库换标签。

## 专用攻略交付

每类默认五章，可修改后运行：

- **Boss**：条件、策略、准备资源、阶段/动作信号与应对窗口、建议和证据缺口。没有原文不编造抗性、招架资格或帧数。
- **构筑**：条件、方案、属性/负重预算或黑夜遗物/远征资源、取得路径与取舍、待确认项。
- **路线**：条件、路线、解锁前置、可错过内容与替代方案、建议。遵守玩家声明的剧透范围。
- **补丁影响**：逐字变化、攻略依赖、当前适用条件及复核行动，历史补丁不充当最新性证明。
- **攻略冲突**：双侧原文、来源和条件对照、条件化选择。来源等级不等于某方结论正确。

检索把具体游戏和研究目标带入每章，而非仅检索「目标Boss」「配装」等空泛模板词。普通攻略先按数据库中的游戏、发行版、补丁、模式和平台筛选资料版本，再约束向量、BM25和关系图召回。未标注游戏的旧资料不自动纳入游戏回答。

冲突模板允许同一游戏的不同发行版/模式/平台资料用于解释差异；补丁模板允许历史攻略用于对比。它们带有仅比较/历史/不可推荐标记，不能当作当前无条件建议。不同游戏仍严格隔离。资料标签人工更正以后以数据库版本记录为准；报告源的条件改变会分配新证据编号，旧章节编号和旧报告保留原快照。

## 官方情报与真实样板

渠道包括已核实的 Steam 官方产品正文、发行商公告，以及具体已核实的 Bandai补丁页面。严格排除 Steam 外部媒体转载；App ID之外还检查明确跨游戏推广。网页抓取使用有界请求与正文提取，预览不自动入库，导入时服务器重新获取真实文章，不接受客户端自行拼接的官方正文。

- `source_tier`：`official` / `community` / `player`。
- `provenance`：真实抓取 `verified_capture` / `feed_capture`，手工上传或标签声明为 `user_declared`。
- `published_at` 是文章发布时间；`captured_at` 是抓取时间。产品介绍没有公告日期，不拿产品发售日冒充。
- 游戏补丁 `patch` 不等于资料文件 `version_label`；没有明确编号就保持未知。
- 官方正文条件不继承玩家当前拥有DLC、玩法或补丁：玩家拥有内容不等于文章需要该内容。整篇同时涉及基础与DLC时，不凭提及一个DLC屏蔽全部基础信息。
- 同一实际正文/条件/来源重复导入复用资料版本；不同正文形成独立版本。

[官方来源研究记录](<souls-official-sources.md>)包含逐项官方URL、发行版和DLC依据。

首批六份实际捕获：五游戏产品介绍，以及[黑夜君临1.03.1补丁](<../knowledge/souls/nightreign/official-patch-1.03.1.md>)。后者公告发布时间 **2025-12-17**，样板抓取于 **2026-10-01**；是可引用的历史样板，不声称当前最新。产品介绍不是完整Boss数据库或攻略库，具体战斗/路线建议还需导入相应攻略与数值来源。

### 安装与样板导入

原有配置保持；先升级数据库和依赖：

```powershell
psql -U postgres -d evidence_rag -f scripts/init_db.sql
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

配置 `DATABASE_URL`、`EMBEDDING_MODEL`、`OLLAMA_MODEL` 后，预览/导入样板：

若本机导入Ollama/httpx出现 `Invalid port: ':1]'`，检查 `NO_PROXY` 的带括号IPv6条目，可在启动终端临时设 `$env:NO_PROXY='localhost,127.0.0.1'` 后重启Python。在会重新注入环境的工具里，可用Python子进程内 `os.environ['NO_PROXY']='localhost,127.0.0.1'` 临时设置；不需要改项目数据或系统代理。默认样板预览不导入Ollama/向量客户端。

```powershell
# 默认只预览计划，不创建知识库或加载模型
.\.venv\Scripts\python.exe scripts/bootstrap_souls.py
# 创建/复用五个专属样板库，索引实际捕获资料；不自动生成攻略
.\.venv\Scripts\python.exe scripts/bootstrap_souls.py --apply
# 指定一款并创建待确认的攻略提纲
.\.venv\Scripts\python.exe scripts/bootstrap_souls.py --game nightreign --apply --template patch-impact --goal "梳理已导入1.03.1原文的角色调整，并列出当前适用性待确认项"
```

`--knowledge-base-id` 可导入已绑定相同游戏的现有库，只能指定一个游戏。样板导入需要向量模型，报告研究再使用Ollama。英文官方公告配合中文攻略宜使用多语种 embedding；更换 embedding 后需重建对应索引，不直接沿用旧模型向量。视觉截图可沿用第二版 `VISION_MODEL` 和页面区域功能。

迁移仅新增知识库 `game_profile` 和资料版本 `domain_metadata`，旧库/索引不删除，旧行仍保持游戏未知。未设置数据库时先读说明与预览样板；本轮不替用户填写数据库凭据或执行未知环境的迁移。

## 补丁影响候选

从已索引、标注为本游戏 `patch_notes` 的原文抽取含变更措辞的行；每条保留原文、行号、标题上下文、版本、发行版和链接。字面实体或已有引用关联旧章节；模型配置可用时再关联已有核验结论，语义候选必须锚定真实变化ID和已有结论ID。

输出始终 `needs_confirmation`，不会改写旧报告或宣告失效。覆盖是有界的，不保证所有变化或语言别名。可在攻略 `player.entity_aliases` 声明本游戏原文名对应的语言别名，例如 `{"原文实体名":["玩家使用的别名"]}`。进入关联任务后沿用第二版定向补查/局部修订。

## 数值工具

计算基于明确输入，使用Decimal；缺少游戏公式时不假装伤害模拟器。结果包含输入、表达式、来源标注和条件。玩家提交 `source_id` / `quote` 是提供线索，不等于工具核对过原文。

- `stat_budget`：全部本作属性的 `current` / `target` 差值、需增加/减少点数和可选 `available_points` 剩余；不预设职业初值，减少点数不证明可以洗点。不适用于黑夜君临。
- `loadout_weight`：`equipment` 重量和明确 `max_load` 的合计与百分比。只有提交阈值及边界条件才分类，不内置跨游戏阈值。黑夜君临未建此模型，返回不适用。
- `table_comparison`：明确两值 `left` / `right` 的差值、比值及百分比变化；不是隐藏防御、成长修正或真实战斗伤害公式。
- 报告里的完整CSV/Markdown表格分析仍沿用第二版确定性表格工具，保留实际来源行和单位。

## 接口

| 接口 | 用途 |
|---|---|
| `GET /games` | 五游戏目录、规则提示、属性及模板概要 |
| `GET /games/{game}/templates` | 完整可编辑攻略提纲 |
| `POST /games/{game}/knowledge-bases` | 新建绑定游戏知识库，body `{title,description,profile}` |
| `PATCH /knowledge-bases/{kb}/game-profile` | 直接profile对象，返回profile；旧资料不重标 |
| `PATCH /knowledge-bases/{kb}/documents/{version}/metadata` | 直接手工metadata对象，返回资料版本 |
| `GET /games/{game}/sources` | 实际官方渠道 |
| `GET /games/{game}/updates?source_id=...&limit=10` | `{items,errors,latest_version_confirmed:false}`，错误不伪装成无更新 |
| `POST /games/{game}/import` | `{knowledge_base_id,source_id,url或external_id}`，202返回import_id/version |
| `GET /games/imports/{id}` | 持久资料状态及当前进程active |
| `GET /games/imports?knowledge_base_id=...` | 该库官方导入记录 |
| `POST /games/{game}/tasks` | `{knowledge_base_id,template_id,goal,profile,player,conditions_confirmed:true}`，仅创建待确认任务 |
| `POST /games/{game}/impact` | `{knowledge_base_id,version_id?,query?}`，原文变化、关联章节/结论和覆盖说明 |
| `POST /games/{game}/calculate` | `{operation,data,conditions?}`，明确输入算术 |

原有问答、研究交付、版本对比、导出、图文和评测接口保留。查询记录可追踪 `game_scope`，报告导出包含条件快照和官方原始链接。

## 运行方式

公告索引与报告使用现有单进程 [FastAPI BackgroundTasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)，不是分布式调度器。资料状态和原文持久保存；服务重启后可重新选择同一公告恢复待处理索引，研究任务按已有章节显式续接。剧透策略用于约束生成的攻略，原始公告、文件名和主动查看的引用原文可能含剧透，不宣称全局自动脱敏。

必要集成入口：[游戏专精检查](<../scripts/check_souls_integration.py>)。检查采用内存资料库和已有真实捕获，覆盖接口契约、来源范围、引用条件、计算和补丁关联；不替代模型质量评分或当前线上版本调查。
