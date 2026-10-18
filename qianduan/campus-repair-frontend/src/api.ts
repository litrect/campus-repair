import { clearSession, validSession, type LoginData } from './auth'
export class ApiError extends Error {
  constructor(message: string, public status = 0, public code = status) { super(message); this.name = 'ApiError' }
}
let expired = () => {}
export function onUnauthorized(handler: () => void) { expired = handler }
export async function request<T>(path: string, options: {
  method?: string; body?: unknown; query?: Record<string, string | number | boolean | null | undefined>; headers?: Record<string, string>; anonymous?: boolean; signal?: AbortSignal; blob?: boolean
} = {}): Promise<T> {
  if (!path.startsWith('/api/') || /[?#]|\.\./.test(path)) throw new ApiError('无效的接口路径')
  const url = new URL(path, location.origin)
  Object.entries(options.query || {}).forEach(([key, value]) => { if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value)) })
  const headers = new Headers(options.headers)
  if (!options.anonymous) {
    const current = validSession()
    if (!current) { expired(); throw new ApiError('登录已过期，请重新登录', 401) }
    headers.set('Authorization', `Bearer ${current.token}`)
  }
  let body: BodyInit | undefined
  if (options.body instanceof FormData) body = options.body
  else if (options.body !== undefined) { headers.set('Content-Type', 'application/json'); body = JSON.stringify(options.body) }
  let response: Response
  try { response = await fetch(url, { method: options.method || 'GET', headers, body, signal: options.signal }) }
  catch (cause) {
    if (cause instanceof Error && cause.name === 'AbortError') throw cause
    throw new ApiError('网络连接失败，操作可能已成功，请刷新查询后再决定是否重试')
  }
  if (response.status === 401 && !options.anonymous) { clearSession(); expired() }
  if (options.blob && response.ok) return await response.blob() as T
  let payload
  try { payload = await response.json() } catch { throw new ApiError('服务响应异常，请稍后刷新查询', response.status) }
  if (!response.ok || payload.code !== 0) {
    const messages: Record<number, string> = { 400: '参数有误，请检查输入', 401: options.anonymous ? '账号或密码错误' : '登录已过期，请重新登录', 403: '您无权执行此操作', 404: '内容不存在或不可访问', 409: '内容已发生变化，请刷新后重试', 413: '图片不能超过 2 MiB', 415: '请求格式错误', 422: '业务条件不满足，请刷新可选项', 500: '服务异常，请先刷新查询操作结果', 503: '服务暂不可用，请稍后重试' }
    throw new ApiError(payload.message || messages[response.status] || '请求失败', response.status, payload.code)
  }
  return payload.data as T
}
export const api = { login: (username: string, password: string) => request<LoginData>('/api/auth/login', { method: 'POST', anonymous: true, body: { username, password } }) }
