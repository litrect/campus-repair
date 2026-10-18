from datetime import datetime, timedelta
import hashlib
import json
import re
import uuid

from flask import current_app
import pymysql

from ..db import get_db, transaction
from ..errors import BusinessError
from ..repositories import order_repository as repository
from ..responses import CHINA_TZ
from ..validation import text_field
from .access_control import get_visible_order
from .image_service import validate_reference
from .overtime_rules import ACTIVE_STATUSES, effective_overtime

STATUSES = frozenset(('CREATED', 'ASSIGNED', 'PROCESSING', 'DONE', 'CLOSED', 'CANCELLED'))


def now_local():
    return datetime.now(CHINA_TZ).replace(tzinfo=None, microsecond=0)


def normalize_creation(data, student_id):
    normalized = {
        'category': text_field(data['category'], '故障类别', 20),
        'location': text_field(data['location'], '报修地点', 100),
        'description': text_field(data['description'], '故障描述', 500),
        'urgency': data.get('urgency', 'NORMAL'),
        'imageUrl': data.get('imageUrl'),
    }
    if normalized['category'] not in current_app.config['ORDER_CATEGORIES']:
        raise BusinessError('故障类别不合法', 400)
    if not isinstance(normalized['urgency'], str) or normalized['urgency'] not in ('HIGH', 'NORMAL', 'LOW'):
        raise BusinessError('紧急程度不合法', 400)
    normalized['imageUrl'] = validate_reference(normalized['imageUrl'], student_id)
    return normalized


def creation_result(order):
    return {'id': str(order['id']), 'orderNo': order['order_no'],
            'status': order['status'], 'version': order['version']}


def match_existing(order, digest):
    if order['request_hash'] != digest:
        raise BusinessError('相同提交标识对应的报修内容不同，请重新提交', 409)
    return creation_result(order), False


def create_order(data, token, actor):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', token):
        raise BusinessError('必须提供有效的 Idempotency-Key', 400)
    normalized = normalize_creation(data, actor['id'])
    digest = hashlib.sha256(json.dumps(normalized, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    conn = get_db()
    existing = repository.find_idempotent(conn, actor['id'], token)
    if existing:
        return match_existing(existing, digest)
    event_time = now_local()
    deadline = event_time + timedelta(hours=current_app.config['SLA_HOURS'][normalized['urgency']])
    for _ in range(3):
        order_no = uuid.uuid4().hex
        try:
            with transaction() as conn:
                order_id = repository.insert_order(conn, actor['id'], token, digest, normalized,
                                                   order_no, event_time, deadline)
                repository.insert_create_log(conn, order_id, actor['id'], event_time)
            return creation_result({'id': order_id, 'order_no': order_no, 'status': 'CREATED', 'version': 0}), True
        except pymysql.IntegrityError as error:
            if error.args[0] != 1062:
                raise
            # The failed transaction has rolled back. Begin a fresh read snapshot.
            with transaction() as conn:
                existing = repository.find_idempotent(conn, actor['id'], token)
            if existing:
                return match_existing(existing, digest)
            if 'uk_order_no' not in str(error):
                raise
    raise BusinessError('工单编号生成冲突，请稍后重试', 503)


def summary(order, now, *, cancel_time=None):
    deadline = order['deadline']
    active = order['status'] in ACTIVE_STATUSES
    reference = now if active else (cancel_time if order['status'] == 'CANCELLED' else order['finish_time'])
    overdue = bool(deadline and reference and reference > deadline)
    return {
        'id': str(order['id']), 'orderNo': order['order_no'], 'category': order['category'],
        'location': order['location'], 'urgency': order['urgency'], 'status': order['status'],
        'workerId': str(order['worker_id']) if order['worker_id'] is not None else None,
        'createTime': order['create_time'], 'deadline': deadline,
        'isOvertime': effective_overtime(order, now, cancel_time),
        'isCurrentlyOverdue': bool(active and overdue), 'version': order['version'],
    }


def order_summary(conn, row, now):
    cancel_time = repository.cancellation_time(conn, row['id']) if row['status'] == 'CANCELLED' and not row['is_overtime'] else None
    return summary(row, now, cancel_time=cancel_time)


def list_orders(actor, page, page_size, status):
    if status is not None and status not in STATUSES:
        raise BusinessError('工单状态不合法', 400)
    conn = get_db()
    rows, total = repository.list_owned(conn, actor, page, page_size, status)
    now = now_local()
    return {'items': [order_summary(conn, row, now) for row in rows],
            'total': total, 'page': page, 'pageSize': page_size}


def order_detail(order_id, actor):
    conn = get_db()
    order = get_visible_order(conn, order_id, actor)
    result = order_summary(conn, order, now_local())
    result.update({
        'description': order['description'], 'imageUrl': order['image_url'],
        'repairRecord': order['repair_record'], 'studentId': str(order['student_id']),
        'assignTime': order['assign_time'], 'acceptTime': order['accept_time'],
        'finishTime': order['finish_time'], 'closeTime': order['close_time'], 'evaluation': None,
    })
    evaluation = repository.get_evaluation(conn, order['id'])
    if evaluation:
        result['evaluation'] = {'id': str(evaluation['id']), 'score': evaluation['score'],
                                'content': evaluation['content'], 'createTime': evaluation['create_time']}
    return result


def order_logs(order_id, actor):
    conn = get_db()
    order = get_visible_order(conn, order_id, actor)
    return [{
        'id': str(log['id']), 'eventType': log['event_type'], 'fromStatus': log['from_status'],
        'toStatus': log['to_status'], 'orderVersion': log['order_version'],
        'operatorId': str(log['operator_id']) if log['operator_id'] is not None else None,
        'fromWorkerId': str(log['from_worker_id']) if log['from_worker_id'] is not None else None,
        'toWorkerId': str(log['to_worker_id']) if log['to_worker_id'] is not None else None,
        'remark': log['remark'], 'createTime': log['create_time'],
    } for log in repository.get_logs(conn, order['id'])]
