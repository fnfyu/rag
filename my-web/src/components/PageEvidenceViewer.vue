<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
const props = defineProps({ versionId: String, initialPageNumber: Number, initialBbox: Array, request: Function })
const pages = ref([]), pageNumber = ref(null), imageUrl = ref(''), region = ref(null), question = ref(''), answer = ref(null), error = ref(''), loading = ref(false), busy = ref(false)
const tableId = ref(''), operation = ref('sum'), column = ref(''), groupBy = ref(''), rowA = ref(''), rowB = ref(''), filters = ref(''), calculation = ref(null)
let sequence = 0, imageSequence = 0, disposed = false
const page = computed(() => pages.value.find(item => item.page_number === pageNumber.value))
const tables = computed(() => page.value?.tables || [])
const table = computed(() => tables.value.find(item => String(item.id) === String(tableId.value)))
const columns = computed(() => (table.value?.columns || []).map(item => typeof item === 'string' ? item : item.name || item.key || item.id))
const operations = [{ id: 'sum', label: '求和' }, { id: 'mean', label: '平均' }, { id: 'min', label: '最小值' }, { id: 'max', label: '最大值' }, { id: 'count', label: '计数' }, { id: 'difference', label: '两行差值' }, { id: 'ratio', label: '两行比值' }, { id: 'group_sum', label: '分组求和' }]
const serialize = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2)
const cell = (row, name, index) => Array.isArray(row) ? row[index] : row?.[name] ?? row?.values?.[name] ?? row?.cells?.[index] ?? ''
function revoke() { if (imageUrl.value) URL.revokeObjectURL(imageUrl.value); imageUrl.value = '' }
async function asset() {
  const epoch = ++imageSequence; revoke(); region.value = props.initialBbox ? page.value?.regions?.find(item => JSON.stringify(item.bbox) === JSON.stringify(props.initialBbox)) || null : null; answer.value = null; calculation.value = null; tableId.value = tables.value[0]?.id || ''; error.value = ''
  if (!page.value?.asset_url) return
  try {
    // Absolute asset URLs are accepted only on the current/API origin. Never send auth to an arbitrary origin.
    const apiBase = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
    const rawAsset = page.value.asset_url.startsWith('/documents/') ? `${apiBase}${page.value.asset_url}` : page.value.asset_url
    const url = new URL(rawAsset, window.location.origin)
    const apiUrl = new URL(apiBase, window.location.origin)
    if (![window.location.origin, apiUrl.origin].includes(url.origin)) throw new Error('页图地址不在可信的服务来源，未发送鉴权')
    const headers = new Headers(); const key = import.meta.env.DEV ? import.meta.env.VITE_API_KEY : ''; if (key) headers.set('X-API-Key', key)
    const response = await fetch(url.href, { headers, credentials: 'same-origin' }); if (!response.ok) throw new Error(`页图加载失败 (${response.status})`)
    const blob = await response.blob(); if (epoch !== imageSequence || disposed) return; imageUrl.value = URL.createObjectURL(blob)
  } catch (e) { if (epoch === imageSequence) error.value = e.message }
}
async function load() {
  const epoch = ++sequence; ++imageSequence; revoke(); pages.value = []; pageNumber.value = null; answer.value = null; calculation.value = null; error.value = ''; loading.value = true
  if (!props.versionId) { loading.value = false; return }
  try { const payload = await (await props.request(`/documents/versions/${encodeURIComponent(props.versionId)}/pages`)).json(); if (epoch !== sequence || disposed) return; pages.value = Array.isArray(payload) ? payload : payload.pages || []; pageNumber.value = pages.value.find(item => item.page_number === props.initialPageNumber)?.page_number ?? pages.value[0]?.page_number ?? null } catch (e) { if (epoch === sequence) error.value = e.message } finally { if (epoch === sequence) loading.value = false }
}
async function post(suffix, body) { return (await props.request(`/documents/versions/${encodeURIComponent(props.versionId)}${suffix}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json() }
async function analyze() { if (!page.value?.asset_url || page.value?.is_virtual_page) { error.value = '文本资料没有实际页图，不支持视觉分析'; return } busy.value = true; error.value = ''; const epoch = sequence, pageId = pageNumber.value; try { const value = await post(`/pages/${pageId}/analyze`, { question: question.value }); if (epoch === sequence && pageId === pageNumber.value) answer.value = value } catch (e) { if (epoch === sequence) error.value = e.message } finally { busy.value = false } }
async function calculate() {
  busy.value = true; error.value = ''; calculation.value = null; const epoch = sequence, pageId = pageNumber.value
  try { let filterValue; if (filters.value.trim()) { try { filterValue = JSON.parse(filters.value) } catch { throw new Error('筛选条件必须为合法 JSON，不会由模型猜测') } }
    const body = { table_id: tableId.value, operation: operation.value, column: column.value, ...(filterValue ? { filters: filterValue } : {}), ...(operation.value === 'group_sum' ? { group_by: groupBy.value } : {}), ...(['difference','ratio'].includes(operation.value) ? { row_a: Number(rowA.value), row_b: Number(rowB.value) } : {}) }
    const value = await post('/tables/calculate', body); if (epoch === sequence && pageId === pageNumber.value) calculation.value = { ...value, selected_column: column.value, selected_operation: operation.value }
  } catch (e) { if (epoch === sequence) error.value = e.message } finally { busy.value = false }
}
watch(() => props.versionId, load, { immediate: true })
watch(pageNumber, asset)
watch(() => props.initialPageNumber, value => { if (pages.value.some(item => item.page_number === value)) pageNumber.value = value })
watch(() => props.initialBbox, () => { region.value = page.value?.regions?.find(item => JSON.stringify(item.bbox) === JSON.stringify(props.initialBbox)) || null })
watch(tableId, () => { column.value = columns.value[0] || ''; groupBy.value = columns.value[0] || ''; rowA.value = ''; rowB.value = ''; calculation.value = null })
onBeforeUnmount(() => { disposed = true; ++sequence; ++imageSequence; revoke() })
</script>
<template>
  <section class="v2-card">
    <div class="v2-heading">
      <h3>{{ page?.is_virtual_page ? '文本区域与表格证据' : '图文页与表格证据' }}</h3>
      <el-button :disabled="loading || busy" @click="load">刷新页面</el-button>
    </div>
    <p v-if="loading" role="status">加载页面证据…</p>
    <p v-if="error" class="v2-error" role="alert">{{ error }}</p>
    <p v-if="!loading && !pages.length" class="panel-note">该版本没有返回页图或表格。仅支持已解析的图文页，不虚构视觉证据。</p>
    <template v-if="page">
      <label class="v2-form">证据分组<select v-model="pageNumber" :disabled="busy">
          <option v-for="item in pages" :key="item.page_number" :value="item.page_number">{{ item.label || `第 ${item.page_number} 页` }}</option>
        </select>
      </label>
      <div class="page-evidence-layout">
        <div>
          <div v-if="imageUrl" class="page-image">
            <img :src="imageUrl" :alt="`资料第 ${page.page_number} 页`" :width="page.width || undefined" :height="page.height || undefined" />
            <svg v-if="page.width && page.height" :viewBox="`0 0 ${page.width} ${page.height}`" class="page-overlay" aria-label="页面证据定位">
              <rect v-for="(item,index) in page.regions || []" :key="index" :x="item.bbox?.[0] || 0" :y="item.bbox?.[1] || 0" :width="Math.max(0,(item.bbox?.[2] || 0)-(item.bbox?.[0] || 0))" :height="Math.max(0,(item.bbox?.[3] || 0)-(item.bbox?.[1] || 0))" class="region-box" :class="{ selected: region === item }" tabindex="0" role="button" :aria-label="`阅读区域 ${index + 1}：${item.region_type || '文本'}`" @click="region = item" @keydown.enter.prevent="region = item" @keydown.space.prevent="region = item" />
              <rect v-if="initialBbox?.length === 4 && page.page_number === initialPageNumber" :x="initialBbox[0]" :y="initialBbox[1]" :width="initialBbox[2]-initialBbox[0]" :height="initialBbox[3]-initialBbox[1]" class="answer-box" />
              <rect v-if="answer?.bbox?.length === 4" :x="answer.bbox[0]" :y="answer.bbox[1]" :width="answer.bbox[2]-answer.bbox[0]" :height="answer.bbox[3]-answer.bbox[1]" class="answer-box" />
            </svg>
          </div>
          <p v-else class="panel-note">未提供可加载的页图，仍可阅读已解析区域。</p>
        </div>
        <div>
          <h4>{{ page.is_virtual_page ? '文本区域' : '页面区域' }}</h4>
          <button v-for="(item,index) in page.regions || []" :key="index" type="button" class="evidence-link" @click="region = item">区域 {{ index + 1 }} · {{ item.region_type }} · {{ item.evidence_modality }}</button>
          <pre v-if="region" class="v2-pre">{{ region.content }}</pre>
        </div>
      </div>
      <p v-if="page.is_virtual_page" class="panel-note">这是文本资料的虚拟证据分组，不是实际分页；可阅读区域、核对表格与计算来源，不支持视觉分析。</p>
      <form v-if="page.asset_url && !page.is_virtual_page" class="v2-form" @submit.prevent="analyze">
        <label>向本页提问<textarea v-model="question" rows="2" required placeholder="针对图表、图片或本页内容提问" />
        </label>
        <el-button native-type="submit" type="primary" :loading="busy" :disabled="!question.trim()">分析当前页</el-button>
      </form>
      <div v-if="answer" class="v2-progress">
        <pre class="v2-pre">{{ answer.answer }}</pre>
        <p>来源 {{ answer.source_id || '未提供' }} · 第 {{ answer.page_number }} 页 · 定位 {{ serialize(answer.bbox) }}</p>
      </div>
      <div v-if="tables.length" class="table-evidence">
        <h3>确定性表格计算</h3>
        <p class="panel-note">明确指定操作与列，不由模型猜算。来源行索引从 0 开始。</p>
        <div class="v2-form-grid">
          <label>表格<select v-model="tableId" :disabled="busy">
              <option v-for="item in tables" :key="item.id" :value="item.id">{{ item.title || item.id }}</option>
            </select>
          </label>
          <label>操作<select v-model="operation" :disabled="busy">
              <option v-for="item in operations" :key="item.id" :value="item.id">{{ item.label }}</option>
            </select>
          </label>
          <label>计算列<select v-model="column" :disabled="busy">
              <option v-for="name in columns" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>
          <label v-if="operation === 'group_sum'">分组列<select v-model="groupBy">
              <option v-for="name in columns" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>
          <template v-if="['difference','ratio'].includes(operation)">
            <label>行 A 索引<input v-model="rowA" type="number" min="0" :max="(table?.rows?.length || 1)-1" />
            </label>
            <label>行 B 索引<input v-model="rowB" type="number" min="0" :max="(table?.rows?.length || 1)-1" />
            </label>
          </template>
        </div>
        <details class="v2-form">
          <summary>可选筛选条件（JSON）</summary>
          <label>筛选条件<textarea v-model="filters" rows="2" placeholder="留空使用全部行；按后端 filters 契约填写 JSON" />
          </label>
        </details>
        <div class="table-wrap">
          <table class="evidence-table">
            <thead>
              <tr>
                <th>来源行索引</th>
                <th v-for="name in columns" :key="name">{{ name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row,index) in table?.rows || []" :key="index">
                <th>{{ index }}</th>
                <td v-for="(name,col) in columns" :key="name">{{ cell(row,name,col) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <el-button type="primary" :loading="busy" :disabled="!tableId || !column || (operation === 'group_sum' && !groupBy) || (['difference','ratio'].includes(operation) && (rowA === '' || rowB === ''))" @click="calculate">计算并返回来源行</el-button>
        <div v-if="calculation" class="v2-progress">
          <h4>{{ calculation.selected_column }} · {{ operations.find(item => item.id === calculation.selected_operation)?.label }}</h4>
          <pre class="v2-pre">{{ serialize(calculation.result) }} {{ calculation.unit || '' }}</pre>
          <p>公式：{{ calculation.formula }}</p>
          <h4>使用的来源行</h4>
          <pre class="v2-pre">{{ serialize(calculation.used_rows) }}</pre>
          <h4>计算证据</h4>
          <pre class="v2-pre">{{ serialize(calculation.evidence) }}</pre>
        </div>
      </div>
    </template>
  </section>
</template>
