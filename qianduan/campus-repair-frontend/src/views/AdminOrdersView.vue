<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../api'
import { formatTime, statusLabels, type OrderStatus, type Page } from '../utils/display'
import type { OrderSummary } from '../types/orders'
const overtime = useRoute().path === '/admin/overtime'
const router = useRouter()
const page = ref(1), pageSize = ref(20), scope = ref('active'), knownId = ref('')
const data = ref<Page<OrderSummary> | null>(null), loading = ref(false), error = ref('')
let controller: AbortController | undefined
let timer: ReturnType<typeof setInterval> | undefined
async function load(reset = false, silent = false) {
  if (silent && (loading.value || document.hidden)) return
  if (reset) page.value = 1
  controller?.abort(); const current = new AbortController(); controller = current
  loading.value = true; error.value = ''
  try { data.value = await request(overtime ? '/api/orders/overtime' : '/api/orders/pending', { query: { page: page.value, pageSize: pageSize.value, ...(overtime ? { scope: scope.value } : {}) }, signal: current.signal }) }
  catch (cause) { if (!current.signal.aborted) { data.value = null; error.value = cause instanceof Error ? cause.message : '列表加载失败' } }
  finally { if (!current.signal.aborted) loading.value = false }
}
function openKnown() {
  const id = knownId.value.trim()
  if (!/^[1-9]\d{0,18}$/.test(id) || BigInt(id) > 9223372036854775807n) { error.value = '请输入有效的工单 ID（不是工单编号）'; return }
  void router.push(`/admin/orders/${id}`)
}
function visibilityChanged() { if (document.hidden) controller?.abort(); else void load(false, true); if (document.hidden) loading.value = false }
onMounted(() => { void load(); timer = setInterval(() => { void load(false, true) }, 30000); document.addEventListener('visibilitychange', visibilityChanged) })
onBeforeUnmount(() => { controller?.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', visibilityChanged) })
</script>
<template>
  <section class="content-card">
    <div class="toolbar"><label v-if="overtime">超时范围 <el-select v-model="scope" style="width:160px" @change="load(true)"><el-option label="当前超时" value="active" /><el-option label="历史超时" value="history" /></el-select></label><el-button :loading="loading" @click="load()">刷新</el-button><span v-if="data">共 {{ data.total }} 单</span></div>
    <form class="toolbar" @submit.prevent="openKnown"><label for="known-id">通过工单 ID 查看或改派</label><input id="known-id" v-model="knownId" placeholder="输入工单 ID" inputmode="numeric" /><el-button native-type="submit">打开详情</el-button></form>
    <p class="hint">{{ overtime ? '当前超时为仍需处理且已逾期的工单；历史超时包含曾超时的已结束工单。' : '此列表仅显示待派工单。已派工单可通过已知工单 ID 打开详情。' }} 页面可见时每 30 秒更新。</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <div v-loading="loading"><el-table v-if="data" :data="data.items" empty-text="暂无符合条件的工单">
      <el-table-column label="工单编号" min-width="240"><template #default="{ row }"><RouterLink :to="`/admin/orders/${row.id}`">{{ row.orderNo }}</RouterLink><p class="hint">ID：{{ row.id }}</p></template></el-table-column>
      <el-table-column prop="category" label="分类" width="90" /><el-table-column prop="location" label="地点" min-width="140" />
      <el-table-column label="状态" width="100"><template #default="{ row }">{{ statusLabels[row.status as OrderStatus] }}</template></el-table-column>
      <el-table-column label="处理期限" min-width="240"><template #default="{ row }">{{ formatTime(row.deadline) }}</template></el-table-column>
      <el-table-column label="超时情况" min-width="120"><template #default="{ row }"><el-tag v-if="row.isCurrentlyOverdue" type="danger">当前已逾期</el-tag><el-tag v-else-if="row.isOvertime" type="warning">曾经超时</el-tag><span v-else>未超时</span></template></el-table-column>
    </el-table><p v-if="loading" role="status">正在更新列表…</p></div>
    <el-pagination v-if="data" v-model:current-page="page" v-model:page-size="pageSize" :total="data.total" :page-sizes="[10,20,50]" layout="prev, pager, next, sizes, total" @current-change="load()" @size-change="load(true)" />
  </section>
</template>
<style scoped>.toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:20px; }.hint { color:#637186; font-size:13px; line-height:1.6; }input { padding:10px; border:1px solid #c4cedc; border-radius:6px; max-width:100%; }.el-pagination { margin-top:24px; overflow-x:auto; }</style>
