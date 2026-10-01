# 证据驱动研究升级

本轮主线是复杂任务能力，不是防御性工程或扩大测试数量。交付四项相互配合的实现：结构感知证据、多跳研究、逐结论语义核验、明确关系增强。

## 1. 结构感知索引与预算化上下文

[structure.py](../structure.py)识别 Markdown ATX/Setext 标题、段落、围栏代码和表格。长块优先按原文行切分，长表的后续片段携带原始列头元数据。PDF 利用原有 Unstructured 元素类型和页码，不新增 OCR、视觉模型或整页视觉索引。

索引文本可以带章节/列头检索前缀，但 `original_content` 始终保存原文。检索输出恢复原文，前缀不会混进来源 quote 或偏移。

[context_composer.py](../context_composer.py)将同父片段的多个命中合为窗口，保留每个实际包含的 child ID，按来源轮转分配上下文。紧预算先缩邻近内容，再截取证据；被截取内容明确标记。窗口字段：

```json
{
  "content": "实际原文",
  "start_line": 12,
  "end_line": 15,
  "start_offset": 108,
  "end_offset": 190,
  "offset_scope": "source"
}
```

PDF 偏移作用域是抽取元素，不能伪装为原始 PDF 字节坐标。行号无法确定时为 null。离散窗口不会合成一个虚假的连续原文行区间；恢复的表头是独立窗口。

预算估算采用 `ceil(UTF8bytes/3) + 每文档32`，不是模型 tokenizer，也不覆盖整个聊天 prompt。报告同时显示输入 child 数、选用上下文文档数和未包含 child 数，这三个数字不必直接相减，因为多个 child 可以合为一份上下文。

旧资料仍能检索；重新上传才能获得新结构元数据。固定检索 qrels 的索引 CLI 显式关闭新切分，避免改变原来的 19 问/8 child 判定口径。

## 2. 自适应多跳研究

[research.py](../research.py)的 `ResearchEngine.run()` 统一快速与研究路径。

- `auto`：根据比较、推荐、依赖等可解释关键词路由；不是训练出的分类器。
- `quick`：单轮原文检索与统一上下文编排，不运行多跳规划或图扩展。
- `research`：模型拆解必要子问题及其依赖，先查询无依赖任务，再依据证据缺口补检。

每轮复用既有混合检索，跨问题结果交错加入证据池并按稳定 child ID 去重。评估的是实际上下文预算内的证据，不能用未提供给答案模型的召回片段假称任务已覆盖。图遍历发现的实体可成为下一轮普通文本查询。

停止原因包括：

| 原因 | 含义 |
| --- | --- |
| single_pass | 快速路径完成 |
| sufficient_evidence | gap judge 判断必要任务已有证据；辅助判断，不是事实保证 |
| no_new_evidence | 没有新证据或没有尚未尝试的查询 |
| round_budget | 达到最大研究轮次 |
| time_budget | 达到研究时间预算 |
| token_budget | 估算规划成本超过预算 |
| model_unavailable | 规划/评估模型不能完成；保留已有资料和部分完成状态 |
| empty_collection | 知识库为空 |

规划与 gap judge 输出是可观察任务决策；不暴露隐藏思维链。时间预算包含研究过程，不包含之后的回答生成和语义核验。同步检索在线程中执行，超时会停止等待，但不能强制取消底层模型计算。

## 3. 逐结论语义核验

[claim_audit.py](../claim_audit.py)执行最多两次模型调用：原子事实抽取、一次批量 judge。对没有本句引用的事实也进行检查。支持、矛盾与证据不足三类结果分别显示，回答不自动重写。

每条结论保留原回答的精确 Python 字符偏移（end-exclusive；不是浏览器 UTF-16 索引），每个证据 quote 必须是所引来源的真实连续子串。离散窗口间的拼接分隔符不构成证据。无法锚定的模型 quote 不会被当成有效支持。

默认复用配置的 Ollama 模型，不是第二个独立模型，不证明资料本身真实。模型失败、列表截断、非原子 fallback 均明确标记。前端以结论列表展示核验，不改写原聊天气泡的字符偏移或引用按钮。

## 4. 明确关系图增强

选择图增强而不是重型视觉索引，是因为当前资料和代码主要面向文本。 [graph_retrieval.py](../graph_retrieval.py)抽取明确关系，不从共同出现创造关系。

支持两种明确表达：

```markdown
| 主体 | 关系 | 客体 |
| --- | --- | --- |
| Orion | 依赖消息接入 | RelayMesh |
| RelayMesh | 使用持久队列 | AtlasQueue |

Orion --依赖消息接入--> RelayMesh
```

长表后续 child 能利用原始列头，但每条关系 quote 必须来自该 child 的原文行。关系携带 child ID、来源和原文。集合快照变化后重新派生图，无需引入 Neo4j 或维护第二份持久化真相。

最多默认两跳关系发现，普通混合检索跟进发现的实体。遍历可以沿关联关系发现资料，但不把反向遍历改称反向事实，也不把路径自动推断为因果。它不是全量自然语言知识抽取、社区摘要或完整 GraphRAG。

未进入最终生成上下文的关系证据在前端明确标为仅知识库摘录，不赋予本次回答的 `[S#]` 编号。

## 5. 使用与接口

聊天输入区提供模式选择、关系增强开关和逐结论核验开关。历史消息回放包含研究轮次与核验，不需要新数据库迁移：研究记录在已有 `retrieval_trace.research`，核验记录在 `citation_validation.semantic_audit`。

```json
{
  "messages": [{"role":"user","parts":[{"type":"text","text":"比较两套方案"}]}],
  "mode": "research",
  "graph_enabled": true,
  "audit_enabled": true
}
```

SSE 增加 `research-progress`、`claim-audit-start`、`claim-audit`；原有 `retrieval-trace`、`data-sources`、文本事件和 `citation-validation` 保留。检索在流内部执行，长研究任务会先显示实际研究阶段，而不是长时间没有响应。流开始后的失败以错误事件返回，不再尝试改变 HTTP 状态。

新配置集中在 [.env.example](../.env.example)，无需新增 Python/npm 依赖。默认最大 3 轮、4 个子问题、90 秒研究时间、16000 估算规划 tokens、6000 估算证据 tokens、12 条核验结论。生成与核验有单独时限。

## 6. 有区分度的演示案例

[研究案例](../evaluation/research/cases.json)和[5份虚构资料](../evaluation/research/corpus/)覆盖：简单事实、跨资料比较、依赖多跳、版本冲突、资料不足。

```powershell
# 真实结构/BM25/图/编排代码，脚本化 planner/judge；不是模型质量评测。
.\.venv\Scripts\python.exe scripts/run_research_cases.py --mode offline

# 使用配置好的模型；独立Chroma研究集合，不需要PostgreSQL会话。
.\.venv\Scripts\python.exe scripts/run_research_cases.py --mode live --case dependency-multihop
```

离线报告写入 [本地能力报告](../data/research-capabilities.json)，标记 `is_model_quality_benchmark=false` 和 `scripted_fixture_not_a_real_llm`；真实模式才生成真实模型回答。离线案例检查预算、真实原文偏移、长表列头恢复、关系 quote、非关系共现、两跳路径，以及 supported/contradicted/insufficient 状态与引用锚定。不以虚构百分比包装结果。

推荐演示顺序：上传5份资料 → 快速内存问答 → 深度对比方案 → Orion消息依赖与重启约束 → 16/24GB版本冲突 → 无成本/概率依据的问题。点击研究轮次、关系原文和结论 quote 展示技术决策。

## 7. 本机验证边界

本机项目虚拟环境有后端依赖；当前没有配置 DATABASE_URL、EMBEDDING_MODEL、OLLAMA_MODEL，Ollama的11434端口拒绝连接。因此已执行离线能力案例与必要构建，不能宣称真实 embedding/Ollama/数据库端到端链路已经通过。

当前进程的 `NO_PROXY` 包含 `::1,[::1]`，已安装 httpx/Ollama 在导入时会解析失败。验证时只在子进程内临时将该值设为 `localhost,127.0.0.1`，未修改系统环境或项目凭据。遇到同一导入错误，可在自己的终端进程使用有效的 NO_PROXY 本地地址列表，再启动后端。

运行依赖事实依据： [ChatOllama官方源码](https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/partners/ollama/langchain_ollama/chat_models.py)、[Unstructured元素说明](https://docs.unstructured.io/open-source/concepts/document-elements)、[Vue响应式说明](https://vuejs.org/guide/essentials/reactivity-fundamentals.html)。Context7工具在本会话未暴露，采用这些官方资料核对接口。
