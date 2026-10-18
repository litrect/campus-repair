<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError, request } from '../api'
import { formatTime, statusLabels, urgencyLabels } from '../utils/display'
import type { OrderDetail, OrderLog } from '../types/orders'
interface Worker { id:string; realName:string; skill:string|null; activeOrderCount:number; recommendationScore:number }
const id = String(useRoute().params.id)
const order = ref<OrderDetail|null>(null), logs = ref<OrderLog[]>([]), workers = ref<Worker[]>([])
const workerId = ref(''), reason = ref(''), action = ref<''|'assign'|'cancel'>('')
const loading = ref(false), saving = ref(false), error = ref(''), extraError = ref(''), image = ref('')
let controller: AbortController | undefined
const mutationController = new AbortController()
function clearImage() { if(image.value) URL.revokeObjectURL(image.value); image.value = '' }
async function load() {
  controller?.abort(); const current = new AbortController(); controller = current
  loading.value=true; error.value=''; extraError.value=''; workers.value=[]; logs.value=[]; clearImage()
  try {
    if(!/^[1-9]\d{0,18}$/.test(id) || BigInt(id)>9223372036854775807n) throw new Error('无效的工单 ID')
    const detail = await request<OrderDetail>(`/api/orders/${id}`, { signal:current.signal }); order.value=detail
    const jobs = [
      request<OrderLog[]>(`/api/orders/${id}/logs`,{signal:current.signal}).then(value=>{logs.value=value}),
      request<Worker[]>('/api/workers/available',{query:{category:detail.category},signal:current.signal}).then(value=>{workers.value=value}),
      detail.imageUrl ? request<Blob>(detail.imageUrl,{blob:true,signal:current.signal}).then(value=>{if(!current.signal.aborted) image.value=URL.createObjectURL(value)}) : Promise.resolve(),
    ]
    const results=await Promise.allSettled(jobs)
    if(!current.signal.aborted) extraError.value=results.map((result,index)=>result.status==='rejected' ? ['处理日志加载失败','维修工候选加载失败','图片加载失败'][index] : '').filter(Boolean).join('；')
  } catch(cause) { if(!current.signal.aborted) {order.value=null; error.value=cause instanceof Error?cause.message:'加载失败'} }
  finally { if(!current.signal.aborted) loading.value=false }
}
async function submit() {
  if(!order.value || !action.value || saving.value || loading.value) return
  if(!['CREATED','ASSIGNED'].includes(order.value.status)) {error.value='当前状态不允许派单或取消';return}
  if(action.value==='assign' && (!workers.value.some(worker=>worker.id===workerId.value) || workerId.value===order.value.workerId)) {error.value='请选择另一位启用的维修工';return}
  if(reason.value.length>500) {error.value='取消原因不能超过 500 字';return}
  saving.value=true; error.value=''
  try {
    await request(`/api/orders/${id}/${action.value}`,{method:'POST',body:action.value==='assign'?{workerId:workerId.value,version:order.value.version}:{reason:reason.value.trim(),version:order.value.version},signal:mutationController.signal})
    action.value=''; reason.value=''; workerId.value=''; ElMessage.success('操作成功'); await load()
  } catch(cause) {
    if(mutationController.signal.aborted) return
    const message=cause instanceof Error?cause.message:'操作失败'
    if(cause instanceof ApiError && [409,422].includes(cause.status)) {await load(); error.value=message+'。详情和候选已尝试刷新，输入已保留，请核对后再操作。'}
    else error.value=message
  } finally {saving.value=false}
}
onMounted(()=>load())
onBeforeUnmount(()=>{controller?.abort();mutationController.abort();clearImage()})
</script>
<template>
  <section class="content-card" v-loading="loading">
    <div class="toolbar"><RouterLink to="/admin/pending">待派工单</RouterLink><RouterLink to="/admin/overtime">超时预警</RouterLink><el-button :loading="loading" :disabled="saving" @click="load">刷新详情</el-button></div>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="extraError" class="form-error">{{ extraError }}，请刷新重试。</p>
    <template v-if="order">
      <dl><dt>工单编号 / ID</dt><dd>{{ order.orderNo }} / {{ order.id }}</dd><dt>状态</dt><dd>{{ statusLabels[order.status] }}</dd><dt>分类 / 紧急程度</dt><dd>{{ order.category }} / {{ urgencyLabels[order.urgency] }}</dd><dt>地点</dt><dd>{{ order.location }}</dd><dt>故障描述</dt><dd>{{ order.description }}</dd><dt>当前维修工 ID</dt><dd>{{ order.workerId || '未指派' }}</dd><dt>提交时间</dt><dd>{{ formatTime(order.createTime) }}</dd><dt>处理期限</dt><dd>{{ formatTime(order.deadline) }}</dd><dt>维修记录</dt><dd>{{ order.repairRecord || '暂无' }}</dd></dl>
      <img v-if="image" :src="image" alt="报修现场图片" />
      <div v-if="['CREATED','ASSIGNED'].includes(order.status)" class="toolbar"><el-button type="primary" :disabled="loading||saving" @click="action='assign'">{{ order.status==='ASSIGNED'?'改派':'派单' }}</el-button><el-button :disabled="loading||saving" @click="action='cancel'">取消工单</el-button></div>
      <form v-if="action" @submit.prevent="submit">
        <template v-if="action==='assign'"><h2>选择维修工</h2><p>按技能匹配和当前负载排序，可手动选择任一启用维修工。</p><el-radio-group v-model="workerId" :disabled="saving||loading"><div v-for="worker in workers" :key="worker.id" class="worker"><el-radio :value="worker.id" :disabled="worker.id===order.workerId">{{ worker.realName }}{{ worker.id===order.workerId?'（当前维修工）':'' }}</el-radio><p>技能：{{ worker.skill || '未设置' }} · 在办：{{ worker.activeOrderCount }} 单 · 推荐分：{{ worker.recommendationScore }}</p></div></el-radio-group><p v-if="!workers.length">暂无可选维修工，请刷新重试。</p></template>
        <template v-else><label for="cancel-reason">取消原因（选填）</label><textarea id="cancel-reason" v-model="reason" rows="3" maxlength="500" :disabled="saving" /></template>
        <div class="toolbar"><el-button type="primary" native-type="submit" :loading="saving" :disabled="loading||!['CREATED','ASSIGNED'].includes(order.status)">确认{{ action==='assign'?(order.status==='ASSIGNED'?'改派':'派单'):'取消工单' }}</el-button><el-button :disabled="saving" @click="action=''">返回</el-button></div>
      </form>
      <h2>处理日志</h2><el-timeline><el-timeline-item v-for="log in logs" :key="log.id" :timestamp="formatTime(log.createTime)">{{ log.fromStatus?statusLabels[log.fromStatus]+' → ':'' }}{{ statusLabels[log.toStatus] }}<p v-if="log.fromWorkerId||log.toWorkerId">维修工 ID：{{ log.fromWorkerId || '未指派' }} → {{ log.toWorkerId || '未指派' }}</p><p class="remark">{{ log.remark }}</p></el-timeline-item></el-timeline>
    </template>
  </section>
</template>
<style scoped>.toolbar {display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:16px 0 24px}dl {display:grid;grid-template-columns:140px minmax(0,1fr);gap:16px;line-height:1.7}dt {color:#637186}dd {margin:0;white-space:pre-wrap;overflow-wrap:anywhere}img {max-width:100%;max-height:360px;border-radius:8px}form {padding:20px;background:#f3f7fc;border-radius:8px}textarea {width:100%;padding:12px}h2 {font-size:20px}.worker {width:100%;padding:12px;border-bottom:1px solid #dce3ed}.worker p {margin:6px 0;color:#637186}.remark {white-space:pre-wrap}.el-radio-group {display:block}@media(max-width:500px){dl {grid-template-columns:1fr;gap:6px}dd {margin-bottom:12px}}</style>
