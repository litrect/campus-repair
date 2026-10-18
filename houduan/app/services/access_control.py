"""Shared ownership check for later order, log, evaluation and image services."""
from ..errors import BusinessError
from ..repositories.order_repository import find_order
from ..validation import positive_id


def ensure_order_visible(order, actor):
    if order is None or not (
        actor['role'] == 'ADMIN'
        or (actor['role'] == 'STUDENT' and order['student_id'] == actor['id'])
        or (actor['role'] == 'WORKER' and order['worker_id'] == actor['id'])
    ):
        raise BusinessError('资源不存在或不可访问', 404)
    return order


def get_visible_order(conn, order_id, actor):
    return ensure_order_visible(find_order(conn, positive_id(order_id)), actor)
