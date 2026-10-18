export type ID = string;
export type Role = 'STUDENT' | 'WORKER' | 'ADMIN';
export type OrderStatus = 'CREATED' | 'ASSIGNED' | 'PROCESSING' | 'DONE' | 'CLOSED' | 'CANCELLED';
export type Urgency = 'HIGH' | 'NORMAL' | 'LOW';
export type EventType = 'CREATE' | 'ASSIGN' | 'REASSIGN' | 'ACCEPT' | 'FINISH' | 'CONFIRM' | 'REJECT' | 'CANCEL' | 'OVERTIME';
export interface ApiSuccess<T> { code: 0; message: string; data: T }
export interface ApiFailure { code: number; message: string; data: null }
export interface Page<T> { items: T[]; total: number; page: number; pageSize: number }
export interface User { id: ID; realName: string; role: Role }
export interface LoginData { token: string; expiresIn: number; user: User }
export interface OrderSummary {
  id: ID; orderNo: string; category: string; location: string; urgency: Urgency;
  status: OrderStatus; workerId: ID | null; createTime: string; deadline: string | null;
  isOvertime: boolean; isCurrentlyOverdue: boolean; version: number;
}
export interface Evaluation { id: ID; score: number; content: string | null; createTime: string }
export interface OrderDetail extends OrderSummary {
  description: string; imageUrl: string | null; repairRecord: string | null; studentId: ID;
  assignTime: string | null; acceptTime: string | null; finishTime: string | null;
  closeTime: string | null; evaluation: Evaluation | null;
}
export interface OrderLog {
  id: ID; eventType: EventType; fromStatus: OrderStatus | null; toStatus: OrderStatus;
  orderVersion: number; operatorId: ID | null; fromWorkerId: ID | null;
  toWorkerId: ID | null; remark: string | null; createTime: string;
}
export interface WorkerCandidate {
  id: ID; realName: string; skill: string | null; activeOrderCount: number; recommendationScore: number;
}
export interface CreateOrderInput {
  category: string; location: string; description: string; urgency?: Urgency; imageUrl?: string | null;
}
export interface CreatedOrder { id: ID; orderNo: string; status: OrderStatus; version: number }
export interface ActionResult { id: ID; status: OrderStatus; version: number; workerId?: ID }
export interface EvaluationItem extends Evaluation { orderId: ID; workerId: ID | null }
export interface EvaluationSummary extends Page<EvaluationItem> {
  workerId: ID | null; averageScore: number | null; evaluationCount: number;
}
export interface OrderStatistics {
  metric: 'created' | 'completed'; groupBy: 'category' | 'status' | 'worker' | 'day';
  total: number; buckets: { key: string | null; count: number; workerName?: string | null }[];
}
