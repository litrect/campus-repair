from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from threading import Barrier
from unittest.mock import patch

import pymysql
import pytest

from app.services import workflow_service
from test_orders import auth, create, scalar

pytestmark = [pytest.mark.database, pytest.mark.skipif(
    os.environ.get('RUN_DB_TESTS') != '1', reason='Set RUN_DB_TESTS=1')]


def action(env, oid, name, version, username, **fields):
    return env[0].test_client().post(f'/api/orders/{oid}/{name}',
        headers=auth(env, username), json={'version': version, **fields})


def order_row(env, oid):
    with env[1].cursor() as cursor:
        cursor.execute('SELECT * FROM repair_order WHERE id=%s', (oid,))
        return cursor.fetchone()


def assigned(env, worker='worker1'):
    oid = create(env).json['data']['id']
    response = action(env, oid, 'assign', 0, 'admin', workerId=str(env[2][worker]))
    assert response.status_code == 200
    return oid


def processing(env):
    oid = assigned(env)
    assert action(env, oid, 'accept', 1, 'worker1').status_code == 200
    return oid


def done(env):
    oid = processing(env)
    assert action(env, oid, 'finish', 2, 'worker1', repairRecord='更换阀芯').status_code == 200
    return oid


def test_complete_flow_rejection_and_log_versions(env):
    oid = create(env).json['data']['id']
    original_deadline = order_row(env, oid)['deadline']
    assert action(env, oid, 'assign', 0, 'admin', workerId=str(env[2]['worker1'])).json['data']['version'] == 1
    assert action(env, oid, 'assign', 1, 'admin', workerId=str(env[2]['worker2'])).json['data']['version'] == 2
    assert action(env, oid, 'accept', 2, 'worker2').json['data']['status'] == 'PROCESSING'
    assert action(env, oid, 'finish', 3, 'worker2', repairRecord='第一次维修').status_code == 200
    assert action(env, oid, 'reject', 4, 'stu1', reason='仍然漏水').status_code == 200
    rejected = order_row(env, oid)
    assert rejected['finish_time'] is None and rejected['repair_record'] == '第一次维修'
    assert rejected['deadline'] == original_deadline
    assert action(env, oid, 'finish', 5, 'worker2', repairRecord='再次密封').status_code == 200
    assert action(env, oid, 'confirm', 6, 'stu1').json['data'] == {'id': oid, 'status': 'CLOSED', 'version': 7}
    assert action(env, oid, 'confirm', 7, 'stu1').status_code == 409
    logs = env[0].test_client().get(f'/api/orders/{oid}/logs', headers=auth(env)).json['data']
    assert [log['orderVersion'] for log in logs] == list(range(8))
    assert [log['eventType'] for log in logs] == ['CREATE','ASSIGN','REASSIGN','ACCEPT','FINISH','REJECT','FINISH','CONFIRM']
    assert logs[2]['fromWorkerId'] == str(env[2]['worker1'])
    assert logs[2]['toWorkerId'] == str(env[2]['worker2'])
    assert [logs[index]['remark'] for index in (4, 5, 6)] == ['第一次维修', '仍然漏水', '再次密封']
    row = order_row(env, oid)
    assert row['close_time'].isoformat() + '+08:00' == logs[-1]['createTime']


def test_pending_only_created_and_roles(env):
    oid = create(env).json['data']['id']
    client = env[0].test_client()
    response = client.get('/api/orders/pending?pageSize=100', headers=auth(env, 'admin'))
    data = response.json['data']
    assert response.status_code == 200 and oid in {row['id'] for row in data['items']}
    assert all(row['status'] == 'CREATED' for row in data['items'])
    assert data['total'] == scalar(env, "SELECT COUNT(*) FROM repair_order WHERE status='CREATED'")
    assert client.get('/api/orders/pending', headers=auth(env)).status_code == 403
    assert client.get('/api/orders/pending').status_code == 401
    assert client.get('/api/orders/pending?status=ASSIGNED', headers=auth(env, 'admin')).status_code == 400


def test_worker_recommendation_skill_load_and_disabled(env):
    client = env[0].test_client()
    with env[1].cursor() as cursor:
        cursor.execute("INSERT INTO user(username,password,real_name,role,skill,is_active) "
                       "SELECT 'disabled-worker',password,'停用师傅','WORKER','水电',0 FROM user WHERE username='worker1'")
        cursor.execute("INSERT INTO user(username,password,real_name,role,skill) "
                       "SELECT 'partial-worker',password,'部分技能','WORKER','水' FROM user WHERE username='worker1'")
    rows = client.get('/api/workers/available?category=水电', headers=auth(env, 'admin')).json['data']
    assert '停用师傅' not in {row['realName'] for row in rows}
    for row in rows:
        count = scalar(env, "SELECT COUNT(*) FROM repair_order WHERE worker_id=%s AND status IN ('ASSIGNED','PROCESSING')", (row['id'],))
        match = '水电' in {tag.strip() for tag in (row['skill'] or '').split(',')}
        assert row['activeOrderCount'] == count
        assert row['recommendationScore'] == 100 * match - 10 * count
    assert rows == sorted(rows, key=lambda row: (-row['recommendationScore'], row['activeOrderCount'], int(row['id'])))
    assert next(row for row in rows if row['realName'] == '部分技能')['recommendationScore'] == 0
    assert client.get('/api/workers/available?category=未知', headers=auth(env, 'admin')).status_code == 400
    assert client.get('/api/workers/available', headers=auth(env, 'worker1')).status_code == 403


@pytest.mark.parametrize('target', ['missing', 'student', 'disabled'])
def test_invalid_assignment_targets(env, target):
    oid = create(env).json['data']['id']
    if target == 'missing':
        worker_id = '99999999'
    elif target == 'student':
        worker_id = str(env[2]['stu1'])
    else:
        with env[1].cursor() as cursor:
            cursor.execute("INSERT INTO user(username,password,real_name,role,is_active) "
                           "SELECT 'inactive-target',password,'停用目标','WORKER',0 FROM user WHERE username='worker1'")
            worker_id = str(cursor.lastrowid)
    response = action(env, oid, 'assign', 0, 'admin', workerId=worker_id)
    assert response.status_code == 422
    assert order_row(env, oid)['version'] == 0
    assert scalar(env, 'SELECT COUNT(*) FROM order_log WHERE order_id=%s', (oid,)) == 1


@pytest.mark.parametrize('version', [True, False, -1, 1.5, '0', None, 2147483647])
def test_invalid_versions(env, version):
    oid = create(env).json['data']['id']
    assert action(env, oid, 'assign', version, 'admin', workerId=str(env[2]['worker1'])).status_code == 400
    assert order_row(env, oid)['version'] == 0


def test_reassignment_invalid_states_and_stale_versions(env):
    oid = assigned(env)
    assert action(env, oid, 'assign', 1, 'admin', workerId=str(env[2]['worker1'])).status_code == 409
    assert action(env, oid, 'assign', 0, 'admin', workerId=str(env[2]['worker2'])).status_code == 409
    assert action(env, oid, 'accept', 1, 'worker2').status_code == 404
    assert action(env, oid, 'accept', 1, 'worker1').status_code == 200
    assert action(env, oid, 'accept', 1, 'worker1').status_code == 409
    assert action(env, oid, 'assign', 2, 'admin', workerId=str(env[2]['worker2'])).status_code == 409
    assert action(env, oid, 'confirm', 2, 'stu1').status_code == 409
    assert action(env, oid, 'finish', 2, 'worker1', repairRecord=' ').status_code == 400
    assert action(env, oid, 'finish', 2, 'worker1', repairRecord='完成').status_code == 200
    assert action(env, oid, 'reject', 3, 'stu1', reason=' ').status_code == 400
    assert action(env, oid, 'reject', 3, 'stu2', reason='没修好').status_code == 404
    assert action(env, oid, 'reject', 3, 'stu1', reason='没修好').status_code == 200


def test_cancel_permissions_and_close_time(env):
    client = env[0].test_client()
    oid = create(env).json['data']['id']
    assert action(env, oid, 'cancel', 0, 'worker1').status_code == 403
    assert action(env, oid, 'cancel', 0, 'stu2').status_code == 404
    assert action(env, oid, 'cancel', 0, 'stu1').status_code == 200
    assert order_row(env, oid)['close_time'] is None
    assert action(env, oid, 'cancel', 1, 'stu1').status_code == 409
    created = create(env).json['data']['id']
    assert action(env, created, 'cancel', 0, 'admin', reason='重复报修').status_code == 200
    waiting = assigned(env)
    assert action(env, waiting, 'cancel', 1, 'stu1').status_code == 409
    assert action(env, waiting, 'cancel', 1, 'admin').status_code == 200
    busy = processing(env)
    assert action(env, busy, 'cancel', 2, 'admin').status_code == 409
    assert action(env, busy, 'cancel', 2, 'stu1').status_code == 409
    logs = client.get(f'/api/orders/{created}/logs', headers=auth(env, 'admin')).json['data']
    assert logs[-1]['remark'] == '重复报修' and logs[-1]['eventType'] == 'CANCEL'


@pytest.mark.parametrize('kind', ['assign', 'reassign', 'confirm-reject'])
def test_same_version_concurrent_actions_one_wins(env, monkeypatch, kind):
    barrier = Barrier(2)
    original_get = workflow_service.get_visible_order
    if kind == 'assign':
        oid = create(env).json['data']['id']
        version = 0
        jobs = [('assign', 'admin', {'workerId': str(env[2][w])}) for w in ('worker1', 'worker2')]
    elif kind == 'reassign':
        oid = assigned(env)
        version = 1
        jobs = [('assign', 'admin', {'workerId': str(env[2]['worker2'])})] * 2
    else:
        oid = done(env)
        version = 3
        jobs = [('confirm', 'stu1', {}), ('reject', 'stu1', {'reason': '仍需维修'})]
    before_logs = scalar(env, 'SELECT COUNT(*) FROM order_log WHERE order_id=%s', (oid,))
    def simultaneous_read(conn, order_id, actor):
        row = original_get(conn, order_id, actor)
        if str(order_id) == oid:
            barrier.wait(timeout=10)
        return row
    monkeypatch.setattr(workflow_service, 'get_visible_order', simultaneous_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda job: action(env, oid, job[0], version, job[1], **job[2]), jobs))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert order_row(env, oid)['version'] == version + 1
    assert scalar(env, 'SELECT COUNT(*) FROM order_log WHERE order_id=%s', (oid,)) == before_logs + 1


@pytest.mark.parametrize('name,actor,fields', [
    ('assign', 'admin', {'workerId': 'worker2'}),
    ('finish', 'worker1', {'repairRecord': '完成'}),
    ('confirm', 'stu1', {}),
])
def test_log_insert_failure_rolls_back_all_fields(env, monkeypatch, name, actor, fields):
    oid = processing(env) if name == 'finish' else (done(env) if name == 'confirm' else assigned(env))
    before = order_row(env, oid)
    log_count = scalar(env, 'SELECT COUNT(*) FROM order_log WHERE order_id=%s', (oid,))
    fields = dict(fields)
    if 'workerId' in fields:
        fields['workerId'] = str(env[2][fields['workerId']])
    def fail(*args, **kwargs):
        raise pymysql.IntegrityError(1452, 'Injected log failure')
    monkeypatch.setattr(workflow_service.order_repository, 'insert_event_log', fail)
    assert action(env, oid, name, before['version'], actor, **fields).status_code == 503
    assert order_row(env, oid) == before
    assert scalar(env, 'SELECT COUNT(*) FROM order_log WHERE order_id=%s', (oid,)) == log_count


def test_overtime_actions_do_not_depend_on_scanner(env):
    oid = processing(env)
    deadline = order_row(env, oid)['deadline']
    with patch('app.services.workflow_service.now_local', return_value=deadline + timedelta(seconds=1)):
        assert action(env, oid, 'finish', 2, 'worker1', repairRecord='晚完成').status_code == 200
    assert order_row(env, oid)['is_overtime'] == 1
    with patch('app.services.workflow_service.now_local', return_value=deadline + timedelta(days=1)):
        assert action(env, oid, 'confirm', 3, 'stu1').status_code == 200
    assert order_row(env, oid)['is_overtime'] == 1
    on_time = processing(env)
    deadline = order_row(env, on_time)['deadline']
    with patch('app.services.workflow_service.now_local', return_value=deadline):
        assert action(env, on_time, 'finish', 2, 'worker1', repairRecord='准时完成').status_code == 200
    with patch('app.services.workflow_service.now_local', return_value=deadline + timedelta(days=1)):
        assert action(env, on_time, 'confirm', 3, 'stu1').status_code == 200
    assert order_row(env, on_time)['is_overtime'] == 0
    rejected = done(env)
    deadline = order_row(env, rejected)['deadline']
    with patch('app.services.workflow_service.now_local', return_value=deadline + timedelta(seconds=1)):
        assert action(env, rejected, 'reject', 3, 'stu1', reason='仍有问题').status_code == 200
    row = order_row(env, rejected)
    assert row['deadline'] == deadline and row['is_overtime'] == 1 and row['finish_time'] is None
    cancelled = create(env).json['data']['id']
    deadline = order_row(env, cancelled)['deadline']
    with patch('app.services.workflow_service.now_local', return_value=deadline + timedelta(seconds=1)):
        assert action(env, cancelled, 'cancel', 0, 'stu1').status_code == 200
    assert order_row(env, cancelled)['is_overtime'] == 1


def test_role_and_unknown_fields_rejected(env):
    oid = create(env).json['data']['id']
    assert action(env, oid, 'assign', 0, 'stu1', workerId=str(env[2]['worker1'])).status_code == 403
    assert action(env, oid, 'assign', 0, 'admin', workerId=str(env[2]['worker1']), status='CLOSED').status_code == 400
    assert action(env, oid, 'assign', 0, 'admin', workerId=True).status_code == 400
    assert env[0].test_client().post(f'/api/orders/{oid}/assign', headers=auth(env, 'admin'), json={'workerId': '2'}).status_code == 400
