from flask import current_app, g, request, send_file

from . import api
from ..auth import roles_required
from ..errors import BusinessError
from ..responses import success
from ..services import image_service, order_service
from ..validation import json_object, pagination, query_fields


@api.get('/meta/order-options')
def order_options():
    return success({'categories': list(current_app.config['ORDER_CATEGORIES']),
                    'urgencies': ['HIGH', 'NORMAL', 'LOW']})


@api.post('/uploads/images')
@roles_required('STUDENT')
def upload_image():
    if set(request.files) != {'file'} or len(request.files.getlist('file')) != 1 or request.form:
        raise BusinessError('请通过 file 字段上传一张图片', 400)
    return success({'imageUrl': image_service.upload_image(request.files['file'], g.current_user['id'])},
                   message='上传成功', status=201)


@api.get('/uploads/images/<student_id>/<filename>')
def read_image(student_id, filename):
    path = image_service.readable_image(student_id, filename, g.current_user)
    return send_file(path, mimetype='image/png' if path.suffix == '.png' else 'image/jpeg',
                     conditional=False, etag=False, max_age=0)


@api.post('/orders')
@roles_required('STUDENT')
def create_order():
    data = json_object(required=('category', 'location', 'description'), optional=('urgency', 'imageUrl'))
    result, created = order_service.create_order(data, request.headers.get('Idempotency-Key'), g.current_user)
    return success(result, message='提交成功', status=201 if created else 200)


def own_list():
    args = query_fields(('page', 'pageSize', 'status'))
    page, page_size = pagination(args)
    return success(order_service.list_orders(g.current_user, page, page_size, args.get('status')))


@api.get('/orders/my')
@roles_required('STUDENT')
def my_orders():
    return own_list()


@api.get('/orders/assigned-to-me')
@roles_required('WORKER')
def assigned_orders():
    return own_list()


@api.get('/orders/<order_id>')
def order_detail(order_id):
    return success(order_service.order_detail(order_id, g.current_user))


@api.get('/orders/<order_id>/logs')
def order_logs(order_id):
    return success(order_service.order_logs(order_id, g.current_user))
