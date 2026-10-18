from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
import json
import os
from threading import Barrier
import uuid

from PIL import Image
import pymysql
import pytest

from app.services import order_service
from app.services.auth_service import serializer

pytestmark = [pytest.mark.database, pytest.mark.skipif(
    os.environ.get('RUN_DB_TESTS') != '1', reason='Set RUN_DB_TESTS=1')]


def auth(env, username='stu1'):
    app, _, users = env
    with app.app_context():
        return {'Authorization': 'Bearer ' + serializer().dumps({'uid': str(users[username])})}


def create(env, *, key=None, username='stu1', changes=None):
    app, _, _ = env
    body = {'category': '水电', 'location': ' A栋101 ', 'description': ' 水龙头漏水 '}
    if changes:
        body.update(changes)
    headers = {**auth(env, username), 'Idempotency-Key': key or uuid.uuid4().hex}
    return app.test_client().post('/api/orders', json=body, headers=headers)


def scalar(env, sql, params=()):
    with env[1].cursor() as cursor:
        cursor.execute(sql, params)
        return next(iter(cursor.fetchone().values()))


def png():
    buffer = BytesIO()
    Image.new('RGB', (4, 4), 'blue').save(buffer, format='PNG')
    return buffer.getvalue()


def upload(env, content, username='stu1', filename='photo.png'):
    return env[0].test_client().post('/api/uploads/images', headers=auth(env, username),
        data={'file': (BytesIO(content), filename)}, content_type='multipart/form-data')


def test_options_and_create_detail_logs(env):
    app, _, users = env
    client = app.test_client()
    assert client.get('/api/meta/order-options').status_code == 401
    options = client.get('/api/meta/order-options', headers=auth(env)).json['data']
    assert options == {'categories': ['水电', '门锁', '网络', '家具', '其他'], 'urgencies': ['HIGH', 'NORMAL', 'LOW']}
    response = create(env)
    assert response.status_code == 201
    created = response.json['data']
    assert created['status'] == 'CREATED' and created['version'] == 0 and isinstance(created['id'], str)
    details = client.get('/api/orders/' + created['id'], headers=auth(env)).json['data']
    assert details['location'] == 'A栋101' and details['description'] == '水龙头漏水'
    assert details['studentId'] == str(users['stu1'])
    assert details['imageUrl'] is None and details['evaluation'] is None
    assert details['urgency'] == 'NORMAL' and details['deadline'].endswith('+08:00')
    assert not details['isCurrentlyOverdue'] and not details['isOvertime']
    for private in ('password', 'request_hash', 'request_token', 'phone'):
        assert private not in json.dumps(details)
    with env[1].cursor() as cursor:
        cursor.execute('SELECT create_time,deadline FROM repair_order WHERE id=%s', (created['id'],))
        row = cursor.fetchone()
        assert row['deadline'] - row['create_time'] == timedelta(hours=24)
    logs = client.get(f"/api/orders/{created['id']}/logs", headers=auth(env)).json['data']
    assert len(logs) == 1 and logs[0]['eventType'] == 'CREATE' and logs[0]['orderVersion'] == 0
    assert logs[0]['operatorId'] == str(users['stu1'])
    assert logs[0]['createTime'] == details['createTime']


@pytest.mark.parametrize('changes', [{'location': ' '}, {'description': ''}, {'category': '不存在'},
    {'urgency': True}, {'urgency': 'normal'}, {'description': 'a' * 501}, {'studentId': '1'},
    {'status': 'CLOSED'}, {'imageUrl': 'https://example.com/photo.png'}, {'imageUrl': '../file'},
    {'imageUrl': True}])
def test_invalid_creation_no_rows(env, changes):
    count = scalar(env, 'SELECT COUNT(*) FROM repair_order')
    response = create(env, changes=changes)
    assert response.status_code == 400
    assert scalar(env, 'SELECT COUNT(*) FROM repair_order') == count


def test_required_fields_role_and_idempotency_key(env):
    app = env[0]
    assert app.test_client().post('/api/orders', headers=auth(env), json={'category': '水电'}).status_code == 400
    assert create(env, username='worker1').status_code == 403
    for key in ('', 'bad key', 'a' * 65, '中文'):
        response = app.test_client().post('/api/orders', headers={**auth(env), 'Idempotency-Key': key},
                        json={'category': '水电', 'location': 'A', 'description': '漏水'})
        assert response.status_code == 400
    assert app.test_client().post('/api/orders', headers=auth(env),
                        json={'category': '水电', 'location': 'A', 'description': '漏水'}).status_code == 400


def test_idempotency_normalization_conflict_and_user_scope(env):
    key = uuid.uuid4().hex
    first = create(env, key=key)
    again = create(env, key=key, changes={'location': 'A栋101', 'description': '水龙头漏水', 'urgency': 'NORMAL', 'imageUrl': None})
    assert again.status_code == 200 and again.json['data'] == first.json['data']
    assert create(env, key=key, changes={'description': '不同内容'}).status_code == 409
    other = create(env, key=key, username='stu2')
    assert other.status_code == 201 and other.json['data']['id'] != first.json['data']['id']
    assert scalar(env, 'SELECT COUNT(*) FROM order_log WHERE order_id=%s', (first.json['data']['id'],)) == 1
    # Retrying an already assigned order must return its current state/version.
    with env[1].cursor() as cursor:
        cursor.execute("UPDATE repair_order SET status='ASSIGNED',worker_id=%s,version=1 WHERE id=%s",
                       (env[2]['worker1'], first.json['data']['id']))
    retried = create(env, key=key)
    assert retried.json['data']['status'] == 'ASSIGNED' and retried.json['data']['version'] == 1


def test_concurrent_idempotency(env, monkeypatch):
    key = uuid.uuid4().hex
    initial_reads = Barrier(2)
    original_find = order_service.repository.find_idempotent
    def simultaneous_miss(conn, student_id, token):
        row = original_find(conn, student_id, token)
        if token == key and row is None:
            initial_reads.wait(timeout=10)
        return row
    monkeypatch.setattr(order_service.repository, 'find_idempotent', simultaneous_miss)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(env, key=key), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json['data']['id'] == responses[1].json['data']['id']
    assert scalar(env, 'SELECT COUNT(*) FROM repair_order WHERE request_token=%s', (key,)) == 1
    assert scalar(env, 'SELECT COUNT(*) FROM order_log WHERE order_id=%s', (responses[0].json['data']['id'],)) == 1


def test_create_log_failure_rolls_back(env, monkeypatch):
    key = uuid.uuid4().hex
    def fail(*args):
        raise pymysql.IntegrityError(1452, 'Injected log failure')
    monkeypatch.setattr(order_service.repository, 'insert_create_log', fail)
    assert create(env, key=key).status_code == 503
    assert scalar(env, 'SELECT COUNT(*) FROM repair_order WHERE request_token=%s', (key,)) == 0


def test_ownership_lists_and_reassignment(env):
    app, admin, users = env
    client = app.test_client()
    oid = create(env).json['data']['id']
    for suffix in ('', '/logs'):
        path = '/api/orders/' + oid + suffix
        assert client.get(path, headers=auth(env, 'stu2')).status_code == 404
        assert client.get(path, headers=auth(env, 'worker1')).status_code == 404
        assert client.get(path, headers=auth(env, 'admin')).status_code == 200
    with admin.cursor() as cursor:
        cursor.execute("UPDATE repair_order SET status='ASSIGNED',worker_id=%s WHERE id=%s", (users['worker1'], oid))
    assert client.get('/api/orders/' + oid, headers=auth(env, 'worker1')).status_code == 200
    worker_list = client.get('/api/orders/assigned-to-me', headers=auth(env, 'worker1')).json['data']
    assert oid in {row['id'] for row in worker_list['items']}
    with admin.cursor() as cursor:
        cursor.execute('UPDATE repair_order SET worker_id=%s WHERE id=%s', (users['worker2'], oid))
    assert client.get('/api/orders/' + oid, headers=auth(env, 'worker1')).status_code == 404
    mine = client.get('/api/orders/my?pageSize=1', headers=auth(env, 'stu2')).json['data']
    assert mine['total'] == scalar(env, 'SELECT COUNT(*) FROM repair_order WHERE student_id=%s', (users['stu2'],))
    assert len(mine['items']) == 1
    assert client.get('/api/orders/my', headers=auth(env, 'worker1')).status_code == 403
    for query in ('page=0', 'pageSize=101', 'status=UNKNOWN', 'page=1&page=2', 'studentId=1'):
        assert client.get('/api/orders/my?' + query, headers=auth(env)).status_code == 400


def test_image_validation_size_and_references(env):
    app = env[0]
    client = app.test_client()
    content = png()
    response = upload(env, content, filename='misleading.exe')
    assert response.status_code == 201
    url = response.json['data']['imageUrl']
    own = client.get(url, headers=auth(env))
    assert own.status_code == 200 and own.data == content and own.mimetype == 'image/png'
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth(env, 'stu2')).status_code == 404
    assert client.get(url, headers=auth(env, 'worker1')).status_code == 404
    assert client.get(url, headers=auth(env, 'admin')).status_code == 200
    assert create(env, changes={'imageUrl': url}).status_code == 201
    assert create(env, username='stu2', changes={'imageUrl': url}).status_code == 400
    assert upload(env, b'not an image', filename='fake.png').status_code == 400
    assert upload(env, content, username='worker1').status_code == 403
    exact = content + b'\0' * (2_097_152 - len(content))
    assert upload(env, exact).status_code == 201
    assert upload(env, exact + b'\0').status_code == 413
    gif = BytesIO()
    Image.new('RGB', (2, 2)).save(gif, format='GIF')
    assert upload(env, gif.getvalue(), filename='fake.jpg').status_code == 400


def test_image_worker_access_tracks_current_assignment(env):
    app, admin, users = env
    url = upload(env, png()).json['data']['imageUrl']
    oid = create(env, changes={'imageUrl': url}).json['data']['id']
    with admin.cursor() as cursor:
        cursor.execute("UPDATE repair_order SET status='ASSIGNED',worker_id=%s WHERE id=%s", (users['worker1'], oid))
    assert app.test_client().get(url, headers=auth(env, 'worker1')).status_code == 200
    with admin.cursor() as cursor:
        cursor.execute('UPDATE repair_order SET worker_id=%s WHERE id=%s', (users['worker2'], oid))
    assert app.test_client().get(url, headers=auth(env, 'worker1')).status_code == 404
    assert app.test_client().get(url, headers=auth(env, 'worker2')).status_code == 200


def test_order_number_collision_retries_separately(env, monkeypatch):
    first = create(env).json['data']
    original_uuid = uuid.uuid4
    values = iter([uuid.UUID(hex=first['orderNo']), original_uuid()])
    key = original_uuid().hex
    monkeypatch.setattr(order_service.uuid, 'uuid4', lambda: next(values))
    response = create(env, key=key)
    assert response.status_code == 201 and response.json['data']['id'] != first['id']


def test_list_overtime_boundary_and_finished_pause(env):
    app, admin, users = env
    oid = create(env, changes={'urgency': 'HIGH'}).json['data']['id']
    with admin.cursor() as cursor:
        cursor.execute('SELECT deadline,create_time FROM repair_order WHERE id=%s', (oid,))
        row = cursor.fetchone()
        assert row['deadline'] - row['create_time'] == timedelta(hours=4)
    with patch_time(row['deadline']):
        details = app.test_client().get('/api/orders/' + oid, headers=auth(env)).json['data']
        assert not details['isCurrentlyOverdue']
    with patch_time(row['deadline'] + timedelta(seconds=1)):
        details = app.test_client().get('/api/orders/' + oid, headers=auth(env)).json['data']
        assert details['isCurrentlyOverdue'] and details['isOvertime']
    with admin.cursor() as cursor:
        cursor.execute("UPDATE repair_order SET status='DONE',worker_id=%s,finish_time=deadline,repair_record='已修复' WHERE id=%s",
                       (users['worker1'], oid))
    with patch_time(row['deadline'] + timedelta(hours=24)):
        details = app.test_client().get('/api/orders/' + oid, headers=auth(env)).json['data']
        assert not details['isCurrentlyOverdue'] and not details['isOvertime']


def patch_time(moment):
    from unittest.mock import patch
    return patch('app.services.order_service.now_local', return_value=moment)
