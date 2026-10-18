import type { OrderStatus } from '../utils/display'
export interface OrderSummary {
  id: string; orderNo: string; category: string; location: string; urgency: 'HIGH' | 'NORMAL' | 'LOW'; status: OrderStatus;
  workerId: string | null; createTime: string; deadline: string | null; isOvertime: boolean; isCurrentlyOverdue: boolean; version: number;
}
export interface OrderDetail extends OrderSummary {
  description: string; imageUrl: string | null; repairRecord: string | null; studentId: string;
  assignTime: string | null; acceptTime: string | null; finishTime: string | null; closeTime: string | null;
  evaluation: { id: string; score: number; content: string | null; createTime: string } | null;
}
export interface OrderLog {
  id: string; eventType: string; fromStatus: OrderStatus | null; toStatus: OrderStatus; orderVersion: number;
  operatorId: string | null; fromWorkerId: string | null; toWorkerId: string | null; remark: string | null; createTime: string;
}
