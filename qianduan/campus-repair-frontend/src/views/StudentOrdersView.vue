<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { request } from '../api'
import { useRoute } from 'vue-router'
import { formatTime, statusLabels, urgencyLabels, type OrderStatus, type Page } from '../utils/display'
import type { OrderSummary } from '../types/orders'
const status = ref<OrderStatus | ''>(''), page = ref(1), pageSize = ref(20)
const isWorker = useRoute().meta.role === 'WORKER'
const listPath = isWorker ? '/worker/orders' : '/student/orders'
const data = ref<Page<OrderSummary> | null>(null), loading = ref(false), error = ref('')
let controller: AbortController | undefined
let timer: ReturnType<typeof setInterval> | undefined
async function load(reset = false, silent = false) {
  if (silent && (loading.value || document.hidden)) return
  if (reset) page.value = 1
  controller?.abort(); const current = new AbortController(); controller = current
  loading.value = true; error.value = ''
  if (!silent) data.value = null
  try { data.value = await request(isWorker ? '/api/orders/assigned-to-me' : '/api/orders/my', { query: { page: page.value, pageSize: pageSize.value, status: status.value }, signal: current.signal }) }
  catch (cause) { if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '列表加载失败' }
  finally { if (!current.signal.aborted) loading.value = false }
}
function onVisibilityChange() {
  if (document.hidden) { controller?.abort(); loading.value = false }
  else void load(false, true)
}
onMounted(() => {
  void load()
  timer = setInterval(() => { void load(false, true) }, 30000)
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onBeforeUnmount(() => {
  controller?.abort()
  clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>
<template>
  <section class="content-card">
    <div class="list-toolbar"><label>工单状态 <el-select v-model="status" style="width: 150px" @change="load(true)"><el-option label="全部状态" value="" /><el-option v-for="(label, value) in statusLabels" :key="value" :label="label" :value="value" /></el-select></label><el-button :loading="loading" @click="load()">刷新</el-button><RouterLink v-if="!isWorker" to="/student/create">提交新报修</RouterLink></div>
    <p class="poll-hint">页面可见时每 30 秒更新一次{{ isWorker ? '待接单工单' : '待确认工单' }}。</p>
    <p v-if="error" class="form-error" role="alert">{{ error }} <el-button @click="load()">重试</el-button></p>
    <div v-loading="loading" :aria-busy="loading">
      <el-table v-if="data" :data="data.items" empty-text="暂无符合条件的报修工单" style="width: 100%">
        <el-table-column label="工单编号" min-width="240"><template #default="{ row }"><RouterLink :to="`${listPath}/${row.id}`">{{ row.orderNo }}</RouterLink></template></el-table-column>
        <el-table-column prop="category" label="分类" width="90" /><el-table-column prop="location" label="地点" min-width="150" />
        <el-table-column label="状态" width="110"><template #default="{ row }">{{ statusLabels[row.status as OrderStatus] }}</template></el-table-column>
        <el-table-column label="紧急程度" width="110"><template #default="{ row }">{{ urgencyLabels[row.urgency as keyof typeof urgencyLabels] }}</template></el-table-column>
        <el-table-column label="提交时间" min-width="240"><template #default="{ row }">{{ formatTime(row.createTime) }}</template></el-table-column>
      </el-table>
      <p v-if="loading" role="status">正在加载报修列表…</p>
    </div>
    <el-pagination v-if="data" v-model:current-page="page" v-model:page-size="pageSize" :total="data.total" :page-sizes="[10, 20, 50]" layout="prev, pager, next, sizes, total" @current-change="load()" @size-change="load(true)" />
  </section>
</template>
<style scoped>.list-toolbar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }.poll-hint { color:#637186; font-size:13px; margin:0 0 20px; }.el-pagination { margin-top: 24px; overflow-x: auto; }</style>
