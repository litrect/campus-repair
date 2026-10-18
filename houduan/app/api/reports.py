from flask import g

from . import api
from ..auth import roles_required
from ..responses import success
from ..services import report_service
from ..validation import json_object, pagination, query_fields


@api.post('/orders/<order_id>/evaluate')
@roles_required('STUDENT')
def evaluate(order_id):
    data = json_object(required=('score',), optional=('content',))
    return success(report_service.evaluate(order_id, g.current_user, data), message='评价成功', status=201)


@api.get('/stats/evaluations')
@roles_required('ADMIN')
def evaluation_summary():
    args = query_fields(('workerId', 'page', 'pageSize'))
    page, page_size = pagination(args)
    return success(report_service.evaluation_summary(args.get('workerId'), page, page_size))


@api.get('/stats/orders')
@roles_required('ADMIN')
def order_statistics():
    args = query_fields(('metric', 'groupBy', 'from', 'to', 'category', 'status'))
    return success(report_service.statistics(args))


@api.get('/orders/overtime')
@roles_required('ADMIN')
def overtime_orders():
    args = query_fields(('scope', 'page', 'pageSize'))
    page, page_size = pagination(args)
    return success(report_service.overtime_list(args.get('scope', 'active'), page, page_size))
