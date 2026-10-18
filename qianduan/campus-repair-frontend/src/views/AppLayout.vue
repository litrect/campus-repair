<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearSession, roleLabels, session } from '../auth'
import { navigation } from '../router'
const route = useRoute(), router = useRouter()
const items = computed(() => navigation.filter(item => item.role === session.value?.user.role))
function logout() { clearSession(); void router.replace('/login') }
</script>
<template>
  <div v-if="session" class="workspace">
    <header class="topbar"><RouterLink class="brand" to="/">校园报修系统</RouterLink><div class="account"><span>{{ session.user.realName }} · {{ roleLabels[session.user.role] }}</span><el-button @click="logout">退出登录</el-button></div></header>
    <div class="workspace-body"><nav class="sidebar" aria-label="主要导航"><RouterLink v-for="item in items" :key="item.path" :to="item.path">{{ item.title }}</RouterLink></nav>
      <main class="page-content"><h1>{{ route.meta.title }}</h1><RouterView :key="route.path" /></main>
    </div>
  </div>
</template>
