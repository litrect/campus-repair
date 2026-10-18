from flask import current_app
import pymysql

from ..db import get_db, transaction
from ..errors import BusinessError
from ..repositories import order_repository, worker_repository
from ..validation import positive_id, text_field, version_number
from .access_control import get_visible_order
from .order_service import now_local, order_summary
from .overtime_rules import effective_overtime

# ASSIGN also selects REASSIGN when the order is still awaiting acceptance.
EVENT_RULES = {
    'ASSIGN': ({'ADMIN'}, {'CREATED', 'ASSIGNED'}, 'ASSIGNED'),
    'ACCEPT': ({'WORKER'}, {'ASSIGNED'}, 'PROCESSING'),
    'FINISH': ({'WORKER'}, {'PROCESSING'}, 'DONE'),
    'CONFIRM': ({'STUDENT'}, {'DONE'}, 'CLOSED'),
    'REJECT': ({'STUDENT'}, {'DONE'}, 'PROCESSING'),
    'CANCEL': ({'STUDENT', 'ADMIN'}, {'CREATED', 'ASSIGNED'}, 'CANCELLED'),
}


def pending_orders(page, page_size):
    conn = get_db()
    rows, total = order_repository.list_pending(conn, page, page_size)
    now = now_local()
    return {'items': [order_summary(conn, row, now) for row in rows],
            'total': total, 'page': page, 'pageSize': page_size}


def recommended_workers(category=None):
    if category is not None and category not in current_app.config['ORDER_CATEGORIES']:
        raise BusinessError('故障类别不合法', 400)
    rows = worker_repository.available_workers(get_db())
    result = []
    for row in rows:
        tags = {tag.strip() for tag in (row['skill'] or '').split(',') if tag.strip()}
        count = int(row['active_count'])
        score = (current_app.config['RECOMMENDATION_SKILL_WEIGHT'] * int(category in tags)
                 - current_app.config['RECOMMENDATION_LOAD_PENALTY'] * count)
        result.append({'id': str(row['id']), 'realName': row['real_name'], 'skill': row['skill'],
                       'activeOrderCount': count, 'recommendationScore': score})
    result.sort(key=lambda row: (-row['recommendationScore'], row['activeOrderCount'], int(row['id'])))
    return result


def change_status(order_id, expected_version, event, actor, payload):
    if event == 'OVERTIME':
        if actor is not None:
            raise BusinessError('无权执行此操作', 403)
        return mark_overtime(order_id, expected_version, payload['event_time'])
    roles, source_states, target = EVENT_RULES[event]
    if actor['role'] not in roles:
        raise BusinessError('无权执行此操作', 403)
    try:
        with transaction() as conn:
            order = get_visible_order(conn, order_id, actor)
            expected_version = version_number(expected_version)
            if order['version'] >= 2_147_483_647:
                current_app.logger.error('Order version limit reached (order_id=%s)', order['id'])
                raise BusinessError('工单版本已达到上限，请联系管理员', 409)
            if order['version'] != expected_version:
                raise BusinessError('该工单刚被其他人处理，请刷新后重试', 409)
            if order['status'] not in source_states or (
                event == 'CANCEL' and actor['role'] == 'STUDENT' and order['status'] != 'CREATED'
            ):
                raise BusinessError('当前工单状态不允许此操作', 409)

            actual_event = event
            fields = {'status': target}
            remark = None
            from_worker = to_worker = None
            # Fields are validated before fixing the event time, especially if a target lock waits.
            if event == 'ASSIGN':
                worker_id = positive_id(payload['workerId'])
                worker = worker_repository.lock_worker(conn, worker_id)
                if not worker or worker['role'] != 'WORKER' or worker['is_active'] != 1:
                    raise BusinessError('请选择启用的维修工', 422)
                if order['status'] == 'ASSIGNED':
                    if order['worker_id'] == worker_id:
                        raise BusinessError('改派必须选择另一位维修工', 409)
                    actual_event = 'REASSIGN'
                    from_worker = order['worker_id']
                to_worker = worker_id
                fields['worker_id'] = worker_id
            elif event == 'FINISH':
                remark = text_field(payload['repairRecord'], '维修记录', 500)
                fields['repair_record'] = remark
            elif event == 'REJECT':
                remark = text_field(payload['reason'], '驳回原因', 500)
                fields['finish_time'] = None
            elif event == 'CANCEL':
                if 'reason' in payload:
                    remark = text_field(payload['reason'], '取消原因', 500, required=False)

            event_time = now_local()
            time_column = {'ASSIGN': 'assign_time', 'ACCEPT': 'accept_time',
                           'FINISH': 'finish_time', 'CONFIRM': 'close_time'}.get(event)
            if time_column:
                fields[time_column] = event_time
            reference = order['finish_time'] if event == 'CONFIRM' else event_time
            fields['is_overtime'] = int(bool(order['is_overtime']) or bool(
                order['deadline'] and reference and reference > order['deadline']))
            changed = order_repository.update_for_event(conn, order, expected_version, actor, fields)
            if changed != 1:
                raise BusinessError('该工单刚被其他人处理，请刷新后重试', 409)
            order_repository.insert_event_log(conn, order, actual_event, target, actor['id'],
                expected_version + 1, event_time, remark=remark, from_worker=from_worker, to_worker=to_worker)
            result = {'id': str(order['id']), 'status': target, 'version': expected_version + 1}
            if event == 'ASSIGN':
                result['workerId'] = str(to_worker)
        return result
    except pymysql.OperationalError as error:
        if error.args[0] in (1205, 1213):
            raise BusinessError('工单正在被处理，请刷新后重试', 503) from None
        raise


def mark_overtime(order_id, expected_version, event_time):
    """System-only 0→1 update through the same conditional update/log transaction pattern."""
    with transaction() as conn:
        order = order_repository.find_order(conn, order_id)
        if not order or order['version'] != expected_version or order['is_overtime']:
            return False
        if order['version'] >= 2_147_483_647:
            current_app.logger.error('Order version limit reached (order_id=%s)', order['id'])
            return False
        cancelled = order_repository.cancellation_time(conn, order['id']) if order['status'] == 'CANCELLED' else None
        if not effective_overtime(order, event_time, cancelled):
            return False
        if order_repository.update_for_event(conn, order, expected_version, None, {'is_overtime': 1}) != 1:
            return False
        order_repository.insert_event_log(conn, order, 'OVERTIME', order['status'], None,
                                           expected_version + 1, event_time)
    return True
