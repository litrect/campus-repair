<script setup lang="ts">
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { request } from '../api'
import { statusLabels, type OrderStatus } from '../utils/display'
interface Statistics { metric:'created'|'completed'; groupBy:'category'|'status'|'worker'|'day'; total:number; buckets:{key:string|null;count:number;workerName?:string|null}[] }
const filters=reactive({metric:'created',groupBy:'category',from:'',through:'',category:'',status:''})
const categories=ref<string[]>([]), optionError=ref(''), error=ref(''), loading=ref(false), data=ref<Statistics|null>(null)
let controller:AbortController|undefined
const optionsController=new AbortController()
function endExclusive(day:string) {
  const date=new Date(`${day}T00:00:00Z`); date.setUTCDate(date.getUTCDate()+1)
  return date.toISOString().slice(0,10)
}
async function loadOptions() {
  optionError.value=''
  try { categories.value=(await request<{categories:string[]}>('/api/meta/order-options',{signal:optionsController.signal})).categories }
  catch(cause) {if(!optionsController.signal.aborted) optionError.value=cause instanceof Error?cause.message:'分类加载失败'}
}
async function load() {
  error.value=''
  if(filters.from && filters.through && filters.from>filters.through) {error.value='开始日期不能晚于结束日期';return}
  controller?.abort(); const current=new AbortController();controller=current;loading.value=true;data.value=null
  try {
    data.value=await request('/api/stats/orders',{query:{metric:filters.metric,groupBy:filters.groupBy,from:filters.from,to:filters.through?endExclusive(filters.through):undefined,category:filters.category,status:filters.status},signal:current.signal})
  } catch(cause) {if(!current.signal.aborted) error.value=cause instanceof Error?cause.message:'统计加载失败'}
  finally {if(!current.signal.aborted) loading.value=false}
}
function label(bucket:Statistics['buckets'][number]) {
  if(data.value?.groupBy==='status') return statusLabels[bucket.key as OrderStatus] || bucket.key || '未知状态'
  if(data.value?.groupBy==='worker') return bucket.workerName || (bucket.key ? `维修工 ID：${bucket.key}`:'未指派')
  return bucket.key || '未分类'
}
onMounted(()=>{void loadOptions();void load()})
onBeforeUnmount(()=>{controller?.abort();optionsController.abort()})
</script>
<template>
  <section class="content-card">
    <form class="filters" @submit.prevent="load">
      <label>统计指标<el-select v-model="filters.metric"><el-option label="提交量" value="created"/><el-option label="确认关闭量" value="completed"/></el-select></label>
      <label>分组方式<el-select v-model="filters.groupBy"><el-option label="故障分类" value="category"/><el-option label="工单状态" value="status"/><el-option label="维修工" value="worker"/><el-option label="日期" value="day"/></el-select></label>
      <label>开始日期<input v-model="filters.from" type="date"/></label><label>结束日期（含当天）<input v-model="filters.through" type="date"/></label>
      <label>故障分类<el-select v-model="filters.category"><el-option label="全部分类" value=""/><el-option v-for="category in categories" :key="category" :label="category" :value="category"/></el-select></label>
      <label>工单状态<el-select v-model="filters.status"><el-option label="全部状态" value=""/><el-option v-for="(text,value) in statusLabels" :key="value" :label="text" :value="value"/></el-select></label>
      <el-button native-type="submit" type="primary" :loading="loading">查询统计</el-button>
    </form>
    <p class="hint">提交量按提交时间统计；确认关闭量仅统计学生确认后的工单。日期按北京时间，结束日期包含当天。</p>
    <p v-if="optionError" class="form-error">{{ optionError }} <el-button @click="loadOptions">重载分类</el-button></p><p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <div v-loading="loading"><template v-if="data"><p class="total">{{ data.metric==='created'?'提交量':'确认关闭量' }}：<strong>{{ data.total }}</strong> 单</p>
      <el-table :data="data.buckets" empty-text="所选条件下暂无数据"><el-table-column label="分组" min-width="180"><template #default="{row}">{{ label(row) }}</template></el-table-column><el-table-column prop="count" label="工单数量" width="120"/><el-table-column label="占比" min-width="160"><template #default="{row}"><el-progress :percentage="data.total?Math.round(row.count/data.total*1000)/10:0"/></template></el-table-column></el-table>
    </template><p v-if="loading" role="status">正在查询统计…</p></div>
  </section>
</template>
<style scoped>.filters {display:flex;flex-wrap:wrap;gap:16px;align-items:end}.filters label {display:flex;flex-direction:column;gap:8px;margin:0;width:190px;font-weight:400}input {padding:8px;border:1px solid #c4cedc;border-radius:5px;min-height:32px}.hint {color:#637186;line-height:1.7;font-size:13px}.total {font-size:20px;margin:28px 0}.total strong {color:#2468d8;font-size:30px}</style>
