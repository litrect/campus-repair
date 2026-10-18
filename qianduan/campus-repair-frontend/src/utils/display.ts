export type OrderStatus = 'CREATED' | 'ASSIGNED' | 'PROCESSING' | 'DONE' | 'CLOSED' | 'CANCELLED'
export interface Page<T> { items: T[]; total: number; page: number; pageSize: number }
export const statusLabels: Record<OrderStatus, string> = { CREATED: '待派单', ASSIGNED: '待接单', PROCESSING: '维修中', DONE: '待确认', CLOSED: '已关闭', CANCELLED: '已取消' }
export const urgencyLabels = { HIGH: '紧急', NORMAL: '普通', LOW: '低优先级' }
export function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date) + '（北京时间）'
}
