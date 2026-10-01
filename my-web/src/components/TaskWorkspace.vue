<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ClaimAudit from './ClaimAudit.vue'
import ResearchPanel from './ResearchPanel.vue'
const props = defineProps({ knowledgeBaseId: String, initialTaskId: String, request: { type: Function, required: true } })
const emit = defineEmits(['open-source'])
const tasks = ref([]), task = ref(null), loading = ref(false), busy = ref(false), error = ref('')
const title = ref(''), question = ref(''), outline = ref([]), applicability = ref(''), selectedVersions = ref([]), documentSeries = ref([])
const editing = ref(false), sectionEdits = ref({}), instructions = ref({}), claimSelections = ref({}), runSections = ref([])
const versions = ref([]), historyOpen = ref(false), fromRevision = ref(''), toRevision = ref(''), diff = ref(null), historical = ref(null)
let timer = null, generation = 0, disposed = false
const report = computed(() => ['running', 'planning'].includes(task.value?.status) ? task.value?.context?.draft_report || task.value?.report : task.value?.report || task.value?.context?.draft_report)
const running = computed(() => ['running', 'planning'].includes(task.value?.status) && task.value?.active !== false)
const progress = computed(() => task.value?.context?.progress)
const statusLabel = status => ({ draft: '草稿', planning: '规划中', running: '研究中', completed: '已交付', partial: '部分完成', error: '执行失败' })[status] || status
const list = (data, key) => Array.isArray(data) ? data : data?.[key] || data?.items || []
async function json(path, body, method = 'POST') { return (await props.request(path, body === undefined ? {} : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json() }
const path = () => `/research-tasks/${encodeURIComponent(task.value.id)}`
function setFields() { title.value = task.value?.title || ''; question.value = task.value?.question || ''; outline.value = JSON.parse(JSON.stringify(task.value?.outline || [])); applicability.value = task.value?.context?.applicability || ''; selectedVersions.value = [...(task.value?.context?.selected_version_ids || [])] }
function schedule() { for (const section of report.value?.sections || []) { if (!Array.isArray(claimSelections.value[section.id])) claimSelections.value[section.id] = [] } clearTimeout(timer); if (running.value && !disposed) timer = setTimeout(refresh, 1800) }
async function refresh() {
  if (!task.value) return
  const id = task.value.id, epoch = generation
  try { const value = await json(`/research-tasks/${encodeURIComponent(id)}`); if (epoch !== generation || disposed) return; task.value = value; error.value = ''; schedule() }
  catch (e) { if (epoch === generation) { error.value = `进度读取中断：${e.message}。可刷新后继续。`; clearTimeout(timer) } }
}
async function load() {
  const epoch = ++generation; clearTimeout(timer); task.value = null; tasks.value = []; documentSeries.value = []; editing.value = false; error.value = ''; historical.value = null; historyOpen.value = false
  if (!props.knowledgeBaseId) return
  loading.value = true
  try {
    const [items, docs] = await Promise.all([json(`/knowledge-bases/${encodeURIComponent(props.knowledgeBaseId)}/tasks`), json(`/knowledge-bases/${encodeURIComponent(props.knowledgeBaseId)}/documents`)])
    if (epoch !== generation) return
    tasks.value = list(items, 'tasks'); documentSeries.value = list(docs, 'document_series')
    loading.value = false
    if (props.initialTaskId && tasks.value.some(item => item.id === props.initialTaskId)) await selectTask(props.initialTaskId)
    else if (tasks.value.length) await selectTask(tasks.value[0].id)
    else { title.value = ''; question.value = ''; outline.value = []; selectedVersions.value = []; applicability.value = ''; editing.value = true }
  } catch (e) { if (epoch === generation) error.value = e.message } finally { if (epoch === generation) loading.value = false }
}
async function selectTask(id) {
  const epoch = ++generation; clearTimeout(timer); historical.value = null; diff.value = null; historyOpen.value = false; task.value = null; error.value = ''; editing.value = false; sectionEdits.value = {}; instructions.value = {}; runSections.value = []
  try { const value = await json(`/research-tasks/${encodeURIComponent(id)}`); if (epoch !== generation) return; task.value = value; setFields(); schedule() } catch (e) { if (epoch === generation) error.value = e.message }
}
async function action(work) { if (busy.value) return; busy.value = true; error.value = ''; const epoch = generation; try { await work(epoch) } catch (e) { if (epoch === generation) error.value = e.message } finally { busy.value = false } }
async function save() {
  if (!title.value.trim() || !question.value.trim()) return
  await action(async epoch => {
    const body = { title: title.value.trim(), question: question.value.trim(), outline: outline.value, context: { ...(task.value?.context || {}), selected_version_ids: selectedVersions.value, applicability: applicability.value } }
    const value = await json(task.value ? path() : `/knowledge-bases/${encodeURIComponent(props.knowledgeBaseId)}/tasks`, body, task.value ? 'PATCH' : 'POST')
    if (epoch !== generation) return; task.value = value; editing.value = false; setFields(); const index = tasks.value.findIndex(item => item.id === value.id); if (index < 0) tasks.value.unshift(value); else tasks.value[index] = value; schedule(); ElMessage.success('任务设置已保存')
  })
}
async function mutate(suffix, body) { await action(async epoch => { const value = await json(`${path()}${suffix}`, body); if (epoch !== generation) return; task.value = value; setFields(); schedule() }) }
async function generateOutline() { await mutate('/outline', {}); if (!error.value) editing.value = true }
async function run() { await mutate('/run', { resume: true, ...(runSections.value.length ? { section_ids: runSections.value } : {}) }) }
async function editSection(section) { await mutate(`/sections/${encodeURIComponent(section.id)}/edit`, { content: sectionEdits.value[section.id] }); if (!error.value) delete sectionEdits.value[section.id] }
async function revise(section) { await mutate('/revise', { section_id: section.id, instruction: instructions.value[section.id], claim_ids: claimSelections.value[section.id] || [] }) }
function newTask() { ++generation; clearTimeout(timer); task.value = null; title.value = ''; question.value = ''; outline.value = []; applicability.value = ''; selectedVersions.value = []; editing.value = true; historyOpen.value = false; historical.value = null; error.value = '' }
function addSection() { outline.value.push({ id: crypto.randomUUID(), title: '', question: '', enabled: true }) }
function segments(text = '') { return String(text).split(/(\[S\d+\])/g).filter(Boolean).map(text => ({ text, id: /^\[S\d+\]$/.test(text) ? text.slice(1, -1) : null })) }
function source(id, quote = '') { const value = report.value?.sources?.find(item => item.id === id); if (value) emit('open-source', value, quote); else ElMessage.warning(`${id} 的原文未随报告返回`) }
function evidence(item) { const value = report.value?.sources?.find(s => (item.evidence_id ? [s.evidence_id, s.chunk_id, s.child_chunk_id, ...(s.child_chunk_ids || [])].includes(item.evidence_id) || (s.evidence || []).some(hit => [hit.evidence_id, hit.chunk_id, hit.child_chunk_id].includes(item.evidence_id)) : Boolean(item.source_id) && s.id === item.source_id)); if (value) emit('open-source', value, item.quote || ''); else if (item.quote) emit('open-source', { ...item, content: item.quote, quote_only: true }); else ElMessage.warning('没有可定位的原文') }
async function loadHistory() { historyOpen.value = true; await action(async () => { versions.value = list(await json(`${path()}/versions`), 'versions'); const ordered = [...versions.value].sort((a,b) => a.revision-b.revision); fromRevision.value = ordered[0]?.revision ?? ''; toRevision.value = ordered.at(-1)?.revision ?? '' }) }
async function compare() { await action(async () => { diff.value = await json(`${path()}/diff?from_revision=${encodeURIComponent(fromRevision.value)}&to_revision=${encodeURIComponent(toRevision.value)}`) }) }
async function preview(revision) { await action(async () => { historical.value = await json(`${path()}/versions/${revision}`) }) }
async function restore(revision) { try { await ElMessageBox.confirm(`恢复修订 ${revision} 将创建一个新版本，不覆盖历史。`, '确认恢复', { type: 'warning' }); await mutate(`/restore/${revision}`, {}); await loadHistory() } catch (e) { if (e !== 'cancel' && e !== 'close') error.value = e.message } }
async function download(format) { await action(async () => { const response = await props.request(`${path()}/export?format=${format}`); const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `research-${task.value.id}.${format === 'markdown' ? 'md' : format}`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }) }
watch(() => props.knowledgeBaseId, load, { immediate: true })
watch(() => props.initialTaskId, id => { if (id && id !== task.value?.id) selectTask(id) })
onBeforeUnmount(() => { disposed = true; ++generation; clearTimeout(timer) })
</script>

<template>
  <div v-if="!knowledgeBaseId" class="v2-empty">
    <h2>研究从共享知识库开始</h2>
    <p>选择或新建知识库，上传资料后创建研究交付任务。</p>
  </div>
  <div v-else class="task-workspace">
    <aside class="task-list">
      <div class="v2-heading">
        <h2>研究任务</h2>
        <el-button :disabled="busy" @click="newTask">新建</el-button>
      </div>
      <p class="panel-note">从提纲到交付，逐章保留检查点。</p>
      <p v-if="loading" role="status">加载中…</p>
      <button v-for="item in tasks" :key="item.id" type="button" class="task-item" :class="{ active: task?.id === item.id }" :disabled="busy" @click="selectTask(item.id)">
        <strong>{{ item.title }}</strong>
        <small>{{ statusLabel(item.status) }} · 修订 {{ item.revision || 0 }}</small>
      </button>
      <el-button :disabled="busy" text @click="load">刷新任务列表</el-button>
    </aside>
    <div class="task-detail">
      <div v-if="error" class="v2-error" role="alert">{{ error }} <el-button text :disabled="busy" @click="task ? refresh() : load()">重试读取</el-button>
      </div>
      <div v-if="task" class="v2-heading">
        <div>
          <p class="eyebrow">研究交付 · 修订 {{ task.revision }}</p>
          <h2>{{ task.title }}</h2>
          <p v-if="task.context?.game" class="panel-note">攻略条件：{{ task.context.game.game_id }} · {{ task.context.game.edition || '版本未知' }} · 补丁 {{ task.context.game.patch || '未知' }} · {{ task.context.game.mode || '玩法未知' }} · 剧透 {{ task.context.game.spoiler_policy || '未确认' }}。保留任务条件快照。</p>
          <p class="panel-note">{{ statusLabel(task.status) }}<template v-if="task.active === false && ['running','planning'].includes(task.status)"> · 执行已中断，可续接检查点</template>
          </p>
        </div>
        <div class="v2-actions">
          <el-button :disabled="busy" @click="refresh">刷新进度</el-button>
          <el-button :disabled="busy || running" @click="setFields(); editing = !editing">编辑设置</el-button>
          <el-button :disabled="busy || running" @click="loadHistory">版本历史</el-button>
        </div>
      </div>
      <form v-if="editing" class="v2-card v2-form" @submit.prevent="save">
        <h3>{{ task ? '确认修改任务与提纲' : '创建研究任务' }}</h3>
        <label>任务名称<input v-model="title" required maxlength="160" />
        </label>
        <label>研究问题<textarea v-model="question" rows="3" required />
        </label>
        <label>适用条件<textarea v-model="applicability" rows="2" placeholder="如：地区、政策生效时间、产品型号；未知条件不要默认为适用" />
        </label>
        <details>
          <summary>选择使用的资料版本（未选择时由后端检索库内资料）</summary>
          <div v-for="series in documentSeries" :key="series.id" class="version-checklist">
            <strong>{{ series.filename }}</strong>
            <label v-for="version in series.versions" :key="version.id" class="v2-check">
              <input v-model="selectedVersions" type="checkbox" :value="version.id" />{{ version.version_label || '未标版本' }} · {{ version.release_date || '日期未知' }} · {{ version.applicability || '适用条件未知' }}<span v-if="version.domain_metadata?.game_id"> · {{ version.domain_metadata.game_id }} / {{ version.domain_metadata.edition || '版本未知' }} / 补丁 {{ version.domain_metadata.patch || '未知' }}</span></label>
          </div>
        </details>
        <div class="v2-heading">
          <h3>可编辑提纲</h3>
          <el-button @click="addSection">添加章节</el-button>
        </div>
        <div v-for="(section,index) in outline" :key="section.id" class="outline-editor">
          <label class="v2-check">
            <input v-model="section.enabled" type="checkbox" />研究本章</label>
          <label>章节标题<input v-model="section.title" required />
          </label>
          <label>本章问题<textarea v-model="section.question" rows="2" required />
          </label>
          <div class="v2-actions">
            <el-button :disabled="index === 0" @click="outline.splice(index - 1, 0, outline.splice(index,1)[0])">上移</el-button>
            <el-button :disabled="index === outline.length - 1" @click="outline.splice(index + 1, 0, outline.splice(index,1)[0])">下移</el-button>
            <el-button @click="outline.splice(index,1)">删除</el-button>
          </div>
        </div>
        <div class="v2-actions">
          <el-button native-type="submit" type="primary" :loading="busy" :disabled="!title.trim() || !question.trim()">{{ task ? '确认保存修改' : '创建任务' }}</el-button>
          <el-button v-if="task" :disabled="busy" @click="editing = false">取消修改</el-button>
        </div>
      </form>
      <template v-if="task && !editing">
        <p class="task-question">{{ task.question }}</p>
        <div class="v2-card">
          <div class="v2-actions">
            <el-button :disabled="busy || running" @click="generateOutline">生成可编辑提纲</el-button>
            <el-button type="primary" :loading="busy || running" :disabled="busy || running || !task.outline?.length" @click="run">{{ ['partial','error','running'].includes(task.status) ? '继续研究' : '开始研究' }}</el-button>
            <el-button v-for="format in ['markdown','html','json']" :key="format" :disabled="busy || !task.report || running" @click="download(format)">导出 {{ format.toUpperCase() }}</el-button>
          </div>
          <p class="panel-note">勾选章节只执行选中章节；未勾选时续接任务。每章完成即保存检查点。</p>
          <label v-for="section in task.outline" :key="section.id" class="v2-check">
            <input v-model="runSections" type="checkbox" :value="section.id" :disabled="running || busy || section.enabled === false" />{{ section.title }}<small>{{ section.enabled === false ? '（已禁用）' : section.question }}</small>
          </label>
        </div>
        <section v-if="progress" class="v2-progress" aria-live="polite">
          <strong>{{ progress.message || progress.stage }}</strong>
          <p>{{ progress.stage }} · 章节 {{ progress.index ?? '—' }}/{{ progress.total ?? '—' }}<template v-if="progress.section_id"> · {{ progress.section_id }}</template>
          </p>
          <details v-if="progress.events?.length">
            <summary>执行事件</summary>
            <pre class="v2-pre">{{ progress.events.map(event => typeof event === 'string' ? event : JSON.stringify(event)).join('\n') }}</pre>
          </details>
        </section>
        <p v-if="report && (!task.report || ['running','planning'].includes(task.status))" class="panel-note">以下为已保存的章节草稿，尚非最终交付。</p>
        <article v-for="section in report?.sections || []" :key="section.id" class="report-chapter v2-card">
          <div class="v2-heading">
            <h3>{{ section.title }}</h3>
            <span class="report-badge">{{ statusLabel(section.status) }}</span>
          </div>
          <p class="panel-note">{{ section.question }}</p>
          <div v-if="sectionEdits[section.id] === undefined" class="report-text">
            <template v-for="(part,index) in segments(section.content)" :key="index">
              <button v-if="part.id" class="inline-citation" type="button" @click="source(part.id)">{{ part.text }}</button>
              <span v-else>{{ part.text }}</span>
            </template>
          </div>
          <label v-else class="v2-form">编辑本章正文<textarea v-model="sectionEdits[section.id]" rows="12" />
          </label>
          <div class="v2-actions">
            <el-button v-if="sectionEdits[section.id] === undefined" :disabled="busy || running" @click="sectionEdits[section.id] = section.content">编辑本章</el-button>
            <template v-else>
              <el-button type="primary" :disabled="busy || running" @click="editSection(section)">确认保存为新版本</el-button>
              <el-button @click="delete sectionEdits[section.id]">取消编辑</el-button>
            </template>
            <el-button v-for="id in section.sources || []" :key="id" text @click="source(id)">{{ id }} 原文</el-button>
          </div>
          <ResearchPanel :trace="section.trace" @open-evidence="evidence" />
          <ClaimAudit :audit="section.audit" @open-evidence="evidence" />
          <div v-if="section.unresolved?.length" class="v2-warning">
            <strong>未解决的问题</strong>
            <ul>
              <li v-for="(item,index) in section.unresolved" :key="index">{{ typeof item === 'string' ? item : JSON.stringify(item) }}</li>
            </ul>
          </div>
          <details class="chapter-revision">
            <summary>定向补查并只修订本章</summary>
            <div class="v2-form">
              <label>修订指令<textarea v-model="instructions[section.id]" rows="3" placeholder="明确要补查的结论、条件或证据缺口" />
              </label>
              <div v-if="section.audit?.claims?.length">
                <p class="panel-note">可选：限定待修订结论</p>
                <label v-for="claim in section.audit.claims" :key="claim.id" class="v2-check">
                  <input v-model="claimSelections[section.id]" type="checkbox" :value="claim.id" />{{ claim.id }} · {{ claim.text }}</label>
              </div>
              <el-button type="primary" :disabled="busy || running || !instructions[section.id]?.trim()" @click="revise(section)">补查修订本章</el-button>
              <p class="panel-note">不重做其他章节；完成后生成不可变修订版本。</p>
            </div>
          </details>
        </article>
        <div v-if="!report && !running" class="v2-empty">
          <h3>确认提纲后开始研究</h3>
          <p>报告按章节交付，原文引用、核验与未解决问题会一起保留。</p>
        </div>
      </template>
      <section v-if="historyOpen" class="v2-card">
        <div class="v2-heading">
          <h3>不可变版本历史</h3>
          <el-button @click="historyOpen = false">收起</el-button>
        </div>
        <div v-for="version in versions" :key="version.revision" class="history-row">
          <span>修订 {{ version.revision }} · {{ version.kind }} · {{ version.created_at }}<small>{{ typeof version.changes === 'string' ? version.changes : JSON.stringify(version.changes) }}</small>
          </span>
          <div class="v2-actions">
            <el-button :disabled="busy" @click="preview(version.revision)">查看</el-button>
            <el-button :disabled="busy || running" @click="restore(version.revision)">恢复为新版本</el-button>
          </div>
        </div>
        <div class="v2-form-grid">
          <label>原修订<select v-model="fromRevision">
              <option v-for="v in versions" :key="v.revision" :value="v.revision">{{ v.revision }}</option>
            </select>
          </label>
          <label>目标修订<select v-model="toRevision">
              <option v-for="v in versions" :key="v.revision" :value="v.revision">{{ v.revision }}</option>
            </select>
          </label>
          <el-button :disabled="busy || fromRevision === '' || toRevision === ''" @click="compare">比较历史差异</el-button>
        </div>
        <article v-for="section in diff?.sections || []" :key="section.id" class="diff-section">
          <h4>{{ section.title }} · {{ section.kind }}</h4>
          <div class="diff-columns">
            <pre class="v2-pre">{{ typeof section.before === 'string' ? section.before : JSON.stringify(section.before,null,2) }}</pre>
            <pre class="v2-pre">{{ typeof section.after === 'string' ? section.after : JSON.stringify(section.after,null,2) }}</pre>
          </div>
          <details>
            <summary>逐行差异</summary>
            <pre class="v2-pre">{{ section.unified_diff }}</pre>
          </details>
        </article>
        <p v-if="diff && !diff.sections?.length" class="panel-note">这两个修订没有章节差异。</p>
        <div v-if="historical">
          <h4>历史报告 · 修订 {{ historical.revision }}</h4>
          <article v-for="section in historical.report?.sections || []" :key="section.id">
            <h4>{{ section.title }}</h4>
            <pre class="v2-pre">{{ section.content }}</pre>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>
