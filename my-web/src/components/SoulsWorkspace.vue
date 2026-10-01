<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'

// This module owns game conditions and provenance; App owns KB selection and V2 navigation.
const props = defineProps({ knowledgeBase: Object, knowledgeBases: Array, request: { type: Function, required: true } })
const emit = defineEmits(['open-task', 'select-knowledge-base', 'changed'])
const GAME_IDS = ['elden-ring', 'nightreign', 'dark-souls-1', 'dark-souls-2', 'dark-souls-3']
const catalog = ref([]), gameId = ref('elden-ring'), templates = ref([]), sources = ref([]), updates = ref([]), tasks = ref([])
const loading = ref(false), busy = ref(''), error = ref(''), notice = ref(''), feedError = ref(''), feedErrors = ref([]), feedLoaded = ref(false)
const sourceId = ref(''), limit = ref(10), templateId = ref(''), goal = ref(''), confirmed = ref(false)
const kbTitle = ref(''), kbDescription = ref(''), createOpen = ref(false), dlcText = ref(''), playerJson = ref('{}')
const profile = reactive(emptyProfile())
const dlcUnknown = ref(true)
const importJobs = ref([]), impact = ref(null), impactVersion = ref(''), impactQuery = ref(''), documentVersions = ref([])
const operation = ref('loadout_weight'), statsJson = ref('{\n  "starting_stats": {},\n  "target_stats": {}\n}'), thresholdsJson = ref('[]')
const comparisonJson = ref('{\n  "left": 0,\n  "right": 0,\n  "unit": ""\n}')
const maxLoad = ref(''), weightRows = ref([{ name: '', weight: '', source_id: '', quote: '' }]), calculation = ref(null)
let epoch = 0, timer = null, disposed = false
function emptyProfile() { return { edition: '', patch: '', platform: '', mode: '', cycle: '', progress: '', player_level: '', character: '', spoiler_policy: 'none' } }
const game = computed(() => catalog.value.find(item => item.id === gameId.value))
const boundGame = computed(() => props.knowledgeBase?.game_profile?.game_id)
const scoped = computed(() => Boolean(props.knowledgeBase?.id && boundGame.value === gameId.value))
const matchingBases = computed(() => (props.knowledgeBases || []).filter(kb => kb.game_profile?.game_id === gameId.value))
const isNightreign = computed(() => gameId.value === 'nightreign')
const statFields = computed(() => game.value?.stats || game.value?.fields?.stats || game.value?.fields?.attributes || [])
const statLabels = computed(() => Array.isArray(statFields.value) ? statFields.value.map(item => typeof item === 'string' ? item : `${item.label || item.id} (${item.id})`).join('、') : Object.keys(statFields.value).join('、'))
const selectedTemplate = computed(() => templates.value.find(item => item.id === templateId.value))
const list = (payload, key) => Array.isArray(payload) ? payload : payload?.[key] || payload?.items || []
const pretty = value => JSON.stringify(value, null, 2)
const text = value => typeof value === 'string' ? value : value == null ? '未提供' : pretty(value)
const optionId = item => typeof item === 'string' ? item : item.id || item.value
const optionLabel = item => typeof item === 'string' ? item : item.label || item.title || item.id
const safeUrl = value => { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null } catch { return null } }
const time = value => { if (!value) return '未知'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '未知' : date.toLocaleString('zh-CN') }
async function json(path, body, method = 'POST') {
  return (await props.request(path, body === undefined ? {} : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json()
}
function profileBody() {
  const body = { ...profile, game_id: gameId.value, player_level: profile.player_level === '' || profile.player_level == null ? null : Number(profile.player_level) }
  delete body.dlc
  if (!dlcUnknown.value) body.dlc = dlcText.value.split(/[,，\n]/).map(value => value.trim()).filter(Boolean)
  return body
}
function requireScope() { if (!scoped.value) throw new Error('请先选择本游戏的专属知识库；不会使用其他游戏资料。') }
function parseObject(value, label) { const parsed = JSON.parse(value); if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error(`${label}必须是 JSON 对象`); return parsed }
async function action(name, work) {
  if (busy.value) return
  busy.value = name; error.value = ''; notice.value = ''
  const current = epoch
  try { await work(current) } catch (e) { if (current === epoch) error.value = e.message } finally { busy.value = '' }
}
function syncProfile() {
  const stored = scoped.value ? props.knowledgeBase.game_profile : {}
  Object.assign(profile, emptyProfile(), stored)
  dlcText.value = (stored.dlc || []).join(', '); dlcUnknown.value = !Array.isArray(stored.dlc); confirmed.value = false
  if (isNightreign.value) operation.value = 'table_comparison'
}
async function loadScope() {
  const current = ++epoch
  clearTimeout(timer); syncProfile(); tasks.value = []; documentVersions.value = []; impact.value = null; calculation.value = null; error.value = ''; notice.value = ''
  if (!scoped.value) return
  try {
    const kb = encodeURIComponent(props.knowledgeBase.id)
    const [taskData, docs] = await Promise.all([json(`/knowledge-bases/${kb}/tasks`), json(`/knowledge-bases/${kb}/documents`)])
    if (current !== epoch || disposed) return
    tasks.value = list(taskData, 'tasks')
    documentVersions.value = list(docs, 'document_series').flatMap(series => (series.versions || []).map(version => ({ ...version, filename: series.filename })))
    scheduleImports()
  } catch (e) { if (current === epoch) error.value = e.message }
}
let gameSequence = 0
async function loadGame() {
  const current = ++gameSequence
  templates.value = []; sources.value = []; updates.value = []; feedErrors.value = []; feedError.value = ''; feedLoaded.value = false; sourceId.value = ''; templateId.value = ''; loading.value = true
  try {
    const id = encodeURIComponent(gameId.value)
    const [templateData, sourceData] = await Promise.all([json(`/games/${id}/templates`), json(`/games/${id}/sources`)])
    if (current !== gameSequence || disposed) return
    templates.value = list(templateData, 'templates'); sources.value = list(sourceData, 'sources')
    templateId.value = templates.value[0]?.id || ''; sourceId.value = sources.value[0]?.id || ''
  } catch (e) { if (current === gameSequence) error.value = e.message } finally { if (current === gameSequence) loading.value = false }
}
async function loadCatalog() {
  loading.value = true; error.value = ''
  try { catalog.value = list(await json('/games'), 'catalog').filter(item => GAME_IDS.includes(item.id)); if (boundGame.value) gameId.value = boundGame.value; await loadGame() }
  catch (e) { error.value = e.message } finally { loading.value = false }
}
async function fetchUpdates() {
  await action('updates', async current => {
    feedError.value = ''; feedErrors.value = []; updates.value = []; feedLoaded.value = false
    const selectedGame = gameId.value
    try {
      const payload = await json(`/games/${encodeURIComponent(selectedGame)}/updates?source_id=${encodeURIComponent(sourceId.value)}&limit=${encodeURIComponent(limit.value)}`)
      if (current !== epoch || selectedGame !== gameId.value) return
      updates.value = payload.items || []; feedErrors.value = payload.errors || []; feedLoaded.value = true
    } catch (e) { if (current === epoch) feedError.value = `抓取失败：${e.message}。无法判断当前最新版本。` }
  })
}
async function createBase() {
  await action('create-kb', async current => {
    const kb = await json(`/games/${encodeURIComponent(gameId.value)}/knowledge-bases`, { title: kbTitle.value.trim(), description: kbDescription.value.trim(), profile: profileBody() })
    if (current !== epoch) return
    createOpen.value = false; kbTitle.value = ''; kbDescription.value = ''; emit('select-knowledge-base', kb.id)
  })
}
async function saveProfile() {
  await action('profile', async current => {
    if (!props.knowledgeBase?.id) throw new Error('请先选择知识库')
    if (boundGame.value && boundGame.value !== gameId.value) throw new Error('此库属于另一游戏；请创建专属库，不可改绑。')
    await json(`/knowledge-bases/${encodeURIComponent(props.knowledgeBase.id)}/game-profile`, profileBody(), 'PATCH')
    if (current !== epoch) return
    notice.value = '游戏条件已持久化；旧资料不自动变成已核验来源。'; emit('changed')
  })
}
async function createTask() {
  await action('task', async current => {
    requireScope()
    const task = await json(`/games/${encodeURIComponent(gameId.value)}/tasks`, { knowledge_base_id: props.knowledgeBase.id, template_id: templateId.value, goal: goal.value.trim(), profile: profileBody(), player: parseObject(playerJson.value, '玩家信息'), conditions_confirmed: confirmed.value })
    if (current !== epoch) return
    emit('open-task', task.id)
  })
}
async function importArticle(item) {
  await action('import', async current => {
    requireScope()
    if (!item.source_id || (!item.external_id && !safeUrl(item.url))) throw new Error('缺少明确文章与来源，不能导入来源首页。')
    const job = await json(`/games/${encodeURIComponent(gameId.value)}/import`, { knowledge_base_id: props.knowledgeBase.id, source_id: item.source_id, external_id: item.external_id, url: item.url, edition: item.edition || undefined, patch: item.patch || undefined, mode: item.mode || undefined, requires_dlc: item.requires_dlc })
    importJobs.value.unshift({ ...job, title: item.title, knowledge_base_id: props.knowledgeBase.id, game_id: gameId.value })
    if (current !== epoch) return
    notice.value = '文章已排队，服务器将重新抓取核验；排队不等于已入库。'; scheduleImports()
  })
}
async function refreshImports() {
  clearTimeout(timer)
  const current = epoch
  const pending = importJobs.value.filter(job => job.knowledge_base_id === props.knowledgeBase?.id && ['queued', 'running'].includes(job.status))
  await Promise.all(pending.map(async job => {
    try { const value = await json(`/games/imports/${encodeURIComponent(job.import_id)}`); Object.assign(job, value); delete job.poll_error; if (value.status === 'completed' && current === epoch) emit('changed') }
    catch (e) { job.poll_error = `状态读取失败：${e.message}，请手动刷新确认。` }
  }))
  if (current === epoch && !disposed) scheduleImports()
}
function scheduleImports() { clearTimeout(timer); if (!disposed && importJobs.value.some(job => job.knowledge_base_id === props.knowledgeBase?.id && ['queued', 'running'].includes(job.status) && !job.poll_error)) timer = setTimeout(refreshImports, 2200) }
async function checkImpact() {
  await action('impact', async current => {
    requireScope(); impact.value = null
    const value = await json(`/games/${encodeURIComponent(gameId.value)}/impact`, { knowledge_base_id: props.knowledgeBase.id, version_id: impactVersion.value || undefined, query: impactQuery.value.trim() || undefined })
    if (current === epoch) impact.value = value
  })
}
async function calculate() {
  await action('calculate', async current => {
    calculation.value = null
    if (isNightreign.value && operation.value !== 'table_comparison') throw new Error('Nightreign 未建立属性预算或传统负重模型，仅提供明确数值对照。')
    const data = operation.value === 'table_comparison' ? parseObject(comparisonJson.value, '数值对照') : operation.value === 'stat_budget' ? parseObject(statsJson.value, '属性预算') : { items: weightRows.value.filter(row => row.name.trim() || row.weight !== '').map(row => { if (!row.name.trim() || row.weight === '' || !Number.isFinite(Number(row.weight)) || Number(row.weight) < 0) throw new Error('请为每个装备填写名称与非负重量'); return { name: row.name.trim(), weight: { value: Number(row.weight), source_id: row.source_id || undefined, quote: row.quote || undefined } } }), max_load: Number(maxLoad.value) }
    if (operation.value === 'loadout_weight') {
      data.equipment = data.items; delete data.items
      const thresholds = JSON.parse(thresholdsJson.value)
      if (!Array.isArray(thresholds)) throw new Error('阈值必须是 JSON 数组：[{"label":"名称","max_percent":数值}]')
      if (thresholds.length) data.thresholds = thresholds
    }
    if (operation.value === 'loadout_weight' && (maxLoad.value === '' || Number(maxLoad.value) <= 0)) throw new Error('最大负重必须为正数，不能由职业或等级猜测。')
    const value = await json(`/games/${encodeURIComponent(gameId.value)}/calculate`, { operation: operation.value, data, conditions: profileBody() })
    if (current === epoch) calculation.value = value
  })
}
watch(() => props.knowledgeBase?.id, () => { if (boundGame.value) gameId.value = boundGame.value; loadScope() })
watch(() => props.knowledgeBase?.game_profile, loadScope, { deep: true })
watch(gameId, () => { loadScope(); loadGame() })
watch([profile, dlcText, dlcUnknown], () => { confirmed.value = false }, { deep: true })
watch(operation, () => { calculation.value = null })
loadCatalog(); loadScope()
onBeforeUnmount(() => { disposed = true; ++epoch; ++gameSequence; clearTimeout(timer) })
</script>

<template>
  <div class="souls-workspace">
    <div class="v2-heading">
      <div>
        <p class="eyebrow">
          V3 · Souls evidence desk
        </p>
        <h2>
          游戏攻略与版本情报
        </h2>
        <p class="panel-note">
          一款游戏，一个资料域。条件先确认，情报回到原文，攻略进入可编辑的研究交付。
        </p>
      </div>
      <el-button :loading="loading" :disabled="!!busy" @click="loadCatalog">
        刷新游戏目录
      </el-button>
    </div>
    <p v-if="error" class="v2-error" role="alert">
      {{ error }}
    </p>
    <p v-if="notice" class="v2-progress" role="status">
      {{ notice }}
    </p>
    <div class="souls-game-picker" role="group" aria-label="选择独立游戏项目">
      <button v-for="entry in catalog" :key="entry.id" type="button" :aria-pressed="entry.id === gameId" :class="{ active: entry.id === gameId }" :disabled="!!busy" @click="gameId = entry.id">
        <strong>
          {{ entry.title }}
        </strong>
        <small>
          {{ entry.id === 'nightreign' ? '独立远征项目 · 角色 / 遗物' : entry.id === 'elden-ring' ? '开放世界 · 本体 / DLC' : entry.editions.map(optionLabel).join(' / ') }}
        </small>
      </button>
    </div>
    <p v-if="!catalog.length && !loading" class="v2-warning">
      游戏目录未加载，不提供虚构游戏、模板或最新补丁。请重试目录接口。
    </p>
    <template v-if="game">
      <section class="souls-section">
        <h3>
          {{ game.title }} · 专属知识库
        </h3>
        <div class="v2-form-grid">
          <label>
            已绑定本游戏的知识库
            <select :value="scoped ? knowledgeBase.id : ''" :disabled="!!busy" @change="$event.target.value && emit('select-knowledge-base', $event.target.value)">
              <option value="">
                选择本游戏专属库
              </option>
              <option v-for="kb in matchingBases" :key="kb.id" :value="kb.id">
                {{ kb.title }}
              </option>
            </select>
          </label>
          <el-button :disabled="!!busy" @click="createOpen = !createOpen">
            新建 {{ game.title }} 专属库
          </el-button>
        </div>
        <p v-if="!scoped" class="v2-warning">
          {{ boundGame ? '当前知识库属于其他游戏，不允许改绑或混用资料。' : '当前库尚未绑定游戏；可建立专属库，或显式保存条件绑定。已有不同游戏标注资料时服务器会拒绝。' }}
        </p>
        <ul v-if="game.rule_notes?.length" class="souls-rules">
          <li v-for="(rule,index) in game.rule_notes" :key="index">
            {{ text(rule) }}
          </li>
        </ul>
        <p v-if="isNightreign" class="panel-note">
          Nightreign 与 Elden Ring 是两个独立项目；使用角色、遗物、远征与队伍条件，不套用 Elden Ring 八属性加点表。
        </p>
        <form class="v2-form" @submit.prevent="saveProfile">
          <div class="souls-condition-grid">
            <label>
              版本 / Edition
              <select v-model="profile.edition">
                <option value="">
                  未知 / 未确认
                </option>
                <option v-for="edition in game.editions" :key="optionId(edition)" :value="optionId(edition)">
                  {{ optionLabel(edition) }}
                </option>
              </select>
            </label>
            <label>
              补丁版本
              <input v-model="profile.patch" placeholder="未知则留空，不推断最新" />
            </label>
            <label>
              平台
              <select v-model="profile.platform">
                <option value="">
                  未知 / 未确认
                </option>
                <option v-for="platform in game.platforms" :key="optionId(platform)" :value="optionId(platform)">
                  {{ optionLabel(platform) }}
                </option>
              </select>
            </label>
            <label>
              玩法 / 联机
              <select v-model="profile.mode">
                <option value="">
                  未知 / 未确认
                </option>
                <option v-for="mode in game.modes" :key="optionId(mode)" :value="optionId(mode)">
                  {{ optionLabel(mode) }}
                </option>
              </select>
            </label>
            <label>
              DLC 访问（逗号分隔）
              <input v-model="dlcText" :disabled="dlcUnknown" placeholder="确认无DLC时留空；填写可访问内容" />
            </label>
            <label>
              {{ isNightreign ? '远征 / 难度阶段' : '周目' }}
              <input v-model="profile.cycle" placeholder="玩家实际条件，未知则留空" />
            </label>
            <label>
              当前进度
              <input v-model="profile.progress" placeholder="区域、首领或解锁进度" />
            </label>
            <label>
              剧透策略
              <select v-model="profile.spoiler_policy">
                <option value="none">
                  不剧透
                </option>
                <option value="bosses">
                  允许首领信息
                </option>
                <option value="full">
                  允许完整剧透
                </option>
              </select>
            </label>
            <label>
              {{ isNightreign ? '夜渡者 / 角色' : '角色 / 流派' }}
              <input v-model="profile.character" placeholder="玩家输入，不猜测职业基值" />
            </label>
            <label>
              玩家等级（可选）
              <input v-model="profile.player_level" type="number" min="1" step="1" />
            </label>
          </div>
          <label class="v2-check">
            <input v-model="dlcUnknown" type="checkbox" />
            DLC 访问未知（不发送空列表）；取消勾选且留空表示明确无 DLC
          </label>
          <p v-if="game.dlcs?.length" class="panel-note">
            目录 DLC：{{ game.dlcs.map(optionLabel).join('、') }}。名单不代表你已拥有访问权限。
          </p>
          <p v-if="!String(profile.patch || '').trim()" class="panel-note">
            补丁未知：无法断言资料适用于当前游戏版本。请在游戏内核对；不会自动填写最新补丁。
          </p>
          <div class="v2-actions">
            <el-button native-type="submit" :loading="busy === 'profile'" :disabled="!!busy || !knowledgeBase?.id || (!!boundGame && !scoped)">
              {{ scoped ? '保存游戏条件' : '显式绑定当前库并保存条件' }}
            </el-button>
          </div>
        </form>
        <form v-if="createOpen" class="v2-form souls-create" @submit.prevent="createBase">
          <label>
            专属库名称
            <input v-model="kbTitle" required maxlength="160" />
          </label>
          <label>
            说明
            <textarea v-model="kbDescription" rows="2" />
          </label>
          <p class="panel-note">
            以上游戏条件将随知识库持久化。一个知识库只绑定一款游戏。
          </p>
          <el-button native-type="submit" type="primary" :loading="busy === 'create-kb'" :disabled="!!busy || !kbTitle.trim()">
            创建专属知识库
          </el-button>
        </form>
      </section>
      <section class="souls-section">
        <div class="v2-heading">
          <div>
            <h3>
              {{ isNightreign ? '角色 · 遗物 · 远征攻略' : '条件化攻略任务' }}
            </h3>
            <p class="panel-note">
              创建任务但不自动执行；进入研究交付后确认或修改提纲。
            </p>
          </div>
        </div>
        <form class="v2-form" @submit.prevent="createTask">
          <label>
            攻略模板
            <select v-model="templateId">
              <option value="">
                选择目录模板
              </option>
              <option v-for="item in templates" :key="item.id" :value="item.id">
                {{ item.title }}
              </option>
            </select>
          </label>
          <p v-if="selectedTemplate" class="panel-note">
            {{ selectedTemplate.description }}
          </p>
          <details v-if="selectedTemplate">
            <summary>
              查看完整模板与适用条件
            </summary>
            <pre class="v2-pre">
              {{ pretty(selectedTemplate) }}
            </pre>
          </details>
          <label>
            攻略目标
            <textarea v-model="goal" rows="3" required :placeholder="isNightreign ? '描述夜渡者、遗物、远征与队伍协作目标' : '描述首领、路线、流派与资源限制'" />
          </label>
          <details>
            <summary>
              玩家信息 JSON（可选）
            </summary>
            <label>
              实际装备 / 遗物 / 队伍 / 属性
              <textarea v-model="playerJson" rows="5" spellcheck="false" />
            </label>
            <p class="panel-note">
              只填写玩家实际输入；不预置职业或装备数值。
            </p>
          </details>
          <label class="v2-check">
            <input v-model="confirmed" type="checkbox" :disabled="!scoped" />
            我已核对以上游戏条件，包括未知补丁与剧透限制
          </label>
          <el-button native-type="submit" type="primary" :loading="busy === 'task'" :disabled="!!busy || !scoped || !confirmed || !templateId || !goal.trim()">
            创建攻略任务 · 前往研究交付
          </el-button>
        </form>
        <details v-if="scoped">
          <summary>
            本知识库旧任务 · {{ tasks.length }}
          </summary>
          <button v-for="task in tasks" :key="task.id" type="button" class="task-item" @click="emit('open-task', task.id)">
            <strong>
              {{ task.title }}
            </strong>
            <small>
              {{ task.status }} · 修订 {{ task.revision ?? 0 }}
            </small>
          </button>
          <p v-if="!tasks.length" class="panel-note">
            此游戏知识库暂无任务。
          </p>
        </details>
      </section>
      <section class="souls-section">
        <h3>
          来源与版本情报
        </h3>
        <p class="panel-note">
          官方与社区 tier 是来源登记，不是事实保证。每条文章区分发布时间和抓取时间；抓取失败或无结果均不能视为当前最新。
        </p>
        <details>
          <summary>
            已登记来源 · {{ sources.length }}
          </summary>
          <div v-for="source in sources" :key="source.id" class="souls-source-row">
            <div>
              <a v-if="safeUrl(source.url)" :href="safeUrl(source.url)" target="_blank" rel="noopener noreferrer">
                {{ source.title }}
              </a>
              <strong v-else>
                {{ source.title }}
              </strong>
              <p class="panel-note">
                {{ source.kind }} · tier {{ source.tier }} · {{ source.edition || '版本未限定' }} · {{ text(source.notes) }}
              </p>
            </div>
            <span class="report-badge">
              {{ source.kind === 'official' || source.tier === 'official' ? '官方来源登记' : '社区 / 其他来源登记' }}
            </span>
          </div>
        </details>
        <form class="v2-form" @submit.prevent="fetchUpdates">
          <div class="v2-form-grid">
            <label>
              情报来源
              <select v-model="sourceId" required>
                <option value="">
                  选择来源
                </option>
                <option v-for="source in sources" :key="source.id" :value="source.id">
                  {{ source.title }} · {{ source.kind }} / {{ source.tier }}
                </option>
              </select>
            </label>
            <label>
              文章数量
              <input v-model="limit" type="number" min="1" max="50" />
            </label>
          </div>
          <el-button native-type="submit" :loading="busy === 'updates'" :disabled="!!busy || !sourceId">
            抓取明确文章
          </el-button>
        </form>
        <p v-if="feedError" class="v2-error" role="alert">
          {{ feedError }}
        </p>
        <div v-if="feedErrors.length" class="v2-warning" role="alert">
          <strong>
            部分来源抓取失败；以下列表不代表完整最新情报
          </strong>
          <p v-for="(item,index) in feedErrors" :key="index">
            {{ text(item) }}
          </p>
        </div>
        <p v-if="feedLoaded && !updates.length" class="panel-note">
          本次抓取没有返回可用文章；无法判断当前最新补丁。
        </p>
        <article v-for="item in updates" :key="`${item.source_id}:${item.external_id || item.url}`" class="souls-article">
          <div class="v2-heading">
            <div>
              <a v-if="safeUrl(item.url)" :href="safeUrl(item.url)" target="_blank" rel="noopener noreferrer">
                <h4>
                  {{ item.title }}
                </h4>
              </a>
              <h4 v-else>
                {{ item.title }}
              </h4>
              <p class="panel-note">
                {{ item.source_kind || '类型未知' }} · tier {{ item.source_tier ?? '未知' }} · {{ item.edition || '版本未知' }} · 补丁 {{ item.patch || '未知' }}
              </p>
            </div>
            <el-button :loading="busy === 'import'" :disabled="!!busy || !scoped || !item.source_id || (!item.external_id && !safeUrl(item.url))" @click="importArticle(item)">
              导入此文章
            </el-button>
          </div>
          <p class="panel-note">
            发布时间：{{ time(item.published_at) }}　抓取时间：{{ time(item.captured_at) }}
          </p>
          <details>
            <summary>
              原文与抓取溯源
            </summary>
            <pre class="evidence-content">
              {{ item.content || '未返回原文，不能据摘要断言结论' }}
            </pre>
            <pre class="v2-pre">
              {{ pretty({ source_id: item.source_id, external_id: item.external_id, content_sha256: item.content_sha256, provenance: item.provenance }) }}
            </pre>
          </details>
        </article>
        <div v-for="job in importJobs.filter(entry => entry.knowledge_base_id === knowledgeBase?.id && entry.game_id === gameId)" :key="job.import_id" class="history-row">
          <span>
            <strong>
              {{ job.title }}
            </strong>
            <small>
              {{ ({ queued: '排队中', running: '重新抓取与核验中', completed: '已完成', error: '导入失败' })[job.status] || job.status }} · 资料版本 {{ job.version_id || job.version?.id || '尚未完成' }}
              <template v-if="job.error">
                · {{ text(job.error) }}
              </template>
              <template v-if="job.poll_error">
                · {{ job.poll_error }}
              </template>
            </small>
          </span>
          <el-button :disabled="!!busy" @click="refreshImports">
            刷新导入状态
          </el-button>
        </div>
      </section>
      <section class="souls-section">
        <h3>
          补丁影响 · 可追溯候选关联
        </h3>
        <p class="panel-note">
          匹配显式补丁引用 / 实体关键词，不声称旧结论自动失效。由你回看原文并在 V2 指定章节补查。
        </p>
        <form class="v2-form" @submit.prevent="checkImpact">
          <div class="v2-form-grid">
            <label>
              补丁资料版本（可选）
              <select v-model="impactVersion">
                <option value="">
                  库内候选补丁资料
                </option>
                <option v-for="version in documentVersions" :key="version.id" :value="version.id">
                  {{ version.filename }} · {{ version.version_label || '未标版本' }}
                </option>
              </select>
            </label>
            <label>
              实体关键词（可选）
              <input v-model="impactQuery" placeholder="如武器、技能或首领名称" />
            </label>
          </div>
          <el-button native-type="submit" :loading="busy === 'impact'" :disabled="!!busy || !scoped">
            查找候选影响
          </el-button>
        </form>
        <template v-if="impact">
          <p v-for="(warning,index) in impact.warnings || []" :key="index" class="v2-warning">
            {{ text(warning) }}
          </p>
          <details>
            <summary>
              检索覆盖范围
            </summary>
            <pre class="v2-pre">
              {{ pretty(impact.coverage) }}
            </pre>
          </details>
          <div v-for="(change,index) in impact.changes || []" :key="index" class="souls-article">
            <strong>
              {{ change.entity }} · {{ text(change.change) }}
            </strong>
            <blockquote class="source-excerpt">
              {{ change.quote || '未提供引用，需补查' }}
            </blockquote>
            <p class="panel-note">
              来源 {{ change.source_id || '未知' }} · 资料版本 {{ change.version_id || '未知' }}
            </p>
            <a v-if="safeUrl(change.url)" :href="safeUrl(change.url)" target="_blank" rel="noopener noreferrer">
              查看变更原文
            </a>
          </div>
          <article v-for="task in impact.affected_tasks || []" :key="task.id" class="souls-article">
            <div class="v2-heading">
              <h4>
                {{ task.title }} · 修订 {{ task.revision }}
              </h4>
              <el-button @click="emit('open-task', task.id)">
                打开任务补查
              </el-button>
            </div>
            <div v-for="section in task.sections || []" :key="section.id">
              <strong>
                {{ section.title }}
              </strong>
              <p v-for="claim in section.claims || []" :key="claim.id" class="panel-note">
                待确认：{{ claim.text }}
                <br />
                关联原因：{{ text(claim.reason) }}
              </p>
            </div>
          </article>
          <p v-if="!impact.affected_tasks?.length" class="panel-note">
            没有匹配到候选任务，不表示所有旧结论均适用。
          </p>
        </template>
      </section>
      <section class="souls-section">
        <h3>
          透明计算工具
        </h3>
        <p class="panel-note">
          {{ isNightreign ? 'Nightreign 未建立属性预算或传统 max_load 负重模型，仅提供明确数值对照；不套用其他游戏机制。' : '提供属性点预算、负重加总与明确数值对照。' }}不计算真实伤害、耐力消耗或回避帧。缺少来源的数值明确为玩家输入。
        </p>
        <form class="v2-form" @submit.prevent="calculate">
          <label>
            运算
            <select v-model="operation">
              <option value="table_comparison">
                明确数值对照（差值 / 比值 / 百分比）
              </option>
              <option v-if="!isNightreign" value="loadout_weight">
                装备负重加总
              </option>
              <option v-if="!isNightreign" value="stat_budget">
                属性点预算
              </option>
            </select>
          </label>
          <template v-if="operation === 'table_comparison'">
            <label>
              明确数值 JSON
              <textarea v-model="comparisonJson" rows="6" spellcheck="false" />
            </label>
            <p class="panel-note">left、right 必须为明确数值，unit 可选。仅比较玩家输入的同单位数值，不推算伤害或未查证的游戏机制。</p>
          </template>
          <template v-else-if="operation === 'stat_budget' && !isNightreign">
            <p class="panel-note">
              目录属性：{{ statLabels || '目录未提供名称；按实际属性输入 JSON，不预置职业基值' }}
            </p>
            <label>
              预算数据 JSON
              <textarea v-model="statsJson" rows="8" spellcheck="false" />
            </label>
            <p class="panel-note">
              契约：starting_stats、target_stats 为属性名到数值的对象；starting_level、budget 为可选数字。
            </p>
          </template>
          <template v-else>
            <div v-for="(row,index) in weightRows" :key="index" class="souls-weight-row">
              <label>
                装备名称
                <input v-model="row.name" />
              </label>
              <label>
                重量（玩家输入）
                <input v-model="row.weight" type="number" min="0" step="any" />
              </label>
              <label>
                来源 ID（可选）
                <input v-model="row.source_id" />
              </label>
              <label>
                原文引文（可选）
                <input v-model="row.quote" />
              </label>
              <el-button :disabled="weightRows.length === 1" @click="weightRows.splice(index,1)">
                删除第 {{ index + 1 }} 行
              </el-button>
            </div>
            <el-button @click="weightRows.push({ name: '', weight: '', source_id: '', quote: '' })">
              添加装备
            </el-button>
            <label>
              最大负重（玩家实际输入）
              <input v-model="maxLoad" type="number" min="0" step="any" required />
            </label>
            <details>
              <summary>
                自定义阈值 JSON（可选）
              </summary>
              <label>
                thresholds
                <textarea v-model="thresholdsJson" rows="4" spellcheck="false" />
              </label>
              <p class="panel-note">
                空数组仅算负重百分比，不预设游戏阈值。自定义格式：[{"label":"名称","max_percent":数值,"inclusive":true}]；不把玩家阈值当作已验证机制。
              </p>
            </details>
          </template>
          <el-button native-type="submit" :loading="busy === 'calculate'" :disabled="!!busy">
            计算并展示公式
          </el-button>
        </form>
        <div v-if="calculation" aria-live="polite">
          <h4>
            计算结果
          </h4>
          <p v-if="calculation.status === 'not_applicable'" class="v2-warning">此运算不适用于该游戏，不套用其他游戏机制。</p>
          <pre class="v2-pre">
            {{ pretty(calculation.result) }}
          </pre>
          <p v-for="(warning,index) in calculation.warnings || []" :key="index" class="v2-warning">
            {{ text(warning) }}
          </p>
          <details open>
            <summary>
              公式 · 输入 · 来源
            </summary>
            <pre class="v2-pre">
              {{ pretty({ formula: calculation.formula, inputs: calculation.inputs, sources: calculation.sources }) }}
            </pre>
          </details>
        </div>
      </section>
    </template>
  </div>
</template>
