# HANDOFF

## 当前状态

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
