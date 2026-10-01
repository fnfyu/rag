<script setup>
import { ref, watch } from 'vue'
const props = defineProps({ series: Object, request: Function })
const emit = defineEmits(['open-task'])
const left = ref(''), right = ref(''), result = ref(null), error = ref(''), busy = ref(false)
let sequence = 0
watch(() => props.series?.id, () => { ++sequence; result.value = null; error.value = ''; left.value = props.series?.versions?.[0]?.id || ''; right.value = props.series?.versions?.[1]?.id || ''; busy.value = false }, { immediate: true })
async function compare() { const epoch = ++sequence; result.value = null; error.value = ''; busy.value = true; try { const value = await (await props.request(`/documents/series/${encodeURIComponent(props.series.id)}/compare?left_version=${encodeURIComponent(left.value)}&right_version=${encodeURIComponent(right.value)}`)).json(); if (epoch === sequence) result.value = value } catch (e) { if (epoch === sequence) error.value = e.message } finally { if (epoch === sequence) busy.value = false } }
const text = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2)
</script>
<template>
  <section class="v2-card">
    <h3>版本比较</h3>
    <p class="panel-note">明确选择两个版本。日期或适用条件未知时，不推断“最新版本一定正确”。</p>
    <div class="v2-form-grid">
      <label>左侧版本<select v-model="left" :disabled="busy" @change="result = null">
          <option value="">选择版本</option>
          <option v-for="v in series?.versions || []" :key="v.id" :value="v.id">{{ v.version_label || v.id }} · {{ v.release_date || '日期未知' }}</option>
        </select>
      </label>
      <label>右侧版本<select v-model="right" :disabled="busy" @change="result = null">
          <option value="">选择版本</option>
          <option v-for="v in series?.versions || []" :key="v.id" :value="v.id">{{ v.version_label || v.id }} · {{ v.release_date || '日期未知' }}</option>
        </select>
      </label>
      <el-button type="primary" :loading="busy" :disabled="!left || !right || left === right" @click="compare">比较版本</el-button>
    </div>
    <p v-if="error" role="alert" class="v2-error">{{ error }}</p>
    <template v-if="result">
      <div class="v2-warning">
        <strong>结论状态：{{ result.summary?.status || '未提供' }}</strong>
        <p>{{ result.summary?.recommendation || '未返回适用性建议，请自行核对条件。' }}</p>
        <article v-for="(conflict,index) in result.summary?.conflicts || []" :key="index">
          <h4>{{ conflict.claim }}</h4>
          <div class="diff-columns">
            <blockquote>{{ conflict.left_quote }}</blockquote>
            <blockquote>{{ conflict.right_quote }}</blockquote>
          </div>
          <p>{{ conflict.reason }}</p>
          <p>适用条件：{{ conflict.applicability || '未知' }}</p>
        </article>
      </div>
      <article v-for="(change,index) in result.changes || []" :key="index" class="diff-section">
        <h4>{{ change.kind }}</h4>
        <div class="diff-columns">
          <div>
            <small>左侧 · 第 {{ change.left_start_line || '未知' }} 行</small>
            <pre class="v2-pre">{{ text(change.before) }}</pre>
          </div>
          <div>
            <small>右侧 · 第 {{ change.right_start_line || '未知' }} 行</small>
            <pre class="v2-pre">{{ text(change.after) }}</pre>
          </div>
        </div>
      </article>
      <p v-if="!result.changes?.length" class="panel-note">没有返回文本差异；这不等于适用条件相同。</p>
      <h4>受影响的研究任务</h4>
      <article v-for="task in result.affected_tasks || []" :key="task.id" class="diff-section">
        <button class="evidence-link" type="button" @click="emit('open-task', task.id)">
          <strong>{{ task.title }} · 修订 {{ task.revision }}</strong>
          <span>受影响章节：{{ task.section_ids?.join('、') || '未提供' }} · 打开研究交付核查</span>
        </button>
        <details v-if="task.claims?.length" class="research-details">
          <summary>可能需重新核验的具体结论 · {{ task.claims.length }}</summary>
          <p class="panel-note">资料版本发生变化，仅提示重新确认，不代表这些结论自动失效或错误。</p>
          <ol class="claim-list">
            <li v-for="(claim, index) in task.claims" :key="`${claim.section_id}-${claim.id || index}`" class="claim-item">
              <div class="panel-heading">
                <strong>章节 {{ claim.section_id || '未提供' }} · {{ claim.id || '未提供结论编号' }}</strong>
                <span>{{ claim.status === 'needs_confirmation' ? '需重新确认' : '待核查' }}</span>
              </div>
              <p class="claim-text">{{ claim.text }}</p>
              <p class="panel-note">此前核验：{{ ({ supported: '证据支持', contradicted: '与证据矛盾', insufficient: '证据不足' })[claim.previous_verdict] || claim.previous_verdict || '未记录' }}</p>
              <p v-if="claim.reason" class="panel-note">重新确认原因：{{ claim.reason }}</p>
              <el-button text @click="emit('open-task', task.id)">打开任务核查本章（{{ claim.section_id || '章节未知' }}）</el-button>
            </li>
          </ol>
        </details>
      </article>
      <p v-if="!result.affected_tasks?.length" class="panel-note">未返回关联任务。</p>
    </template>
  </section>
</template>
