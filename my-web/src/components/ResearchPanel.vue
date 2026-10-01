<script setup>
import { computed } from 'vue'
import EvidenceGraph from './EvidenceGraph.vue'
const props = defineProps({ trace: Object, context: Object })
const emit = defineEmits(['open-evidence'])
const steps = [{ id: 'planning', label: '规划子问题' }, { id: 'retrieving', label: '检索证据' }, { id: 'assessing', label: '评估缺口' }]
const statusLabel = computed(() => ({ planning: '正在规划子问题', retrieving: '正在检索证据', assessing: '正在评估证据缺口', completed: '研究完成', partial: '研究部分完成' })[props.trace?.status] || '等待研究轨迹')
const ongoing = computed(() => ['planning', 'retrieving', 'assessing'].includes(props.trace?.status))
const rounds = computed(() => props.trace?.rounds || [])
const currentRound = computed(() => rounds.value.at(-1))
const contextStats = computed(() => props.trace?.context || props.context)
const modeLabel = (mode) => ({ auto: '自动', quick: '快速', research: '深度研究' })[mode] || mode || '未提供'
const stopLabel = (reason) => ({ single_pass: '单轮检索完成', sufficient_evidence: '证据已充分', no_new_evidence: '没有新增证据', round_budget: '达到轮次预算', time_budget: '达到时间预算', token_budget: '达到规划 token 预算', model_unavailable: '规划模型不可用', empty_collection: '知识库为空' })[reason] || reason || '未提供'
</script>

<template>
  <section v-if="trace" class="research-panel" aria-label="研究轨迹">
    <div class="panel-heading"><strong>自适应研究</strong><span role="status">{{ statusLabel }}</span></div>
    <p class="panel-note">请求 {{ modeLabel(trace.requested_mode) }} · 实际 {{ modeLabel(trace.effective_mode) }}<template v-if="currentRound"> · 第 {{ currentRound.round }} 轮 · 累计 {{ currentRound.total_evidence_count ?? '—' }} 个证据</template></p>
    <ol v-if="ongoing" class="research-steps" aria-label="当前研究步骤">
      <li v-for="step in steps" :key="step.id" :class="{ active: trace.status === step.id }" :aria-current="trace.status === step.id ? 'step' : undefined">{{ step.label }}</li>
    </ol>
    <p v-if="trace.stop_reason" class="panel-note">停止原因：{{ stopLabel(trace.stop_reason) }}</p>
    <details class="research-details" :open="ongoing">
      <summary>{{ ongoing ? '当前计划与研究轮次' : '查看计划、查询、缺口与成本' }}</summary>
      <ol v-if="trace.plan?.length" class="research-plan">
        <li v-for="task in trace.plan" :key="task.id"><strong>{{ task.id }}</strong> {{ task.question }}<small v-if="task.depends_on?.length">依赖 {{ task.depends_on.join('、') }}</small></li>
      </ol>
      <p v-else class="panel-note">尚未返回子问题计划。</p>
      <details v-for="(round, index) in rounds" :key="round.round" class="research-round" :open="ongoing && index === rounds.length - 1">
        <summary>第 {{ round.round }} 轮 · 新增 {{ round.new_evidence_count ?? '—' }} / 累计 {{ round.total_evidence_count ?? '—' }} · {{ round.duration_ms ?? '—' }} ms</summary>
        <ul class="research-query-list"><li v-for="(query, queryIndex) in round.queries || []" :key="queryIndex"><strong>{{ query.task_id }} · {{ query.query }}</strong><span>{{ query.reason }}</span></li></ul>
        <p v-if="round.assessment" class="panel-note">已覆盖：{{ round.assessment.covered_task_ids?.join('、') || '无' }} · {{ round.assessment.sufficient ? '证据充分' : '仍有证据缺口' }}</p>
        <ul v-if="round.assessment?.missing?.length" class="research-query-list"><li v-for="(gap, gapIndex) in round.assessment.missing" :key="gapIndex"><strong>缺口 {{ gap.task_id }} · {{ gap.query }}</strong><span>{{ gap.reason }}</span></li></ul>
        <EvidenceGraph :graph="round.graph" @open-evidence="emit('open-evidence', $event)" />
        <p v-if="round.graph?.expansion_queries?.length" class="panel-note">关系扩展查询：{{ round.graph.expansion_queries.join('；') }}</p>
      </details>
      <dl class="research-costs">
        <div v-if="trace.budget"><dt>规划成本（估算）</dt><dd>{{ trace.budget.estimated_planning_tokens ?? '—' }} / {{ trace.budget.planning_token_budget ?? '—' }} tokens</dd></div>
        <div v-if="trace.budget"><dt>研究预算</dt><dd>{{ trace.budget.max_rounds ?? '—' }} 轮 · {{ trace.budget.time_budget_ms ?? '—' }} ms</dd></div>
        <div v-if="contextStats"><dt>上下文（{{ contextStats.estimator || '估算' }}）</dt><dd>{{ contextStats.estimated_tokens ?? '—' }} / {{ contextStats.token_budget ?? '—' }} tokens · 输入 {{ contextStats.input_count ?? '—' }} / 选用 {{ contextStats.selected_count ?? '—' }} / 省略 {{ contextStats.omitted_count ?? '—' }}</dd></div>
      </dl>
    </details>
    <EvidenceGraph :graph="trace.graph" @open-evidence="emit('open-evidence', $event)" />
  </section>
</template>
