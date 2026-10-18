import { createRouter, createWebHashHistory } from 'vue-router'
import type { Component } from 'vue'
import { home, validSession, type Role } from './auth'
import { onUnauthorized } from './api'
export const navigation: { path: string; title: string; role: Role }[] = [
  { path: '/student/create', title: '提交报修', role: 'STUDENT' },
  { path: '/student/orders', title: '我的报修', role: 'STUDENT' },
  { path: '/worker/orders', title: '我的维修工单', role: 'WORKER' },
  { path: '/admin/pending', title: '待派工单', role: 'ADMIN' },
  { path: '/admin/overtime', title: '超时预警', role: 'ADMIN' },
  { path: '/admin/statistics', title: '工单统计', role: 'ADMIN' },
  { path: '/admin/evaluations', title: '评价汇总', role: 'ADMIN' },
]
const pageComponents: Record<string, () => Promise<{ default: Component }>> = {
  '/student/create': () => import('./views/CreateOrderView.vue'),
  '/student/orders': () => import('./views/StudentOrdersView.vue'),
  '/worker/orders': () => import('./views/StudentOrdersView.vue'),
  '/admin/pending': () => import('./views/AdminOrdersView.vue'),
  '/admin/overtime': () => import('./views/AdminOrdersView.vue'),
  '/admin/statistics': () => import('./views/StatisticsView.vue'),
  '/admin/evaluations': () => import('./views/EvaluationsView.vue'),
}
export const router = createRouter({ history: createWebHashHistory(), routes: [
  { path: '/login', component: () => import('./views/LoginView.vue') },
  { path: '/', component: () => import('./views/AppLayout.vue'), children: [
    ...navigation.map(item => ({ path: item.path.slice(1), component: pageComponents[item.path], meta: { role: item.role, title: item.title } })),
    { path: 'student/orders/:id', component: () => import('./views/StudentDetailView.vue'), meta: { role: 'STUDENT', title: '报修详情' } },
    { path: 'worker/orders/:id', component: () => import('./views/StudentDetailView.vue'), meta: { role: 'WORKER', title: '维修工单详情' } },
    { path: 'admin/orders/:id', component: () => import('./views/AdminDetailView.vue'), meta: { role: 'ADMIN', title: '管理工单详情' } },
  ] },
  { path: '/:pathMatch(.*)*', redirect: '/' },
] })
router.beforeEach(to => {
  const current = validSession()
  if (to.path === '/login') return current ? home(current.user.role) : true
  if (!current) return '/login'
  if (to.path === '/' || (to.meta.role && to.meta.role !== current.user.role)) return home(current.user.role)
  return true
})
onUnauthorized(() => { void router.replace('/login') })
