<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import VersionComparison from './VersionComparison.vue'
import PageEvidenceViewer from './PageEvidenceViewer.vue'
const props = defineProps({ knowledgeBaseId: String, conversationId: String, gameProfile: Object, request: Function })
const emit = defineEmits(['changed', 'open-task'])
const series = ref([]), selectedId = ref(''), versionId = ref(''), jobs = ref([]), loading = ref(false), uploading = ref(false), error = ref(''), search = ref('')
const file = ref(null), fileInput = ref(null), versionLabel = ref(''), releaseDate = ref(''), applicability = ref(''), uploadOpen = ref(false)
const sourceKind = ref('reference'), sourceTier = ref('player'), sourceUrl = ref(''), metadataPatch = ref(''), metadataEdition = ref(''), metadataMode = ref('')
const annotationId = ref(''), annotationJson = ref(''), annotating = ref(false)
const selected = computed(() => series.value.find(item => item.id === selectedId.value))
const domainSummary = version => { const metadata = version.domain_metadata; return metadata?.game_id ? `${metadata.game_id} · ${metadata.edition || '版本未知'} · 补丁 ${metadata.patch || '未知'} · ${metadata.mode || '玩法未知'} · ${metadata.source_kind || '类型未知'} · ${metadata.source_tier || '层级未知'} · ${metadata.provenance || '未核验'}` : '游戏条件未标注' }
function domainMetadata() {
  return { ...(props.gameProfile || {}), source_kind: sourceKind.value, source_tier: sourceTier.value, provenance: 'user_declared', ...(sourceUrl.value.trim() ? { url: sourceUrl.value.trim() } : {}), patch: metadataPatch.value.trim() || null, edition: metadataEdition.value.trim() || null, mode: metadataMode.value.trim() || null }
}
function annotate(version) { if (version.domain_metadata?.game_id && version.domain_metadata.game_id !== props.gameProfile?.game_id) { error.value = '此资料已标注其他游戏，不允许改绑'; return }; annotationId.value = version.id; annotationJson.value = JSON.stringify({ ...domainMetadata(), ...(version.domain_metadata || {}), game_id: props.gameProfile?.game_id, provenance: 'user_declared' }, null, 2) }
async function saveAnnotation() {
  annotating.value = true; error.value = ''
  const epoch = sequence
  try {
    const metadata = JSON.parse(annotationJson.value)
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) throw new Error('元信息必须为JSON对象')
    if (metadata.game_id !== props.gameProfile?.game_id) throw new Error('只能标注本知识库所属游戏')
    metadata.provenance = 'user_declared'
    await props.request(`/knowledge-bases/${encodeURIComponent(props.knowledgeBaseId)}/documents/${encodeURIComponent(annotationId.value)}/metadata`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(metadata) })
    if (epoch !== sequence) return
    annotationId.value = ''; await load()
  } catch (e) { if (epoch === sequence) error.value = e.message } finally { annotating.value = false }
}
const visibleSeries = computed(() => series.value.filter(item => item.filename?.toLowerCase().includes(search.value.toLowerCase())))
let sequence = 0, timer = null, disposed = false
const list = (data, key) => Array.isArray(data) ? data : data?.[key] || data?.items || []
const jobStatus = job => ({ completed: '已索引', failed: '失败', queued: '排队中', processing: '处理中' })[job.status] || job.stage_label || job.status
async function load(reset = false) {
  const kb = props.knowledgeBaseId, epoch = sequence
  if (!kb) return
  loading.value = true; error.value = ''
  try { const [docs, uploads] = await Promise.all([props.request(`/knowledge-bases/${encodeURIComponent(kb)}/documents`), props.request(`/uploads?knowledge_base_id=${encodeURIComponent(kb)}`)])
    const [docData, uploadData] = await Promise.all([docs.json(), uploads.json()]); if (epoch !== sequence || disposed) return
    series.value = list(docData, 'document_series'); jobs.value = list(uploadData, 'uploads'); if (reset || !series.value.some(item => item.id === selectedId.value)) selectedId.value = series.value[0]?.id || ''
    emit('changed'); schedule()
  } catch (e) { if (epoch === sequence) { error.value = e.message; clearTimeout(timer) } } finally { if (epoch === sequence) loading.value = false }
}
function schedule() { clearTimeout(timer); if (jobs.value.some(job => ['queued','processing','running'].includes(job.status)) && !disposed) timer = setTimeout(() => load(), 2000) }
function pick(event) { file.value = event.target.files?.[0] || null }
async function upload() {
  if (!file.value || !props.knowledgeBaseId) return
  const epoch = sequence, form = new FormData(); form.append('file', file.value); form.append('knowledge_base_id', props.knowledgeBaseId)
  if (props.conversationId) form.append('conversation_id', props.conversationId)
  if (versionLabel.value.trim()) form.append('version_label', versionLabel.value.trim())
  if (releaseDate.value) form.append('release_date', releaseDate.value)
  if (applicability.value.trim()) form.append('applicability', applicability.value.trim())
  if (props.gameProfile?.game_id) form.append('domain_metadata', JSON.stringify(domainMetadata()))
  uploading.value = true; error.value = ''
  try { await props.request('/uploads', { method: 'POST', body: form }); if (epoch !== sequence || disposed) return; file.value = null; if (fileInput.value) fileInput.value.value = ''; versionLabel.value = ''; releaseDate.value = ''; applicability.value = ''; uploadOpen.value = false; await load() }
  catch (e) { if (epoch === sequence) error.value = e.message } finally { uploading.value = false }
}
watch(() => props.knowledgeBaseId, () => { ++sequence; clearTimeout(timer); series.value = []; selectedId.value = ''; versionId.value = ''; jobs.value = []; error.value = ''; file.value = null; uploadOpen.value = false; load(true) }, { immediate: true })
watch(selectedId, () => { versionId.value = selected.value?.versions?.[0]?.id || ''; annotationId.value = '' })
watch(() => props.gameProfile, profile => { metadataPatch.value = profile?.patch || ''; metadataEdition.value = profile?.edition || ''; metadataMode.value = profile?.mode || ''; annotationId.value = ''; sourceUrl.value = ''; sourceTier.value = 'player'; sourceKind.value = 'reference' }, { immediate: true, deep: true })
onBeforeUnmount(() => { disposed = true; ++sequence; clearTimeout(timer) })
</script>
<template>
  <div v-if="!knowledgeBaseId" class="v2-empty">
    <h2>选择知识库管理资料</h2>
    <p>资料版本跨会话共享；同名上传保留历史版本。</p>
  </div>
  <div v-else class="document-library">
    <div class="v2-heading">
      <div>
        <p class="eyebrow">Shared evidence library</p>
        <h2>资料与版本</h2>
        <p class="panel-note">同一知识库内共享；同名新版本保留，不覆盖旧资料。</p>
      </div>
      <div class="v2-actions">
        <el-button :loading="loading" @click="load()">刷新资料</el-button>
        <el-button type="primary" @click="uploadOpen = !uploadOpen">上传资料 / 新版本</el-button>
      </div>
    </div>
    <p v-if="error" role="alert" class="v2-error">{{ error }}</p>
    <form v-if="uploadOpen" class="v2-card v2-form" @submit.prevent="upload">
      <h3>上传资料版本</h3>
      <label>文件<input ref="fileInput" type="file" required @change="pick" />
      </label>
      <div class="v2-form-grid">
        <label>版本标记<input v-model="versionLabel" placeholder="可选，例如 v2 / 修订版" />
        </label>
        <label>发布日期<input v-model="releaseDate" type="date" />
        </label>
      </div>
      <label>适用条件<textarea v-model="applicability" rows="2" placeholder="可选，未知则留空，不会推断当前版本适用" />
      </label>
      <template v-if="gameProfile?.game_id">
        <div class="v2-form-grid">
          <label>来源类型<select v-model="sourceKind"><option value="guide">攻略 guide</option><option value="reference">参考资料 reference</option><option value="player_sheet">玩家面板 player_sheet</option></select></label>
          <label>人工声明来源层级<select v-model="sourceTier"><option value="player">玩家输入</option><option value="community">社区</option><option value="official">官方（仅人工声明，非核验抓取）</option></select></label>
          <label>适用补丁<input v-model="metadataPatch" placeholder="未知则留空" /></label>
          <label>适用 edition<input v-model="metadataEdition" placeholder="沿用本库条件，可明确留空为未知" /></label>
          <label>适用玩法 / mode<input v-model="metadataMode" /></label>
          <label>原始来源 URL（可选）<input v-model="sourceUrl" type="url" /></label>
        </div>
        <p class="panel-note">游戏 {{ gameProfile.game_id }}，其余条件继承当前库。上传始终标为 user_declared；声明“官方”不等于 verified_capture。</p>
      </template>
      <p class="panel-note">上传至共享知识库{{ conversationId ? '，同时关联当前会话' : '' }}。同名文件归入版本系列；未提供的日期与条件保持未知。</p>
      <el-button native-type="submit" type="primary" :loading="uploading" :disabled="!file">上传并索引</el-button>
    </form>
    <section v-if="jobs.length" class="v2-card">
      <details>
        <summary>上传与索引状态 · {{ jobs.length }}</summary>
        <div v-for="job in jobs" :key="job.id || job.upload_id" class="history-row">
          <span>
            <strong>{{ job.filename }}</strong>
            <small>{{ jobStatus(job) }} · {{ job.stage_label || job.stage }}<template v-if="job.chunk_count"> · {{ job.chunk_count }} 个片段</template>
              <template v-if="job.error"> · {{ job.error }}</template>
            </small>
          </span>
          <el-button v-if="['failed','unknown'].includes(job.status)" text @click="load()">刷新确认</el-button>
        </div>
      </details>
    </section>
    <div class="library-layout">
      <aside class="v2-card library-list">
        <label class="v2-form">检索文件名<input v-model="search" type="search" placeholder="搜索库内资料" />
        </label>
        <button v-for="item in visibleSeries" :key="item.id" class="task-item" :class="{ active: selectedId === item.id }" type="button" @click="selectedId = item.id">
          <strong>{{ item.filename }}</strong>
          <small>{{ item.versions?.length || 0 }} 个保留版本</small>
        </button>
        <p v-if="!visibleSeries.length" class="panel-note">{{ series.length ? '没有匹配的文件名。' : '暂无资料，请先上传。' }}</p>
      </aside>
      <div v-if="selected" class="library-detail">
        <section class="v2-card">
          <h3>{{ selected.filename }}</h3>
          <div class="table-wrap">
            <table class="evidence-table">
              <thead>
                <tr>
                  <th>版本</th>
                  <th>发布日期</th>
                  <th>适用条件</th>
                  <th>索引状态</th>
                  <th>片段</th>
                  <th>证据页</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="version in selected.versions" :key="version.id">
                  <th>{{ version.version_label || '未标版本' }}</th>
                  <td>{{ version.release_date || '日期未知' }}</td>
                  <td>{{ version.applicability || '适用条件未知' }}
                     <small v-if="gameProfile?.game_id || version.domain_metadata?.game_id" class="panel-note souls-domain-note">{{ domainSummary(version) }}</small>
                     <a v-if="/^https?:\/\//i.test(version.domain_metadata?.url || '')" :href="version.domain_metadata.url" target="_blank" rel="noopener noreferrer">来源链接</a>
                     <el-button v-if="gameProfile?.game_id && !['verified_capture','feed_capture'].includes(version.domain_metadata?.provenance)" text @click="annotate(version)">人工标注旧资料条件</el-button>
                   </td>
                  <td>{{ version.status || '未知' }}</td>
                  <td>{{ version.chunk_count ?? '—' }}</td>
                  <td>
                    <el-button :type="versionId === version.id ? 'primary' : 'default'" @click="versionId = version.id">查看页图 / 表格</el-button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <form v-if="annotationId" class="v2-card v2-form" @submit.prevent="saveAnnotation">
          <h3>人工标注资料游戏条件</h3>
          <label>domain_metadata JSON<textarea v-model="annotationJson" rows="10" spellcheck="false" /></label>
          <p class="panel-note">不改变版本发布日期与适用条件。只能标为本游戏；人工声明不升级为核验抓取。</p>
          <div class="v2-actions"><el-button native-type="submit" type="primary" :loading="annotating">保存条件标注</el-button><el-button @click="annotationId = ''">取消</el-button></div>
        </form>
        <VersionComparison :series="selected" :request="request" @open-task="emit('open-task', $event)" />
        <PageEvidenceViewer v-if="versionId" :version-id="versionId" :request="request" />
      </div>
      <div v-else class="v2-empty">
        <h3>共享资料库</h3>
        <p>选择文件查看保留版本、版本差异与可定位的图文证据。</p>
      </div>
    </div>
  </div>
</template>
