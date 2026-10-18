import { shallowRef } from 'vue'
export type Role = 'STUDENT' | 'WORKER' | 'ADMIN'
export interface LoginData { token: string; expiresIn: number; user: { id: string; realName: string; role: Role } }
type Session = Omit<LoginData, 'expiresIn'> & { expiresAt: number }
const key = 'campus-repair.session'
function restore(): Session | null {
  try {
    const data = JSON.parse(sessionStorage.getItem(key) || 'null')
    if (data && typeof data.token === 'string' && data.token && Number.isFinite(data.expiresAt) && data.expiresAt > Date.now() && typeof data.user?.id === 'string' && typeof data.user.realName === 'string' && ['STUDENT', 'WORKER', 'ADMIN'].includes(data.user.role)) return data
  } catch { /* Invalid storage requires login. */ }
  sessionStorage.removeItem(key)
  return null
}
export const session = shallowRef<Session | null>(restore())
export function clearSession() { sessionStorage.removeItem(key); session.value = null }
export function saveSession(data: LoginData) {
  const next = { token: data.token, user: data.user, expiresAt: Date.now() + data.expiresIn * 1000 }
  sessionStorage.setItem(key, JSON.stringify(next)); session.value = next
}
export function validSession() { if (session.value && session.value.expiresAt <= Date.now()) clearSession(); return session.value }
export const roleLabels = { STUDENT: '学生', WORKER: '维修工', ADMIN: '管理员' }
export function home(role: Role) { return role === 'STUDENT' ? '/student/orders' : role === 'WORKER' ? '/worker/orders' : '/admin/pending' }
