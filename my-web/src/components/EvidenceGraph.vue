<script setup>
import { computed } from 'vue'
const props = defineProps({ graph: Object })
const emit = defineEmits(['open-evidence'])
const edges = computed(() => props.graph?.matched_edges || [])
</script>

<template>
  <details v-if="graph?.enabled || graph?.status === 'unavailable'" class="research-details evidence-graph">
    <summary>关系证据 · {{ graph.node_count ?? '—' }} 个实体 / {{ graph.edge_count ?? '—' }} 条关系</summary>
    <p class="panel-note">关系提取自知识库中的明确陈述；路径连接不自动证明因果或关系可传递。</p>
    <p v-if="graph.status === 'unavailable'" class="panel-note" role="status">关系图不可用<template v-if="graph.reason">：{{ graph.reason }}</template>，不能据此判断知识库没有关系。</p>
    <ul v-if="edges.length" class="relation-list" aria-label="实体关系证据">
      <li v-for="(edge, index) in edges" :key="`${edge.evidence_id}-${index}`">
        <button type="button" class="relation-button" @click="emit('open-evidence', edge)">
          <span class="relation-triple"><strong>{{ edge.subject }}</strong><span>— {{ edge.predicate }} →</span><strong>{{ edge.object }}</strong></span>
          <span class="panel-note">{{ edge.source_id || edge.evidence_id }} · {{ edge.filename || '来源原文' }}</span>
          <span v-if="edge.quote" class="relation-quote">“{{ edge.quote }}”</span>
        </button>
      </li>
    </ul>
    <p v-else-if="graph.status !== 'unavailable'" class="panel-note">本次没有返回匹配关系，不生成示意图。</p>
    <details v-if="graph.paths?.length" class="research-details">
      <summary>查看证据路径 · {{ graph.paths.length }}</summary>
      <div v-for="(path, index) in graph.paths" :key="index" class="research-round">
        <p class="panel-note">{{ path.nodes?.join(' → ') }}</p>
        <button v-for="(edge, edgeIndex) in path.edges || []" :key="edgeIndex" type="button" class="evidence-link" @click="emit('open-evidence', edge)">{{ edge.subject }} — {{ edge.predicate }} → {{ edge.object }} · 查看原文</button>
      </div>
    </details>
  </details>
</template>
