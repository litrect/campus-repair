<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { request } from '../api'
import { formatTime, type Page } from '../utils/display'
interface Item { id:string;orderId:string;workerId:string|null;score:number;content:string|null;createTime:string }
interface Summary extends Page<Item> {workerId:string|null;averageScore:number|null;evaluationCount:number}
const workers=ref<{id:string;realName:string}[]>([]), workerId=ref(''), page=ref(1), pageSize=ref(20)
const data=ref<Summary|null>(null), error=ref(''), workerError=ref(''), loading=ref(false)
let controller:AbortController|undefined
const workerController=new AbortController()
async function loadWorkers() {
  workerError.value=''
  try {workers.value=await request('/api/workers/available',{signal:workerController.signal})}
  catch(cause) {if(!workerController.signal.aborted) workerError.value=cause instanceof Error?cause.message:'维修工列表加载失败'}
}
async function load(reset=false) {
  if(reset) page.value=1
  if(workerId.value && (!/^[1-9]\d{0,18}$/.test(workerId.value)||BigInt(workerId.value)>9223372036854775807n)) {error.value='请选择维修工或输入有效的维修工 ID';return}
  controller?.abort();const current=new AbortController();controller=current;loading.value=true;error.value='';data.value=null
  try {data.value=await request('/api/stats/evaluations',{query:{workerId:workerId.value,page:page.value,pageSize:pageSize.value},signal:current.signal})}
  catch(cause) {if(!current.signal.aborted) error.value=cause instanceof Error?cause.message:'评价加载失败'}
  finally {if(!current.signal.aborted) loading.value=false}
}
function workerName(id:string|null) {return workers.value.find(worker=>worker.id===id)?.realName || (id?`维修工 ID：${id}`:'未指派')}
onMounted(()=>{void loadWorkers();void load()})
onBeforeUnmount(()=>{controller?.abort();workerController.abort()})
</script>
<template>
  <section class="content-card">
    <form class="toolbar" @submit.prevent="load(true)"><label>维修工 <el-select v-model="workerId" clearable filterable allow-create default-first-option placeholder="全部维修工或输入 ID" style="width:240px"><el-option v-for="worker in workers" :key="worker.id" :label="`${worker.realName}（${worker.id}）`" :value="worker.id"/></el-select></label><el-button native-type="submit" type="primary" :loading="loading">查询评价</el-button></form>
    <p class="hint">下拉列表提供当前启用的维修工，也可输入历史维修工 ID。未评价工单不计为 0 分。</p>
    <p v-if="workerError" class="form-error">{{ workerError }} <el-button @click="loadWorkers">重载维修工</el-button></p><p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <div v-loading="loading"><template v-if="data"><div class="summary"><p>平均评分 <strong>{{ data.averageScore===null?'暂无评价':data.averageScore.toFixed(2)+' 分' }}</strong></p><p>评价数量 <strong>{{ data.evaluationCount }} 条</strong></p></div>
      <el-table :data="data.items" empty-text="暂无评价"><el-table-column label="工单" min-width="130"><template #default="{row}"><RouterLink :to="`/admin/orders/${row.orderId}`">工单 ID：{{ row.orderId }}</RouterLink></template></el-table-column><el-table-column label="维修工" min-width="150"><template #default="{row}">{{ workerName(row.workerId) }}</template></el-table-column><el-table-column prop="score" label="评分" width="80"/><el-table-column label="评价内容" min-width="220"><template #default="{row}"><span class="comment">{{ row.content || '未填写内容' }}</span></template></el-table-column><el-table-column label="评价时间" min-width="240"><template #default="{row}">{{ formatTime(row.createTime) }}</template></el-table-column></el-table>
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="data.total" :page-sizes="[10,20,50]" layout="prev, pager, next, sizes, total" @current-change="load()" @size-change="load(true)"/>
    </template><p v-if="loading" role="status">正在查询评价…</p></div>
  </section>
</template>
<style scoped>.toolbar {display:flex;gap:16px;align-items:center;flex-wrap:wrap}.hint {font-size:13px;line-height:1.7;color:#637186}.summary {display:flex;gap:40px;flex-wrap:wrap;margin:24px 0}.summary strong {display:block;font-size:25px;color:#2468d8;margin-top:8px}.comment {white-space:pre-wrap;overflow-wrap:anywhere}.el-pagination {margin-top:24px;overflow-x:auto}</style>
