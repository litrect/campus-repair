<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError, request } from '../api'
import { session } from '../auth'
import { urgencyLabels } from '../utils/display'
import { createSubmissionKey } from '../utils/submissionKey'

type Input = { category: string; location: string; description: string; urgency: string; imageUrl: string | null }
type Pending = { key: string; input: Input }
const router = useRouter()
const storageKey = `campus-repair.pending.${session.value?.user.id}`
const form = reactive<Input>({ category: '', location: '', description: '', urgency: 'NORMAL', imageUrl: null })
const pending = ref<Pending | null>(null)
const options = ref<{ categories: string[]; urgencies: string[] } | null>(null)
const loadingOptions = ref(false), uploading = ref(false), submitting = ref(false)
const error = ref(''), optionError = ref(''), preview = ref('')
const inputFile = ref<HTMLInputElement>()
const controller = new AbortController()
const locked = computed(() => !!pending.value || submitting.value)
function setPreview(blob?: Blob) {
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = blob ? URL.createObjectURL(blob) : ''
}
async function loadOptions() {
  loadingOptions.value = true; optionError.value = ''
  try { options.value = await request('/api/meta/order-options', { signal: controller.signal }) }
  catch (cause) { if (!controller.signal.aborted) optionError.value = cause instanceof Error ? cause.message : '无法加载表单选项' }
  finally { loadingOptions.value = false }
}
async function chooseImage(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || locked.value || uploading.value) return
  error.value = ''
  if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > 2097152) {
    error.value = '请选择不超过 2 MiB 的 PNG 或 JPEG 图片'
    if (inputFile.value) inputFile.value.value = ''
    return
  }
  uploading.value = true
  try {
    const body = new FormData(); body.append('file', file)
    const result = await request<{ imageUrl: string }>('/api/uploads/images', { method: 'POST', body, signal: controller.signal })
    form.imageUrl = result.imageUrl; setPreview(file)
  } catch (cause) { if (!controller.signal.aborted) error.value = cause instanceof Error ? cause.message : '上传失败' }
  finally { uploading.value = false; if (inputFile.value) inputFile.value.value = '' }
}
function removeImage() { form.imageUrl = null; setPreview() }
async function submit() {
  if (submitting.value || uploading.value || !options.value) return
  error.value = ''
  if (!pending.value) {
    const input = { ...form, category: form.category.trim(), location: form.location.trim(), description: form.description.trim() }
    if (!options.value.categories.includes(input.category) || !options.value.urgencies.includes(input.urgency)) { error.value = '请选择故障分类和紧急程度'; return }
    if (!input.location || input.location.length > 100 || !input.description || input.description.length > 500) { error.value = '地点须为 1–100 字，故障描述须为 1–500 字，且不能仅包含空格'; return }
    let key: string
    try { key = createSubmissionKey() }
    catch { error.value = '浏览器无法生成提交标识，请更换浏览器或通过 HTTPS 网址访问'; return }
    const next = { key, input }
    try { sessionStorage.setItem(storageKey, JSON.stringify(next)) }
    catch { error.value = '无法保存提交记录，请检查浏览器存储设置后重试'; return }
    pending.value = next
  }
  submitting.value = true
  try {
    const result = await request<{ id: string; orderNo: string }>('/api/orders', { method: 'POST', body: pending.value.input, headers: { 'Idempotency-Key': pending.value.key }, signal: controller.signal })
    sessionStorage.removeItem(storageKey); pending.value = null
    ElMessage.success(`报修提交成功，工单编号：${result.orderNo}`)
    await router.push({ path: '/student/orders', query: { created: result.id } })
  } catch (cause) {
    if (controller.signal.aborted) return
    error.value = cause instanceof Error ? cause.message : '提交失败'
    // Validation failures definitively did not create an order; uncertain results retain the original request.
    if (cause instanceof ApiError && [400, 403, 404, 413, 415, 422].includes(cause.status)) {
      sessionStorage.removeItem(storageKey); pending.value = null
    }
  } finally { submitting.value = false }
}
onMounted(async () => {
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null')
    if (saved && typeof saved.key === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(saved.key)
      && saved.input && ['category', 'location', 'description', 'urgency'].every(key => typeof saved.input[key] === 'string')
      && (saved.input.imageUrl === null || typeof saved.input.imageUrl === 'string')) {
      pending.value = saved; Object.assign(form, saved.input)
      if (form.imageUrl) {
        try { setPreview(await request<Blob>(form.imageUrl, { blob: true, signal: controller.signal })) }
        catch { error.value = '图片预览暂不可用，原提交图片仍保留' }
      }
    }
  } catch { sessionStorage.removeItem(storageKey) }
  await loadOptions()
})
onBeforeUnmount(() => { controller.abort(); setPreview() })
</script>

<template>
  <section class="content-card repair-form">
    <p class="form-intro">填写故障信息，我们会安排维修人员处理。带 * 的项目为必填项。</p>
    <el-alert v-if="pending" title="上一笔提交的结果尚未确认" description="已保留原始内容。请点击“重试原提交”查询或重试同一笔报修，避免重复建单。" type="warning" :closable="false" show-icon />
    <p v-if="optionError" class="form-error" role="alert">{{ optionError }} <el-button :loading="loadingOptions" @click="loadOptions">重新加载选项</el-button></p>
    <form v-loading="loadingOptions" @submit.prevent="submit">
      <fieldset :disabled="locked || uploading || !options" class="repair-fields">
        <label for="category">故障分类 *</label>
        <select id="category" v-model="form.category" required><option value="" disabled>请选择故障分类</option><option v-for="category in options?.categories" :key="category">{{ category }}</option></select>
        <label for="urgency">紧急程度 *</label>
        <select id="urgency" v-model="form.urgency" required><option v-for="urgency in options?.urgencies" :key="urgency" :value="urgency">{{ urgencyLabels[urgency as keyof typeof urgencyLabels] || urgency }}</option></select>
        <label for="location">故障地点 *</label><input id="location" v-model="form.location" required maxlength="100" placeholder="例如：A 栋宿舍 101 室" />
        <label for="description">故障描述 *</label><textarea id="description" v-model="form.description" required maxlength="500" rows="5" placeholder="请描述故障现象及需要维修的设施" /><span class="field-hint">{{ form.description.length }}/500 字</span>
        <label for="image">现场图片（选填）</label><input id="image" ref="inputFile" type="file" accept="image/png,image/jpeg" @change="chooseImage" /><p class="field-hint">最多一张 PNG/JPEG 图片，大小不超过 2 MiB。</p>
      </fieldset>
      <p v-if="uploading" role="status">图片上传中，请稍候…</p>
      <div v-if="preview" class="image-preview"><img :src="preview" alt="报修现场图片预览" /><el-button v-if="!locked" :disabled="uploading" @click="removeImage">移除图片</el-button></div>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <el-button native-type="submit" type="primary" :loading="submitting" :disabled="uploading || !options || loadingOptions">{{ pending ? '重试原提交' : '提交报修' }}</el-button>
    </form>
  </section>
</template>

<style scoped>
.repair-form { max-width: 780px; }
.form-intro { color: #526072; line-height: 1.7; margin-top: 0; }
.repair-fields { border: 0; padding: 0; margin: 0 0 24px; min-width: 0; }
input:not([type=file]), select, textarea { display: block; width: 100%; padding: 12px; border: 1px solid #c4cedc; border-radius: 7px; color: #1f2937; background: #fff; }
input:focus, select:focus, textarea:focus { outline: 2px solid #2468d8; outline-offset: 2px; }
fieldset:disabled { opacity: .7; }
.field-hint { display: block; color: #637186; font-size: 13px; margin-top: 8px; }
.image-preview { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.image-preview img { max-width: 100%; width: 280px; max-height: 240px; object-fit: contain; border-radius: 8px; }
</style>
