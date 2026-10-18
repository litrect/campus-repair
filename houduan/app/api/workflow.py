from flask import g

from . import api
from ..auth import roles_required
from ..responses import success
from ..services import workflow_service
from ..validation import json_object, pagination, query_fields


@api.get('/orders/pending')
@roles_required('ADMIN')
def pending_orders():
    args = query_fields(('page', 'pageSize'))
    page, page_size = pagination(args)
    return success(workflow_service.pending_orders(page, page_size))


@api.get('/workers/available')
@roles_required('ADMIN')
def available_workers():
    args = query_fields(('category',))
    return success(workflow_service.recommended_workers(args.get('category')))


def perform(order_id, event, required=(), optional=(), message='操作成功'):
    body = json_object(required=('version',) + required, optional=optional)
    return success(workflow_service.change_status(order_id, body['version'], event, g.current_user, body),
                   message=message)


@api.post('/orders/<order_id>/assign')
@roles_required('ADMIN')
def assign(order_id):
    return perform(order_id, 'ASSIGN', required=('workerId',), message='派单成功')


@api.post('/orders/<order_id>/accept')
@roles_required('WORKER')
def accept(order_id):
    return perform(order_id, 'ACCEPT', message='接单成功')


@api.post('/orders/<order_id>/finish')
@roles_required('WORKER')
def finish(order_id):
    return perform(order_id, 'FINISH', required=('repairRecord',), message='提交完成')


@api.post('/orders/<order_id>/confirm')
@roles_required('STUDENT')
def confirm(order_id):
    return perform(order_id, 'CONFIRM', message='确认成功')


@api.post('/orders/<order_id>/reject')
@roles_required('STUDENT')
def reject(order_id):
    return perform(order_id, 'REJECT', required=('reason',), message='驳回成功')


@api.post('/orders/<order_id>/cancel')
@roles_required('STUDENT', 'ADMIN')
def cancel(order_id):
    return perform(order_id, 'CANCEL', optional=('reason',), message='取消成功')
