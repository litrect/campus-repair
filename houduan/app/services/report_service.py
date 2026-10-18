from datetime import date, datetime

from flask import current_app
import pymysql

from ..db import get_db, transaction
from ..errors import BusinessError
from ..repositories import report_repository
from ..responses import CHINA_TZ
from ..validation import positive_id, text_field
from .access_control import get_visible_order
from .order_service import STATUSES, now_local, order_summary


def evaluate(order_id, actor, data):
    try:
        with transaction() as conn:
            order = get_visible_order(conn, order_id, actor)
            if order['status'] != 'CLOSED':
                raise BusinessError('工单确认关闭后才能评价', 409)
            score = data['score']
            if type(score) is not int or not 1 <= score <= 5:
                raise BusinessError('评分必须是 1 至 5 的整数', 400)
            content = text_field(data['content'], '评价内容', 300, required=False) if 'content' in data else None
            evaluation_id = report_repository.insert_evaluation(conn, order['id'], score, content)
        return {'id': str(evaluation_id)}
    except pymysql.IntegrityError as error:
        if error.args[0] == 1062 and 'uk_evaluation_order' in str(error):
            raise BusinessError('该工单已经评价，不能重复提交', 409) from None
        raise


def evaluation_summary(worker_id, page, page_size):
    worker_id = positive_id(worker_id) if worker_id is not None else None
    aggregate, rows = report_repository.evaluations(get_db(), worker_id, page, page_size)
    items = [{'id': str(row['id']), 'orderId': str(row['order_id']),
              'workerId': str(row['worker_id']) if row['worker_id'] is not None else None,
              'score': row['score'], 'content': row['content'], 'createTime': row['create_time']} for row in rows]
    return {'workerId': str(worker_id) if worker_id is not None else None,
            'averageScore': float(round(aggregate['average'], 2)) if aggregate['average'] is not None else None,
            'evaluationCount': aggregate['n'], 'items': items, 'total': aggregate['n'],
            'page': page, 'pageSize': page_size}


def parse_time(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=CHINA_TZ)
        return parsed.astimezone(CHINA_TZ).replace(tzinfo=None)
    except (ValueError, OverflowError):
        raise BusinessError('时间参数不合法，请使用 ISO 日期或时间', 400) from None


def statistics(args):
    metric, group_by = args.get('metric', 'created'), args.get('groupBy', 'category')
    if metric not in ('created', 'completed') or group_by not in ('category', 'status', 'worker', 'day'):
        raise BusinessError('统计指标或分组方式不合法', 400)
    filters = {'from': parse_time(args.get('from')), 'to': parse_time(args.get('to')),
               'category': args.get('category'), 'status': args.get('status')}
    if filters['from'] is not None and filters['to'] is not None and filters['from'] >= filters['to']:
        raise BusinessError('开始时间必须早于结束时间', 400)
    if filters['category'] is not None and filters['category'] not in current_app.config['ORDER_CATEGORIES']:
        raise BusinessError('故障类别不合法', 400)
    if filters['status'] is not None and filters['status'] not in STATUSES:
        raise BusinessError('工单状态不合法', 400)
    rows = report_repository.order_statistics(get_db(), metric, group_by, filters)
    buckets = []
    for row in rows:
        key = row['bucket_key']
        if group_by == 'worker' and key is not None:
            key = str(key)
        elif isinstance(key, date):
            key = key.isoformat()
        bucket = {'key': key, 'count': row['n']}
        if group_by == 'worker':
            bucket['workerName'] = row['worker_name']
        buckets.append(bucket)
    return {'metric': metric, 'groupBy': group_by, 'total': sum(row['n'] for row in rows), 'buckets': buckets}


def overtime_list(scope, page, page_size):
    if scope not in ('active', 'history'):
        raise BusinessError('scope 必须是 active 或 history', 400)
    now = now_local()
    conn = get_db()
    rows, total = report_repository.overtime_orders(conn, scope, now, page, page_size)
    return {'items': [order_summary(conn, row, now) for row in rows],
            'total': total, 'page': page, 'pageSize': page_size}
