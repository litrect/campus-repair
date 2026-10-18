<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { home, saveSession } from '../auth'
const router = useRouter()
const username = ref(''), password = ref(''), error = ref('')
const loading = ref(false)
async function submit() {
  if (loading.value) return
  error.value = ''
  if (!username.value.trim() || !password.value) { error.value = '请输入账号和密码'; return }
  loading.value = true
  try { const data = await api.login(username.value.trim(), password.value); saveSession(data); await router.replace(home(data.user.role)) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '登录失败，请稍后重试' }
  finally { loading.value = false }
}
</script>
<template>
  <main class="app-shell"><section class="welcome-card login-card">
    <p class="eyebrow">校园后勤服务</p><h1>校园报修系统</h1><p>登录后，查看和处理您的校园报修事务。</p>
    <form @submit.prevent="submit">
      <label for="username">账号</label><el-input id="username" v-model="username" autocomplete="username" maxlength="50" placeholder="请输入账号" :disabled="loading" />
      <label for="password">密码</label><el-input id="password" v-model="password" type="password" autocomplete="current-password" show-password placeholder="请输入密码" :disabled="loading" />
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <el-button class="login-submit" type="primary" native-type="submit" :loading="loading">登录</el-button>
    </form>
  </section></main>
</template>
