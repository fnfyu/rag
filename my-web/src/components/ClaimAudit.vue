<script setup>
import { computed } from 'vue'
const props = defineProps({ audit: Object })
const emit = defineEmits(['open-evidence'])
const statusLabel = computed(() => ({ checking: '正在逐结论核验', completed: '逐结论核验完成', partial: '逐结论核验部分完成', unavailable: '语义核验不可用', no_sources: '无来源，无法语义核验', skipped: '已跳过语义核验' })[props.audit?.status] || '未记录语义核验')
const verdictLabel = (verdict) => ({ supported: '证据支持', contradicted: '与证据矛盾', insufficient: '证据不足' })[verdict] || '判断未知'
</script>

<template>
  <section v-if="audit" class="claim-audit" aria-label="逐结论语义核验">
    <div class="panel-heading"><strong>{{ statusLabel }}</strong><span v-if="audit.method">{{ audit.method }}</span></div>
    <p class="panel-note">{{ audit.disclaimer || '模型语义判断不是事实证明，重要结论请查阅引用原文。' }}</p>
    <p class="panel-note">语义核验评估回答与本次证据的关系，不证明资料本身真实。</p>
    <p v-if="audit.summary" class="audit-summary">支持 {{ audit.summary.supported ?? 0 }} · 矛盾 {{ audit.summary.contradicted ?? 0 }} · 不足 {{ audit.summary.insufficient ?? 0 }} · 总计 {{ audit.summary.total ?? 0 }}</p>
    <details v-if="audit.claims?.length" class="research-details">
      <summary>查看结论与原文引用 · {{ audit.claims.length }}</summary>
      <ol class="claim-list">
        <li v-for="claim in audit.claims" :key="claim.id" class="claim-item" :class="claim.verdict">
          <div class="panel-heading"><strong>{{ claim.id }}</strong><span class="verdict-label">{{ verdictLabel(claim.verdict) }}</span></div>
          <p class="claim-text">{{ claim.text }}</p><p class="panel-note">{{ claim.reason }}</p>
          <div class="claim-evidence">
            <button v-for="(evidence, index) in claim.evidence || []" :key="index" type="button" class="evidence-link" @click="emit('open-evidence', evidence)"><strong>{{ evidence.source_id }} · 查看原文<template v-if="evidence.start_line"> · 第 {{ evidence.start_line }}–{{ evidence.end_line || evidence.start_line }} 行</template></strong><span v-if="evidence.quote">“{{ evidence.quote }}”</span></button>
            <button v-for="sourceId in (claim.citation_ids || []).filter(id => !(claim.evidence || []).some(item => item.source_id === id))" :key="sourceId" type="button" class="evidence-link" @click="emit('open-evidence', { source_id: sourceId })">{{ sourceId }} · 查看原文</button>
          </div>
        </li>
      </ol>
    </details>
    <p v-if="audit.truncated" class="panel-note">结论列表已截断，未覆盖回答的全部结论。</p>
  </section>
</template>
