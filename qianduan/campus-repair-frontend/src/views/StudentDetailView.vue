<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError, request } from '../api'
import { formatTime, statusLabels, urgencyLabels } from '../utils/display'
import type { OrderDetail, OrderLog } from '../types/orders'
const route = useRoute()
const isWorker = route.meta.role === 'WORKER'
const id = String(route.params.id)
const order = ref<OrderDetail | null>(null), logs = ref<OrderLog[]>([])
const loading = ref(false), saving = ref(false), error = ref(''), logError = ref(''), imageError = ref(''), image = ref('')
const action = ref<'' | 'cancel' | 'confirm' | 'reject' | 'evaluate' | 'accept' | 'finish'>('')
const repairRecord = ref('')
const reason = ref(''), content = ref(''), score = ref(5)
let currentController: AbortController | undefined
const actionController = new AbortController()
const eventLabels: Record<string, string> = { CREATE: '提交报修', ASSIGN: '派单', REASSIGN: '改派', ACCEPT: '接单', FINISH: '提交维修结果', CONFIRM: '确认完成', REJECT: '驳回维修结果', CANCEL: '取消报修', OVERTIME: '超时标记' }
function clearImage() { if (image.value) URL.revokeObjectURL(image.value); image.value = '' }
async function load() {
  currentController?.abort(); const controller = new AbortController(); currentController = controller
  loading.value = true; error.value = ''; logError.value = ''; imageError.value = ''; clearImage()
  try {
    if (!/^[1-9]\d{0,18}$/.test(id) || BigInt(id) > 9223372036854775807n) throw new Error('工单编号无效')
    order.value = await request<OrderDetail>(`/api/orders/${id}`, { signal: controller.signal })
    await Promise.all([
      request<OrderLog[]>(`/api/orders/${id}/logs`, { signal: controller.signal }).then(value => { logs.value = value }).catch(cause => { if (!controller.signal.aborted) logError.value = cause instanceof Error ? cause.message : '日志加载失败' }),
      order.value.imageUrl ? request<Blob>(order.value.imageUrl, { blob: true, signal: controller.signal }).then(value => { if (!controller.signal.aborted) image.value = URL.createObjectURL(value) }).catch(() => { if (!controller.signal.aborted) imageError.value = '现场图片加载失败，请刷新重试' }) : Promise.resolve(),
    ])
    return true
  } catch (cause) {
    if (!controller.signal.aborted) { order.value = null; logs.value = []; error.value = cause instanceof Error ? cause.message : '详情加载失败' }
    return false
  } finally { if (!controller.signal.aborted) loading.value = false }
}
async function submit() {
  if (!order.value || !action.value || saving.value || loading.value) return
  error.value = ''
  const allowed = isWorker
    ? (action.value === 'accept' && order.value.status === 'ASSIGNED') || (action.value === 'finish' && order.value.status === 'PROCESSING')
    : (action.value === 'cancel' && order.value.status === 'CREATED') || (['confirm', 'reject'].includes(action.value) && order.value.status === 'DONE') || (action.value === 'evaluate' && order.value.status === 'CLOSED' && !order.value.evaluation)
  if (!allowed) { error.value = '当前状态不支持此操作，请刷新详情'; return }
  if (action.value === 'finish' && (!repairRecord.value.trim() || repairRecord.value.trim().length > 500)) { error.value = '请填写 1–500 字的维修记录'; return }
  if (action.value === 'reject' && (!reason.value.trim() || reason.value.trim().length > 500)) { error.value = '请填写 1–500 字的驳回原因'; return }
  if (reason.value.length > 500 || content.value.length > 300) { error.value = '输入内容超过字数限制'; return }
  saving.value = true
  const selected = action.value
  const body = selected === 'evaluate' ? { score: score.value, content: content.value.trim() } : { version: order.value.version, ...(['cancel', 'reject'].includes(selected) ? { reason: reason.value.trim() } : {}), ...(selected === 'finish' ? { repairRecord: repairRecord.value.trim() } : {}) }
  try {
    await request(`/api/orders/${id}/${selected}`, { method: 'POST', body, signal: actionController.signal })
    action.value = ''; reason.value = ''; content.value = ''; repairRecord.value = ''; ElMessage.success('操作成功'); await load()
  } catch (cause) {
    if (actionController.signal.aborted) return
    const message = cause instanceof Error ? cause.message : '操作失败'
    if (cause instanceof ApiError && cause.status === 409) {
      await load(); error.value = `${message}。已尝试刷新详情，输入已保留，请核对当前状态后决定下一步。`
    } else error.value = message
  } finally { saving.value = false }
}
onMounted(() => load())
onBeforeUnmount(() => { currentController?.abort(); actionController.abort(); clearImage() })
</script>
<template>
  <section class="content-card" v-loading="loading">
    <div class="detail-toolbar"><RouterLink :to="isWorker ? '/worker/orders' : '/student/orders'">返回工单列表</RouterLink><el-button :disabled="saving" :loading="loading" @click="load()">刷新详情</el-button></div>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <template v-if="order">
      <dl class="details"><dt>工单编号</dt><dd>{{ order.orderNo }}</dd><dt>当前状态</dt><dd>{{ statusLabels[order.status] }}</dd><dt>分类 / 紧急程度</dt><dd>{{ order.category }} / {{ urgencyLabels[order.urgency] }}</dd><dt>地点</dt><dd>{{ order.location }}</dd><dt>故障描述</dt><dd class="plain-text">{{ order.description }}</dd><dt>提交时间</dt><dd>{{ formatTime(order.createTime) }}</dd><dt>处理期限</dt><dd>{{ formatTime(order.deadline) }}</dd><dt>超时情况</dt><dd>{{ order.isCurrentlyOverdue ? '当前已逾期' : order.isOvertime ? '曾经超时' : '未超时' }}</dd><dt>维修记录</dt><dd class="plain-text">{{ order.repairRecord || '暂无维修记录' }}</dd><dt>维修完成时间</dt><dd>{{ formatTime(order.finishTime) }}</dd><dt>关闭时间</dt><dd>{{ formatTime(order.closeTime) }}</dd></dl>
      <img v-if="image" class="site-image" :src="image" alt="报修现场图片" /><p v-if="imageError" class="form-error">{{ imageError }}</p>
      <div class="detail-toolbar">
        <el-button v-if="isWorker && order.status === 'ASSIGNED'" type="primary" :disabled="saving || loading" @click="action = 'accept'">接单</el-button>
        <el-button v-if="isWorker && order.status === 'PROCESSING'" type="primary" :disabled="saving || loading" @click="action = 'finish'">填写维修结果</el-button>
        <el-button v-if="!isWorker && order.status === 'CREATED'" :disabled="saving || loading" @click="action = 'cancel'">取消报修</el-button>
        <template v-if="!isWorker && order.status === 'DONE'"><el-button type="primary" :disabled="saving || loading" @click="action = 'confirm'">确认修好</el-button><el-button :disabled="saving || loading" @click="action = 'reject'">未修好，驳回</el-button></template>
        <el-button v-if="!isWorker && order.status === 'CLOSED' && !order.evaluation" type="primary" :disabled="saving || loading" @click="action = 'evaluate'">评价本次维修</el-button>
      </div>
      <form v-if="action" class="action-form" @submit.prevent="submit">
        <p v-if="action === 'accept'">确认接手此工单？接单后请完成维修并提交处理记录。</p>
        <template v-if="action === 'finish'"><label for="repair-record">维修记录（必填）</label><textarea id="repair-record" v-model="repairRecord" maxlength="500" rows="5" :disabled="saving" placeholder="请填写故障原因、维修措施与检查结果" /><p>{{ repairRecord.length }}/500 字。提交后等待学生确认；如被驳回，请重新维修并填写本次记录。</p></template>
        <p v-if="action === 'confirm'">确认设施已修复？确认后工单将关闭，您可以评价本次维修。</p>
        <template v-if="action === 'cancel' || action === 'reject'"><label for="reason">{{ action === 'reject' ? '驳回原因（必填）' : '取消原因（选填）' }}</label><textarea id="reason" v-model="reason" maxlength="500" rows="3" :disabled="saving" /></template>
        <template v-if="action === 'evaluate'"><p>评价提交后不可修改，每个工单只能评价一次。</p><label for="score">评分</label><select id="score" v-model.number="score" :disabled="saving"><option v-for="n in 5" :key="n" :value="n">{{ n }} 分</option></select><label for="content">评价内容（选填）</label><textarea id="content" v-model="content" maxlength="300" rows="3" :disabled="saving" /></template>
        <div class="detail-toolbar"><el-button native-type="submit" type="primary" :loading="saving" :disabled="loading || (action === 'accept' ? order.status !== 'ASSIGNED' : action === 'finish' ? order.status !== 'PROCESSING' : action === 'evaluate' ? order.status !== 'CLOSED' || !!order.evaluation : action === 'cancel' ? order.status !== 'CREATED' : order.status !== 'DONE')">确认提交</el-button><el-button :disabled="saving" @click="action = ''">返回</el-button></div>
      </form>
      <template v-if="order.evaluation"><h2>{{ isWorker ? '学生评价' : '我的评价' }}</h2><p>{{ order.evaluation.score }} 分 · {{ formatTime(order.evaluation.createTime) }}</p><p class="plain-text">{{ order.evaluation.content || '未填写评价内容' }}</p></template>
      <h2>处理日志</h2><p v-if="logError" class="form-error">{{ logError }}</p>
      <el-timeline v-else><el-timeline-item v-for="log in logs" :key="log.id" :timestamp="formatTime(log.createTime)"><strong>{{ eventLabels[log.eventType] || log.eventType }}</strong><p>{{ log.fromStatus ? statusLabels[log.fromStatus] + ' → ' : '' }}{{ statusLabels[log.toStatus] }}</p><p v-if="log.remark" class="plain-text">{{ log.remark }}</p></el-timeline-item></el-timeline>
    </template>
  </section>
</template>
<style scoped>
.detail-toolbar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 12px 0 24px; }
.details { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 16px; line-height: 1.7; }
dt { color: #637186; } dd { margin: 0; overflow-wrap: anywhere; }.plain-text { white-space: pre-wrap; overflow-wrap: anywhere; }
.site-image { max-width: 100%; max-height: 360px; border-radius: 8px; }.action-form { background: #f3f7fc; padding: 20px; border-radius: 8px; }
textarea { width: 100%; padding: 12px; border: 1px solid #c4cedc; border-radius: 7px; } select { padding: 10px; } h2 { font-size: 20px; margin-top: 32px; }
@media(max-width: 500px) { .details { grid-template-columns: 1fr; gap: 6px; } dd { margin-bottom: 12px; } }
</style>
