<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  CircleCheck,
  DataAnalysis,
  Document,
  DocumentAdd,
  InfoFilled,
  Plus,
  Promotion,
  Refresh,
  WarningFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const apiBase = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
// A long-lived backend key must never ship in a production browser bundle.
// Local development may use VITE_API_KEY; production should use same-origin
// HttpOnly auth or have the reverse proxy inject X-API-Key server-side.
const apiKey = import.meta.env.DEV ? (import.meta.env.VITE_API_KEY || '') : ''
const RETRIEVAL_METHODS = [
  { id: 'vector', label: '向量', short: 'Vector' },
  { id: 'bm25', label: 'BM25', short: 'BM25' },
  { id: 'rrf', label: 'RRF', short: 'RRF' },
  { id: 'rerank', label: 'Rerank', short: 'Rerank' },
]
const UPLOAD_STAGES = ['queued', 'parsing', 'chunking', 'embedding', 'persisting', 'ready']
const STAGE_LABELS = {
  queued: '排队中',
  parsing: '解析资料',
  chunking: '切分片段',
  embedding: '生成向量',
  persisting: '写入索引',
  ready: '可检索',
  error: '索引失败',
}

const conversations = ref([])
const messages = ref([])
const documents = ref([])
const uploadJobs = ref([])
const currentConversationId = ref(null)
const input = ref('')
const isSending = ref(false)
const isUploading = ref(false)
const isSelectingConversation = ref(false)
const fileInput = ref(null)
const messageList = ref(null)
const composerArea = ref(null)
let composerObserver = null
let activeReader = null
const selectedSource = ref(null)
const sourceDrawerOpen = ref(false)
const health = ref(null)
const healthError = ref('')
const conversationError = ref('')
const connectionError = computed(() => healthError.value || conversationError.value)
const viewMode = ref('chat')
const evaluation = reactive({ status: 'idle', dataset: null, report: null, error: '', warning: '' })
let disposed = false
let conversationSelectionSequence = 0

const activeConversation = computed(() => conversations.value.find((item) => item.id === currentConversationId.value))
const knowledgeCount = computed(() => documents.value.reduce((total, item) => total + (item.chunk_count || 0), 0))
const activeUpload = computed(() => {
  const current = uploadJobs.value.filter((job) => job.conversation_id === currentConversationId.value)
  return current.find((job) => ['queued', 'processing'].includes(job.status)) || current[0] || null
})
const latestAssistant = computed(() => [...messages.value].reverse().find((message) => message.role === 'assistant'))
const latestTrace = computed(() => latestAssistant.value?.retrievalTrace || null)
const serviceLabel = computed(() => {
  if (connectionError.value) return '服务不可用'
  if (!health.value) return '正在检查服务'
  return health.value.status === 'ready' ? '服务就绪' : '待配置模型或数据库'
})
const serviceTagType = computed(() => (health.value?.status === 'ready' ? 'success' : connectionError.value ? 'danger' : 'warning'))
const evaluationCutoffs = computed(() => evaluation.report?.run?.cutoffs || [1, 3, 5, 10])
const evaluationSummaryRows = computed(() => {
  const summary = evaluation.report?.summary || {}
  const cases = evaluation.report?.cases || []
  const activeMethods = evaluation.report?.run?.variants || RETRIEVAL_METHODS.map((method) => method.id)
  return RETRIEVAL_METHODS.filter((method) => activeMethods.includes(method.id)).map((method) => {
    const fallbackCount = cases.filter((item) => {
      const trace = item.strategies?.[method.id]?.trace
      return trace?.status === 'fallback' && trace.effective_method === 'rrf'
    }).length
    const failedCount = cases.filter((item) => item.strategies?.[method.id]?.trace?.status === 'failed').length
    return {
      ...method,
      values: summary[method.id] || {},
      fallbackCount,
      failedCount,
    }
  })
})
const evaluationCaseRows = computed(() => {
  const cases = evaluation.report?.cases || []
  const priority = ['rerank', 'rrf', 'vector', 'bm25']
  return cases.slice(0, 10).map((item) => {
    const entries = Object.entries(item.strategies || {})
    const usable = entries.filter(([, strategy]) => strategy?.trace?.status !== 'failed' && (strategy?.retrieved_chunk_ids || []).length > 0)
    const selected = priority.map((method) => usable.find(([id]) => id === method)).find(Boolean) || entries.find(([, strategy]) => strategy?.trace?.status !== 'failed') || entries[0]
    const [requestedMethod, strategy] = selected || [null, null]
    const trace = strategy?.trace || null
    const lastCutoff = String(evaluationCutoffs.value[evaluationCutoffs.value.length - 1])
    return {
      id: item.id,
      query: item.query,
      method: methodLabel(requestedMethod),
      effectiveMethod: trace?.effective_method || requestedMethod || 'none',
      fallbackReason: trace?.fallback_reason || null,
      retrieved: strategy?.retrieved_chunk_ids || [],
      metrics: strategy?.metrics?.[lastCutoff] || {},
      trace,
    }
  })
})

function endpoint(path) {
  return `${apiBase}${path}`
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (apiKey) headers.set('X-API-Key', apiKey)
  const response = await fetch(endpoint(path), { ...options, headers })
  if (response.ok) return response
  let detail = `请求失败 (${response.status})`
  let payload = null
  try {
    payload = await response.json()
    const rawDetail = payload.detail || payload.message
    detail = typeof rawDetail === 'string' ? rawDetail : rawDetail?.message || detail
  } catch {
    // Non-JSON errors still receive a useful status message.
  }
  const errorDetails = payload?.detail && typeof payload.detail === 'object' ? payload.detail : payload
  const error = new Error(detail)
  error.status = response.status
  error.code = errorDetails?.code || ''
  error.retryable = errorDetails?.retryable ?? response.status >= 500
  throw error
}

async function scrollToBottom() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

async function loadHealth() {
  try {
    health.value = await (await request('/health')).json()
    healthError.value = ''
  } catch (error) {
    healthError.value = error.message
  }
}

async function loadConversations() {
  try {
    conversations.value = await (await request('/conversations')).json()
    conversationError.value = ''
  } catch (error) {
    conversationError.value = error.message
  }
}

async function loadEvaluation() {
  evaluation.status = 'loading'
  evaluation.error = ''
  evaluation.warning = ''
  evaluation.dataset = null
  evaluation.report = null
  try {
    const payload = await (await request('/evaluations/retrieval/latest')).json()
    evaluation.status = payload.status
    evaluation.dataset = payload.dataset
    evaluation.report = payload.status === 'completed' ? payload.report : null
    evaluation.warning = payload.warning || ''
  } catch (error) {
    evaluation.status = 'error'
    evaluation.error = error.message
    evaluation.report = null
  }
}

async function loadUploadJobs(conversationId, selection = null) {
  try {
    const jobs = await (await request(`/uploads?conversation_id=${encodeURIComponent(conversationId)}`)).json()
    if (selection === null || selection === conversationSelectionSequence) uploadJobs.value = jobs
  } catch {
    // Upload status is best-effort; the document list remains authoritative.
  }
}

async function createConversation() {
  try {
    const response = await request('/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: '未命名知识库' }),
    })
    const conversation = await response.json()
    await loadConversations()
    await selectConversation(conversation.id, true)
  } catch (error) {
    ElMessage.error(error.message)
  }
}

async function selectConversation(conversationId, force = false) {
  if (!force && conversationId === currentConversationId.value) return
  const selection = ++conversationSelectionSequence
  isSelectingConversation.value = true
  currentConversationId.value = conversationId
  messages.value = []
  documents.value = []
  uploadJobs.value = []
  selectedSource.value = null
  sourceDrawerOpen.value = false
  try {
    const [messageResponse, documentResponse] = await Promise.all([
      request(`/conversations/${conversationId}/messages`),
      request(`/conversations/${conversationId}/documents`),
    ])
    if (selection !== conversationSelectionSequence) return
    messages.value = await messageResponse.json()
    documents.value = await documentResponse.json()
    await loadUploadJobs(conversationId, selection)
    if (selection === conversationSelectionSequence) await scrollToBottom()
  } catch (error) {
    if (selection === conversationSelectionSequence) ElMessage.error(error.message)
  } finally {
    if (selection === conversationSelectionSequence) isSelectingConversation.value = false
  }
}

function sourceLocation(source) {
  if (source.start_line) return `第 ${source.start_line}-${source.end_line || source.start_line} 行`
  if (source.page_number) return `第 ${source.page_number} 页`
  if (source.chunk_index !== null && source.chunk_index !== undefined) return `片段 ${source.chunk_index + 1}`
  return '已索引片段'
}

function sourceById(message, sourceId) {
  return message.sources?.find((source) => source.id === sourceId) || null
}

function openSource(source) {
  selectedSource.value = source
  sourceDrawerOpen.value = true
}

function openMessageSource(message, sourceId) {
  const source = sourceById(message, sourceId)
  if (source) openSource(source)
}

function citationSegments(text) {
  const segments = []
  const pattern = /\[S\d+\]/g
  let cursor = 0
  let match
  while ((match = pattern.exec(text || ''))) {
    if (match.index > cursor) segments.push({ text: text.slice(cursor, match.index), citation: false })
    segments.push({ text: match[0], citation: true, id: match[0].slice(1, -1) })
    cursor = match.index + match[0].length
  }
  if (cursor < (text || '').length) segments.push({ text: text.slice(cursor), citation: false })
  return segments.length ? segments : [{ text: text || '', citation: false }]
}

function citationStatus(message) {
  if (message.citationValidation?.status) return message.citationValidation.status
  return message.role === 'assistant' && isSending.value && message === messages.value[messages.value.length - 1] ? 'checking' : 'unknown'
}

function citationLabel(status) {
  return {
    checking: '正在校验引用',
    valid: '结构校验通过',
    missing: '缺少引用编号',
    invalid: '存在未匹配引用',
    no_sources: '没有可引用证据',
    generation_failed: '生成失败，未校验',
    unknown: '未记录校验结果',
  }[status] || '引用状态未知'
}

function citationDetail(message, status) {
  const validation = message.citationValidation || {}
  if (status === 'valid') return `${validation.cited_source_count || 0}/${validation.source_count || 0} 个来源被回答引用`
  if (status === 'invalid') return `未知编号：${validation.unknown_ids?.join('、') || '未提供'}`
  if (status === 'missing') return '回答没有检测到 [S#] 来源编号，请回看下方证据。'
  if (status === 'no_sources') return '本次回答没有使用外部资料，不能视为有证据支持。'
  if (status === 'generation_failed') return '模型未完成回答，本次没有进行结构校验。'
  return '引用完整性只校验编号映射，不证明语义事实正确。'
}

function citationClass(status) {
  if (status === 'valid') return 'success'
  if (['invalid', 'missing', 'generation_failed'].includes(status)) return 'danger'
  if (status === 'no_sources') return 'warning'
  return 'neutral'
}

function isSourceCited(message, source) {
  return Boolean(message.citationValidation?.cited_ids?.includes(source.id))
}

function stageEntries(trace) {
  return Object.entries(trace?.stages || {})
}

function stageLabel(stage) {
  return {
    collection: '知识库',
    rewrite: '查询改写',
    vector: '向量召回',
    bm25: 'BM25 召回',
    rrf: 'RRF 融合',
    rerank: 'Cross-Encoder 重排',
  }[stage] || stage
}

function methodLabel(method) {
  return RETRIEVAL_METHODS.find((item) => item.id === method)?.label || method || '无'
}

function traceLabel(trace) {
  if (!trace) return '未记录轨迹'
  if (trace.status === 'fallback') return `已降级 · ${methodLabel(trace.effective_method)}`
  if (trace.status === 'failed') return '检索失败'
  if (trace.status === 'empty') return '无可用证据'
  return methodLabel(trace.effective_method)
}

function traceReason(reason) {
  return {
    partial_candidate_failure: '部分候选召回失败，使用仍可用的结果。',
    reranker_not_configured: '未配置 Cross-Encoder，使用 RRF 排序。',
    reranker_load_failed: 'Cross-Encoder 加载失败，使用 RRF 排序。',
    reranker_inference_failed: 'Cross-Encoder 推理失败，使用 RRF 排序。',
    reranker_backoff: 'Cross-Encoder 处于退避窗口，使用 RRF 排序。',
    knowledge_base_empty: '知识库还没有已索引资料。',
    query_rewrite_timeout: '查询改写超时，已使用原问题检索。',
    query_rewrite_failed: '查询改写失败，已使用原问题检索。',
  }[reason] || reason || '未提供降级原因。'
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  const difference = Date.now() - date.getTime()
  if (difference < 60_000) return '刚刚更新'
  if (difference < 3_600_000) return `${Math.floor(difference / 60_000)} 分钟前`
  if (difference < 86_400_000) return `${Math.floor(difference / 3_600_000)} 小时前`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function formatBytes(value) {
  if (!value && value !== 0) return '大小未知'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function formatMetric(value) {
  return typeof value === 'number' ? value.toFixed(3) : '—'
}

function formatPercent(value) {
  return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—'
}

function uploadStageState(job, stage) {
  if (!job) return 'pending'
  const failedStage = job.failed_stage || job.stage
  if (job.status === 'failed') {
    const failedIndex = UPLOAD_STAGES.indexOf(failedStage)
    const stageIndex = UPLOAD_STAGES.indexOf(stage)
    if (stage === failedStage) return 'error'
    if (failedIndex >= 0 && stageIndex < failedIndex) return 'done'
    return 'pending'
  }
  const currentIndex = Number(job.stage_index || 0)
  const stageIndex = UPLOAD_STAGES.indexOf(stage)
  if (stage === job.stage) return 'current'
  return stageIndex < currentIndex ? 'done' : 'pending'
}

function upsertUpload(task) {
  const index = uploadJobs.value.findIndex((item) => item.id === task.id)
  if (index < 0) uploadJobs.value.unshift(task)
  else uploadJobs.value[index] = { ...uploadJobs.value[index], ...task }
}

function sleep(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

function triggerUpload() {
  fileInput.value?.click()
}

async function refreshUpload(uploadId) {
  try {
    const task = await (await request(`/uploads/${uploadId}`)).json()
    upsertUpload(task)
  } catch (error) {
    ElMessage.error(error.message)
  }
}

async function handleUpload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || !currentConversationId.value) return

  const uploadConversationId = currentConversationId.value
  const uploadSelection = conversationSelectionSequence
  const formData = new FormData()
  formData.append('file', file)
  formData.append('conversation_id', uploadConversationId)
  isUploading.value = true
  let uploaded = null
  let pollingStarted = false
  try {
    uploaded = await (await request('/uploads', { method: 'POST', body: formData })).json()
    upsertUpload({
      ...uploaded,
      id: uploaded.upload_id,
      conversation_id: uploadConversationId,
      filename: file.name,
      size: file.size,
      status: 'queued',
      stage: 'queued',
      stage_label: '等待索引',
      stage_index: 0,
      stage_total: 5,
      progress: null,
      error: null,
    })
    ElMessage.success(`${uploaded.filename} 已进入索引队列`)
    pollingStarted = true
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await sleep(1000)
      try {
        const task = await (await request(`/uploads/${uploaded.upload_id}`)).json()
        upsertUpload(task)
        if (task.status === 'completed') {
          if (currentConversationId.value === uploadConversationId && conversationSelectionSequence === uploadSelection) {
            const refreshedDocuments = await (await request(`/conversations/${uploadConversationId}/documents`)).json()
            if (currentConversationId.value === uploadConversationId && conversationSelectionSequence === uploadSelection) {
              documents.value = refreshedDocuments
              await loadUploadJobs(uploadConversationId, uploadSelection)
            }
          }
          ElMessage.success(`${task.filename} 已索引 ${task.chunk_count} 个片段`)
          return
        }
        if (task.status === 'failed') {
          upsertUpload(task)
          ElMessage.error(task.error || '文档索引失败')
          return
        }
      } catch (error) {
        if (error.status === 404) {
          upsertUpload({ id: uploaded.upload_id, status: 'unknown', stage: 'error', stage_label: '状态不可恢复', error: '服务端已不再保留该任务状态。', retryable: true })
          return
        }
        upsertUpload({ id: uploaded.upload_id, status: 'unknown', stage: 'error', stage_label: '状态读取失败', error: '暂时无法读取任务状态，请稍后刷新。', retryable: true })
        return
      }
    }
    throw new Error('索引等待超时，请刷新任务状态')
  } catch (error) {
    if (uploaded?.upload_id) {
      upsertUpload({
        id: uploaded.upload_id,
        status: pollingStarted ? 'unknown' : 'failed',
        stage: 'error',
        stage_label: pollingStarted ? '状态未知' : '上传失败',
        error: pollingStarted ? '任务轮询超时或状态读取中断，请刷新确认。' : error.message,
        retryable: true,
      })
    } else {
      upsertUpload({
        id: `client-${crypto.randomUUID()}`,
        conversation_id: uploadConversationId,
        filename: file.name,
        size: file.size,
        status: 'failed',
        stage: 'error',
        failed_stage: 'queued',
        stage_label: '上传失败',
        error: error.message,
        retryable: error.retryable !== false,
      })
    }
    ElMessage.error(error.message)
  } finally {
    isUploading.value = false
  }
}

function syncComposerSpace() {
  if (!messageList.value || !composerArea.value) return
  const measured = Math.ceil(composerArea.value.getBoundingClientRect().height) + 24
  messageList.value.style.setProperty('--composer-space', `${measured}px`)
}

async function sendMessage() {
  const question = input.value.trim()
  if (!question || isSending.value || isSelectingConversation.value) return
  if (!currentConversationId.value) {
    ElMessage.warning('请先创建知识库会话')
    return
  }
  const conversationIdAtSend = currentConversationId.value

  const userMessage = { id: `user-${crypto.randomUUID()}`, role: 'user', parts: [{ type: 'text', text: question }] }
  const assistantMessage = reactive({
    id: `assistant-${crypto.randomUUID()}`,
    role: 'assistant',
    parts: [{ type: 'text', text: '' }],
    sources: [],
    citationValidation: { status: 'checking' },
    retrievalTrace: null,
  })
  messages.value.push(userMessage, assistantMessage)
  const messagePayload = JSON.parse(JSON.stringify(messages.value))
  input.value = ''
  isSending.value = true
  await scrollToBottom()

  try {
    const response = await request(`/chat/${conversationIdAtSend}`,  {
      method: 'POST',
      headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: messagePayload }),
    })
    if (!response.body) throw new Error('浏览器不支持流式响应')
    const contentType = response.headers.get('content-type') || ''
    if (!contentType.includes('text/event-stream')) throw new Error('服务返回的不是流式响应')

    const reader = response.body.getReader()
    activeReader = reader
    const decoder = new TextDecoder()
    let buffer = ''
    const streamState = { finished: false, citationReceived: false, doneMarker: false, parseError: false }

    const consumeEvent = (eventText) => {
      const data = eventText
        .split(/\r?\n/)
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
        .trim()
      if (!data) return
      if (data === '[DONE]') {
        streamState.doneMarker = true
        return
      }
      let event
      try {
        event = JSON.parse(data)
      } catch {
        streamState.parseError = true
        return
      }
      if (event.type === 'text-delta') assistantMessage.parts[0].text += event.delta || ''
      if (event.type === 'data-sources') assistantMessage.sources = event.data || []
      if (event.type === 'retrieval-trace') assistantMessage.retrievalTrace = event.data
      if (event.type === 'citation-validation') {
        assistantMessage.citationValidation = event.data
        streamState.citationReceived = true
      }
      if (event.type === 'error') assistantMessage.parts[0].text += `\n\n${event.errorText || '流式生成失败'}`
      if (event.type === 'finish') streamState.finished = true
    }

    while (!disposed && !streamState.doneMarker) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const eventText = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        consumeEvent(eventText)
        boundary = buffer.indexOf('\n\n')
        await scrollToBottom()
      }
    }
    buffer += decoder.decode()
    buffer = buffer.replace(/\r\n/g, '\n')
    if (buffer.trim()) consumeEvent(buffer)
    if (!disposed && (streamState.parseError || !streamState.finished || !streamState.citationReceived)) {
      assistantMessage.parts[0].text += assistantMessage.parts[0].text ? '\n\n' : ''
      assistantMessage.parts[0].text += streamState.parseError ? '流式事件无法解析，请重试以获得完整引用校验。' : '流式响应未完整结束，请重试以获得完整引用校验。'
      assistantMessage.retrievalTrace = {
        ...(assistantMessage.retrievalTrace || {}),
        status: 'failed',
        fallback_reason: streamState.parseError ? 'malformed_stream' : 'incomplete_stream',
        errors: [...(assistantMessage.retrievalTrace?.errors || []), streamState.parseError ? 'malformed_stream' : 'incomplete_stream'],
      }
      assistantMessage.citationValidation = { status: 'generation_failed', warnings: [streamState.parseError ? '流式事件无法解析' : '流式响应未完整结束'] }
    }
    await loadConversations()
  } catch (error) {
    assistantMessage.parts[0].text = `请求失败：${error.message}`
    assistantMessage.retrievalTrace = assistantMessage.retrievalTrace || {
      status: 'failed',
      effective_method: 'none',
      fallback_reason: 'request_failed',
      errors: [error.code || 'request_failed'],
    }
    assistantMessage.citationValidation = { status: 'generation_failed', warnings: ['请求未完成'] }
  } finally {
    activeReader = null
    isSending.value = false
    await scrollToBottom()
  }
}

function observeComposerArea() {
  composerObserver?.disconnect()
  composerObserver = null
  nextTick(() => {
    syncComposerSpace()
    if (typeof ResizeObserver !== 'undefined' && composerArea.value) {
      composerObserver = new ResizeObserver(syncComposerSpace)
      composerObserver.observe(composerArea.value)
    }
  })
}

watch(viewMode, observeComposerArea)

onMounted(async () => {
  observeComposerArea()
  await Promise.all([loadHealth(), loadConversations(), loadEvaluation()])
  if (conversations.value.length) await selectConversation(conversations.value[0].id)
})
onBeforeUnmount(() => {
  disposed = true
  activeReader?.cancel()
  composerObserver?.disconnect()
})
</script>

<template>
  <main class="app-shell">
    <aside class="sidebar" aria-label="知识库导航">
      <div class="brand-lockup">
        <span class="brand-mark" aria-hidden="true"><el-icon><Document /></el-icon></span>
        <span>
          <strong>Evidence RAG</strong>
          <small>可评测 · 可追溯</small>
        </span>
      </div>

      <el-button class="new-space-button" type="primary" :icon="Plus" :disabled="isSending || isSelectingConversation" @click="createConversation">新建知识库</el-button>

      <nav class="conversation-nav" aria-label="历史知识库">
        <p class="nav-label">最近知识库</p>
        <button
          v-for="conversation in conversations"
          :key="conversation.id"
          class="conversation-item"
          :class="{ active: conversation.id === currentConversationId }"
          type="button"
          :disabled="isSending || isSelectingConversation"
          @click="selectConversation(conversation.id)"
        >
          <el-icon aria-hidden="true"><Document /></el-icon>
          <span class="conversation-copy">
            <strong>{{ conversation.title }}</strong>
            <small>{{ formatTime(conversation.updated_at) }}</small>
          </span>
        </button>
        <p v-if="!conversations.length" class="empty-nav">创建知识库，上传资料后开始问答。</p>
      </nav>

      <button class="evaluation-nav" :class="{ active: viewMode === 'evaluation' }" type="button" @click="viewMode = 'evaluation'">
        <el-icon aria-hidden="true"><DataAnalysis /></el-icon>
        <span><strong>离线评测</strong><small>四路检索 · 真实标注</small></span>
      </button>

      <section class="service-card" :class="serviceTagType">
        <span class="service-indicator" aria-hidden="true"></span>
        <div>
          <strong>{{ serviceLabel }}</strong>
          <small v-if="connectionError">{{ connectionError }}</small>
          <small v-else>健康检查不会加载本地模型</small>
        </div>
      </section>
    </aside>

    <section class="workspace">
      <header class="workspace-header">
        <div>
          <p class="eyebrow">{{ viewMode === 'chat' ? '知识库工作台' : '检索质量实验室' }}</p>
          <h1>{{ viewMode === 'chat' ? (activeConversation?.title || '选择或创建知识库') : '检索评测结果' }}</h1>
        </div>
        <div class="header-actions">
          <div class="view-tabs" role="tablist" aria-label="工作台视图">
            <button type="button" :class="{ active: viewMode === 'chat' }" role="tab" :aria-selected="viewMode === 'chat'" @click="viewMode = 'chat'">问答</button>
            <button type="button" :class="{ active: viewMode === 'evaluation' }" role="tab" :aria-selected="viewMode === 'evaluation'" @click="viewMode = 'evaluation'">评测</button>
          </div>
          <el-tag :type="serviceTagType" effect="plain" round>{{ serviceLabel }}</el-tag>
        </div>
      </header>

      <template v-if="viewMode === 'chat'">
        <section class="knowledge-strip" aria-label="当前知识库状态">
          <div class="metric">
            <span>资料</span>
            <strong>{{ documents.length }}</strong>
            <small>{{ knowledgeCount }} 个已索引片段</small>
          </div>
          <div class="metric">
            <span>当前检索</span>
            <strong>{{ latestTrace ? methodLabel(latestTrace.effective_method) : 'Hybrid' }}</strong>
            <small>{{ latestTrace ? traceLabel(latestTrace) : '向量 + BM25 + RRF' }}</small>
          </div>
          <div class="metric metric-action">
            <span>添加资料</span>
            <el-button :icon="DocumentAdd" plain :loading="isUploading" :disabled="isSending || isSelectingConversation || !currentConversationId" @click="triggerUpload">上传文档</el-button>
          </div>
        </section>

        <section v-if="activeUpload" class="pipeline-card" :class="activeUpload.status" aria-live="polite">
          <div class="pipeline-heading">
            <div>
              <p class="eyebrow">索引链路</p>
              <strong>{{ activeUpload.filename }}</strong>
              <small>{{ formatBytes(activeUpload.size) }} · {{ activeUpload.stage_label || STAGE_LABELS[activeUpload.stage] || activeUpload.status }}</small>
            </div>
            <el-tag :type="activeUpload.status === 'completed' ? 'success' : activeUpload.status === 'failed' ? 'danger' : 'warning'" effect="plain">
              {{ activeUpload.status === 'completed' ? '已完成' : activeUpload.status === 'failed' ? '失败' : activeUpload.status === 'unknown' ? '状态未知' : '处理中' }}
            </el-tag>
          </div>
          <ol class="pipeline-steps" aria-label="索引阶段">
            <li v-for="stage in UPLOAD_STAGES" :key="stage" :class="uploadStageState(activeUpload, stage)">
              <span class="pipeline-dot" aria-hidden="true"></span>
              <span>{{ STAGE_LABELS[stage] }}</span>
            </li>
          </ol>
          <div class="pipeline-footer">
            <span v-if="activeUpload.chunk_count">已建立 {{ activeUpload.chunk_count }} 个片段</span>
            <span v-else-if="activeUpload.error">{{ activeUpload.error }}</span>
            <span v-else>阶段 {{ activeUpload.stage_index || 0 }}/{{ activeUpload.stage_total || 5 }} · 不虚报处理中百分比</span>
            <el-button v-if="activeUpload.status === 'unknown' || activeUpload.status === 'failed'" text :icon="Refresh" @click="refreshUpload(activeUpload.id)">刷新状态</el-button>
          </div>
        </section>

        <section ref="messageList" class="message-list" aria-live="polite" :aria-busy="isSending">
          <div v-if="!messages.length" class="empty-workspace">
            <div class="empty-icon" aria-hidden="true"><el-icon><DocumentAdd /></el-icon></div>
            <p class="eyebrow">Evidence first</p>
            <h2>先建立证据，再生成答案</h2>
            <p>上传资料后，系统会记录解析、切分、向量写入和来源定位；回答中的每个 [S#] 都能回到实际证据。</p>
            <el-button type="primary" :icon="DocumentAdd" :disabled="isSending || isSelectingConversation || !currentConversationId" @click="triggerUpload">上传第一份资料</el-button>
            <div class="capability-grid">
              <div><strong>四路检索评测</strong><span>Vector / BM25 / RRF / Rerank 在同一标注集上对比</span></div>
              <div><strong>引用结构校验</strong><span>校验来源编号，不把结构检查冒充事实证明</span></div>
              <div><strong>失败可解释</strong><span>检索降级与索引阶段都留下可回看的轨迹</span></div>
            </div>
          </div>

          <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
            <div v-if="message.role === 'assistant'" class="message-avatar" aria-hidden="true"><el-icon><Document /></el-icon></div>
            <div class="message-content">
              <div class="message-meta">{{ message.role === 'assistant' ? 'Evidence RAG' : '你' }}</div>
              <div class="message-bubble">
                <template v-if="message.role === 'assistant'">
                  <template v-for="(segment, index) in citationSegments(message.parts?.[0]?.text || (isSending ? '正在整理证据…' : ''))" :key="`${message.id}-${index}`">
                    <button v-if="segment.citation && sourceById(message, segment.id)" class="inline-citation" type="button" @click="openMessageSource(message, segment.id)">{{ segment.text }}</button>
                    <span v-else>{{ segment.text }}</span>
                  </template>
                </template>
                <template v-else>{{ message.parts?.[0]?.text }}</template>
              </div>

              <section v-if="message.role === 'assistant' && message.retrievalTrace" class="trace-card" :class="message.retrievalTrace.status">
                <div class="trace-heading">
                  <div>
                    <span class="trace-kicker">检索轨迹</span>
                    <strong>{{ traceLabel(message.retrievalTrace) }}</strong>
                  </div>
                  <span class="trace-count">{{ message.retrievalTrace.result_count || 0 }} 个证据</span>
                </div>
                <p v-if="message.retrievalTrace.fallback_reason" class="trace-reason">{{ traceReason(message.retrievalTrace.fallback_reason) }}</p>
                <details class="trace-details">
                  <summary>查看阶段与降级原因</summary>
                  <div class="trace-meta"><span>候选 {{ message.retrievalTrace.candidate_count || 0 }}</span><span>耗时 {{ message.retrievalTrace.duration_ms || 0 }} ms</span><span>查询 {{ message.retrievalTrace.retrieval_query || '原问题' }}</span></div>
                  <div class="stage-list">
                    <div v-for="([stage, detail]) in stageEntries(message.retrievalTrace)" :key="stage" class="stage-row">
                      <span>{{ stageLabel(stage) }}</span><span>{{ detail.status }} · {{ detail.count || 0 }} · {{ detail.duration_ms || 0 }}ms</span>
                    </div>
                  </div>
                </details>
              </section>

              <section v-if="message.role === 'assistant' && message.citationValidation" class="citation-audit" :class="citationClass(citationStatus(message))" aria-live="polite">
                <el-icon aria-hidden="true"><CircleCheck v-if="citationStatus(message) === 'valid'" /><WarningFilled v-else /></el-icon>
                <div>
                  <strong>{{ citationLabel(citationStatus(message)) }}</strong>
                  <small>{{ citationDetail(message, citationStatus(message)) }}</small>
                </div>
              </section>

              <el-collapse v-if="message.role === 'assistant' && message.sources?.length" class="source-collapse">
                <el-collapse-item name="sources">
                  <template #title>证据来源 · {{ message.sources.length }} <span class="collapse-hint">已引用 {{ message.citationValidation?.cited_source_count || 0 }}</span></template>
                  <button v-for="source in message.sources" :key="source.id" type="button" class="source-row" :class="{ cited: isSourceCited(message, source) }" @click="openSource(source)">
                    <span class="source-id">{{ source.id }}</span>
                    <span class="source-copy"><strong>{{ source.filename }}</strong><small>{{ sourceLocation(source) }} · {{ source.retrieval_method || '未提供策略' }}</small></span>
                    <span class="source-state">{{ isSourceCited(message, source) ? '已引用' : '候选' }}</span>
                  </button>
                </el-collapse-item>
              </el-collapse>
            </div>
          </article>
        </section>

        <footer ref="composerArea" class="composer-area">
          <form class="composer" @submit.prevent="sendMessage">
            <label class="sr-only" for="question">向知识库提问</label>
            <el-input id="question" v-model="input" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" resize="none" placeholder="例如：这份方案的风险与待确认事项是什么？" :disabled="isSending || isSelectingConversation || !currentConversationId" @keydown.enter.exact.prevent="sendMessage" />
            <div class="composer-actions">
              <div><el-button text :icon="DocumentAdd" :loading="isUploading" :disabled="isSending || isSelectingConversation || !currentConversationId" @click="triggerUpload">添加资料</el-button></div>
              <el-button native-type="submit" type="primary" :icon="Promotion" :loading="isSending" :disabled="!input.trim() || isSelectingConversation || !currentConversationId">发送</el-button>
            </div>
          </form>
          <p>回答基于已上传资料生成；引用校验只验证编号，重要信息请回看原文。</p>
        </footer>
      </template>

      <section v-else class="evaluation-view" aria-labelledby="evaluation-title">
        <div class="evaluation-intro">
          <div>
            <p class="eyebrow">Retrieval-only benchmark</p>
            <h2 id="evaluation-title">同一批标注问题，比较四种排序路径</h2>
            <p>不调用 LLM，不把聊天回答的主观质量混进排序指标。每次运行都记录数据集 fingerprint、片段粒度、切点与模型配置。</p>
          </div>
          <el-button :icon="Refresh" :loading="evaluation.status === 'loading'" @click="loadEvaluation">刷新结果</el-button>
        </div>

        <section v-if="evaluation.dataset" class="dataset-card">
          <div><span>数据集</span><strong>{{ evaluation.dataset.id }} · v{{ evaluation.dataset.version }}</strong></div>
          <div><span>问题数</span><strong>{{ evaluation.dataset.queries }}</strong></div>
          <div><span>Fingerprint</span><strong class="mono">{{ evaluation.dataset.fingerprint }}</strong></div>
          <div><span>标注单位</span><strong>{{ evaluation.dataset.judgment_unit }} · exhaustive {{ evaluation.dataset.qrels_exhaustive ? '是' : '否' }}</strong></div>
        </section>

        <el-alert v-if="evaluation.status === 'error'" type="warning" :closable="false" show-icon>
          评测结果接口暂不可用：{{ evaluation.error }}
        </el-alert>
        <el-alert v-else-if="['stale', 'invalid', 'incomplete'].includes(evaluation.status)" type="warning" :closable="false" show-icon>
          {{ evaluation.warning || '最新评测报告未通过完整性校验，已拒绝展示。' }}
        </el-alert>
        <section v-else-if="evaluation.status === 'not_run'" class="not-run-card">
          <el-icon aria-hidden="true"><DataAnalysis /></el-icon>
          <div><strong>暂无真实评测结果</strong><p>先索引固定 benchmark corpus，再执行下面的命令；页面不会展示虚构百分比。</p></div>
          <code>py -3 scripts/evaluate_retrieval.py evaluation/dataset.json --cutoffs 1,3,5,10 --output evaluation/runs/latest.json</code>
        </section>

        <template v-if="evaluation.report">
          <section class="metric-grid" aria-label="评测汇总">
            <article v-for="row in evaluationSummaryRows" :key="row.id" class="evaluation-metric-card">
              <div class="metric-card-top"><span>{{ row.label }}</span><span class="method-chip" :class="{ degraded: row.fallbackCount, failed: row.failedCount }">{{ row.failedCount ? `失败 ${row.failedCount}` : row.fallbackCount ? `RRF fallback · ${row.fallbackCount}` : row.short }}</span></div>
              <strong>{{ formatMetric(row.values.mrr) }}</strong>
              <small>MRR · Recall@{{ evaluationCutoffs[evaluationCutoffs.length - 1] }} {{ formatPercent(row.values[`recall@${evaluationCutoffs[evaluationCutoffs.length - 1]}`]) }}<template v-if="row.fallbackCount"> · {{ row.fallbackCount }} 题实际为 RRF</template><template v-if="row.failedCount"> · {{ row.failedCount }} 题失败</template></small>
            </article>
          </section>

          <section class="report-section">
            <div class="section-heading"><div><p class="eyebrow">Strategy comparison</p><h3>指标对比</h3></div><span class="report-badge">真实运行 · retrieval-only</span></div>
            <div class="table-wrap">
              <table class="evaluation-table"><thead><tr><th>策略</th><th>MRR</th><template v-for="cutoff in evaluationCutoffs" :key="`head-${cutoff}`"><th>Recall@{{ cutoff }}</th><th>nDCG@{{ cutoff }}</th></template></tr></thead>
                <tbody><tr v-for="row in evaluationSummaryRows" :key="row.id"><th>{{ row.label }}<small v-if="row.fallbackCount" class="table-note">实际 RRF {{ row.fallbackCount }} 题</small><small v-if="row.failedCount" class="table-note danger">失败 {{ row.failedCount }} 题</small></th><td class="strong-number">{{ formatMetric(row.values.mrr) }}</td><template v-for="cutoff in evaluationCutoffs" :key="`${row.id}-${cutoff}`"><td>{{ formatPercent(row.values[`recall@${cutoff}`]) }}</td><td>{{ formatMetric(row.values[`ndcg@${cutoff}`]) }}</td></template></tr></tbody>
              </table>
            </div>
          </section>

          <section class="report-section">
            <div class="section-heading"><div><p class="eyebrow">Per-query drilldown</p><h3>逐题命中</h3></div><span class="muted-copy">展示前 10 题 · cutoff {{ evaluationCutoffs[evaluationCutoffs.length - 1] }}</span></div>
            <div class="case-list"><article v-for="item in evaluationCaseRows" :key="item.id" class="case-row"><div class="case-query"><span>{{ item.id }} · 请求 {{ item.method }} · 实际 {{ methodLabel(item.effectiveMethod) }}<template v-if="item.fallbackReason"> · {{ traceReason(item.fallbackReason) }}</template></span><strong>{{ item.query }}</strong></div><div class="case-metrics"><span>MRR <b>{{ formatMetric(item.metrics.reciprocal_rank) }}</b></span><span>Recall <b>{{ formatPercent(item.metrics[`recall@${evaluationCutoffs[evaluationCutoffs.length - 1]}`]) }}</b></span><span>nDCG <b>{{ formatMetric(item.metrics[`ndcg@${evaluationCutoffs[evaluationCutoffs.length - 1]}`]) }}</b></span></div><code>{{ item.retrieved.join(' · ') || '无结果' }}</code></article></div>
          </section>
        </template>

        <section class="method-note"><el-icon aria-hidden="true"><InfoFilled /></el-icon><p><strong>如何读结果：</strong>Recall 看相关证据有没有被召回，MRR 看第一个相关片段出现得早不早，nDCG 还会考虑相关性等级。它们衡量检索排序，不等于回答事实正确性；引用校验也只验证编号结构。</p></section>
      </section>
    </section>

    <el-drawer v-model="sourceDrawerOpen" title="证据详情" size="min(440px, 92vw)" direction="rtl">
      <template v-if="selectedSource">
        <p class="drawer-label">{{ selectedSource.id }} · {{ selectedSource.retrieval_method || 'evidence' }}</p>
        <h2>{{ selectedSource.filename }}</h2>
        <p class="source-excerpt">{{ selectedSource.excerpt || '没有返回片段摘要。' }}</p>
        <dl class="source-details">
          <div><dt>定位</dt><dd>{{ sourceLocation(selectedSource) }}</dd></div>
          <div><dt>Evidence ID</dt><dd class="mono">{{ selectedSource.evidence_id || selectedSource.chunk_id || '未提供' }}</dd></div>
          <div><dt>父片段 / 子片段</dt><dd class="mono">{{ selectedSource.parent_id || '—' }} / {{ selectedSource.child_chunk_id || '—' }}</dd></div>
          <div><dt>候选来源</dt><dd>{{ selectedSource.candidate_origin || '—' }}</dd></div>
          <div><dt>最终排序</dt><dd>#{{ selectedSource.final_rank || '—' }} · Vector #{{ selectedSource.vector_rank || '—' }} · BM25 #{{ selectedSource.bm25_rank || '—' }}</dd></div>
          <div><dt>融合 / 重排分数</dt><dd>{{ selectedSource.rrf_score ?? '—' }} / {{ selectedSource.rerank_score ?? '—' }}</dd></div>
        </dl>
        <p class="drawer-footnote"><el-icon aria-hidden="true"><InfoFilled /></el-icon> 来源编号校验只验证 [S#] 是否映射到本次证据，不证明回答语义上被原文蕴含。</p>
      </template>
    </el-drawer>

    <input ref="fileInput" class="sr-only" tabindex="-1" aria-label="选择要索引的资料文件" type="file" accept=".txt,.md,.pdf,.docx,.csv,.json,.py,.log" @change="handleUpload" />
  </main>
</template>
