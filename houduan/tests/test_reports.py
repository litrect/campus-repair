from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import os
from threading import Barrier
from unittest.mock import patch

import pymysql
import pytest

from app.services import overtime_service, workflow_service
from app.tasks.overtime import OvertimeScheduler
from test_orders import auth, create, scalar
from test_workflow import action, done, order_row, processing

pytestmark = [pytest.mark.database, pytest.mark.skipif(
    os.environ.get('RUN_DB_TESTS') != '1', reason='Set RUN_DB_TESTS=1')]


def closed(env):
    oid = done(env)
    assert action(env, oid, 'confirm', 3, 'stu1').status_code == 200
    return oid


def evaluate(env, oid, score, username='stu1', **fields):
    return env[0].test_client().post(f'/api/orders/{oid}/evaluate', headers=auth(env, username),
                                     json={'score': score, **fields})


def scan(env, moment):
    with env[0].app_context(), patch('app.services.overtime_service.now_local', return_value=moment):
        return overtime_service.scan_once()


def test_evaluation_once_and_does_not_change_order_version(env):
    oid = closed(env)
    before = order_row(env, oid)
    response = evaluate(env, oid, 5, content=' 修好了 ')
    assert response.status_code == 201 and isinstance(response.json['data']['id'], str)
    assert evaluate(env, oid, 4).status_code == 409
    assert order_row(env, oid) == before
    details = env[0].test_client().get(f'/api/orders/{oid}', headers=auth(env)).json['data']
    assert details['evaluation']['score'] == 5 and details['evaluation']['content'] == '修好了'
    assert scalar(env, 'SELECT COUNT(*) FROM evaluation WHERE order_id=%s', (oid,)) == 1


@pytest.mark.parametrize('score', [0, 6, True, False, 1.5, '5', None])
def test_invalid_evaluation_scores(env, score):
    oid = closed(env)
    assert evaluate(env, oid, score).status_code == 400
    assert scalar(env, 'SELECT COUNT(*) FROM evaluation WHERE order_id=%s', (oid,)) == 0


def test_evaluation_permissions_and_content(env):
    oid = create(env).json['data']['id']
    assert evaluate(env, oid, 5).status_code == 409
    oid = closed(env)
    assert evaluate(env, oid, 5, username='stu2').status_code == 404
    assert evaluate(env, oid, 5, username='worker1').status_code == 403
    assert evaluate(env, oid, 5, content='x' * 301).status_code == 400
    assert evaluate(env, oid, 5, content=True).status_code == 400
    assert evaluate(env, oid, 5, operatorId='1').status_code == 400


def test_concurrent_evaluation_one_row(env, monkeypatch):
    oid = closed(env)
    barrier = Barrier(2)
    from app.services import report_service
    original = report_service.get_visible_order
    def concurrent_read(conn, order_id, actor):
        row = original(conn, order_id, actor)
        if str(order_id) == oid:
            barrier.wait(timeout=10)
        return row
    monkeypatch.setattr(report_service, 'get_visible_order', concurrent_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda score: evaluate(env, oid, score), (3, 5)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert scalar(env, 'SELECT COUNT(*) FROM evaluation WHERE order_id=%s', (oid,)) == 1


def test_evaluation_summary_matches_raw_scores_and_unrated_is_null(env):
    oid = closed(env)
    assert evaluate(env, oid, 3).status_code == 201
    closed(env)  # An unrated closed order must not count as a zero score.
    client = env[0].test_client()
    wid = env[2]['worker1']
    result = client.get(f'/api/stats/evaluations?workerId={wid}&pageSize=1', headers=auth(env, 'admin')).json['data']
    count = scalar(env, 'SELECT COUNT(*) FROM evaluation e JOIN repair_order o ON e.order_id=o.id WHERE o.worker_id=%s', (wid,))
    average = scalar(env, 'SELECT AVG(score) FROM evaluation e JOIN repair_order o ON e.order_id=o.id WHERE o.worker_id=%s', (wid,))
    assert result['averageScore'] == float(round(average, 2))
    assert result['evaluationCount'] == result['total'] == count and len(result['items']) == 1
    empty = client.get(f"/api/stats/evaluations?workerId={env[2]['worker2']}", headers=auth(env, 'admin')).json['data']
    assert empty['averageScore'] is None and empty['evaluationCount'] == 0
    assert client.get('/api/stats/evaluations', headers=auth(env)).status_code == 403


def test_statistics_boundaries_metrics_and_no_log_multiplication(env):
    start = datetime(2011, 1, 1)
    with patch('app.services.order_service.now_local', return_value=start):
        first = create(env).json['data']['id']
    with patch('app.services.order_service.now_local', return_value=start + timedelta(days=1)):
        boundary = create(env).json['data']['id']
    assert action(env, first, 'assign', 0, 'admin', workerId=str(env[2]['worker1'])).status_code == 200
    assert action(env, first, 'accept', 1, 'worker1').status_code == 200
    assert action(env, first, 'finish', 2, 'worker1', repairRecord='修好').status_code == 200
    with patch('app.services.workflow_service.now_local', return_value=start + timedelta(days=1, hours=1)):
        assert action(env, first, 'confirm', 3, 'stu1').status_code == 200
    client = env[0].test_client()
    headers = auth(env, 'admin')
    query = '/api/stats/orders?from=2011-01-01&to=2011-01-02'
    data = client.get(query, headers=headers).json['data']
    assert data['total'] == 1 and data['buckets'] == [{'key': '水电', 'count': 1}]
    assert client.get(query + '&metric=completed', headers=headers).json['data']['total'] == 0
    complete = client.get('/api/stats/orders?metric=completed&from=2011-01-02&to=2011-01-03&groupBy=worker', headers=headers).json['data']
    assert complete['total'] == 1 and complete['buckets'][0]['key'] == str(env[2]['worker1'])
    days = client.get(query + '&groupBy=day', headers=headers).json['data']['buckets']
    assert days == [{'key': '2011-01-01', 'count': 1}]
    # UTC interval is normalized to Beijing time, not compared as a naive UTC value.
    assert client.get('/api/stats/orders?from=2010-12-31T16:00:00Z&to=2011-01-01T16:00:00Z', headers=headers).json['data']['total'] == 1
    unassigned = client.get('/api/stats/orders?from=2011-01-02&to=2011-01-03&groupBy=worker', headers=headers).json['data']
    assert unassigned['buckets'] == [{'key': None, 'count': 1, 'workerName': None}]
    for group in ('category', 'status', 'worker', 'day'):
        report = client.get('/api/stats/orders?groupBy=' + group, headers=headers).json['data']
        assert report['total'] == scalar(env, 'SELECT COUNT(*) FROM repair_order')
        assert sum(bucket['count'] for bucket in report['buckets']) == report['total']
    assert scalar(env, 'SELECT COUNT(*) FROM order_log WHERE order_id=%s', (first,)) == 5


@pytest.mark.parametrize('query', ['metric=unknown', 'groupBy=bad', 'from=bad-date',
    'from=2026-10-16&to=2026-10-15', 'from=2026-10-15&to=2026-10-15',
    'category=未知', 'status=UNKNOWN', 'groupBy=worker&groupBy=day', 'extra=1'])
def test_statistics_bad_parameters(env, query):
    assert env[0].test_client().get('/api/stats/orders?' + query, headers=auth(env, 'admin')).status_code == 400


def test_overtime_lists_before_scan_and_single_mark(env):
    oid = create(env).json['data']['id']
    deadline = order_row(env, oid)['deadline']
    client = env[0].test_client()
    with patch('app.services.report_service.now_local', return_value=deadline):
        items = client.get('/api/orders/overtime?pageSize=100', headers=auth(env, 'admin')).json['data']['items']
        assert oid not in {row['id'] for row in items}
    moment = deadline + timedelta(seconds=1)
    with patch('app.services.report_service.now_local', return_value=moment):
        for scope in ('active', 'history'):
            items = client.get('/api/orders/overtime?scope=' + scope + '&pageSize=100', headers=auth(env, 'admin')).json['data']['items']
            assert oid in {row['id'] for row in items}
    assert order_row(env, oid)['is_overtime'] == 0  # Query derives truth before scanner cache catches up.
    scan(env, moment)
    marked = order_row(env, oid)
    assert marked['is_overtime'] == 1 and marked['version'] == 1
    scan(env, moment)
    assert order_row(env, oid)['version'] == 1
    logs = client.get(f'/api/orders/{oid}/logs', headers=auth(env)).json['data']
    assert logs[-1]['eventType'] == 'OVERTIME' and logs[-1]['operatorId'] is None
    assert logs[-1]['fromStatus'] == logs[-1]['toStatus'] == 'CREATED'
    assert [log['orderVersion'] for log in logs] == [0, 1]
    assert client.get('/api/orders/overtime?scope=wrong', headers=auth(env, 'admin')).status_code == 400
    assert client.get('/api/orders/overtime', headers=auth(env)).status_code == 403


def test_overtime_history_finished_and_cancelled_without_cache(env):
    late_done = done(env)
    late_cancel = create(env).json['data']['id']
    assert action(env, late_cancel, 'cancel', 0, 'stu1').status_code == 200
    on_time = done(env)
    no_sla = create(env).json['data']['id']
    with env[1].cursor() as cursor:
        cursor.execute('UPDATE repair_order SET deadline=finish_time-INTERVAL 1 SECOND,is_overtime=0 WHERE id=%s', (late_done,))
        cursor.execute("UPDATE repair_order o SET deadline=(SELECT l.create_time-INTERVAL 1 SECOND FROM order_log l "
                       "WHERE l.order_id=o.id AND l.event_type='CANCEL'),is_overtime=0 WHERE o.id=%s", (late_cancel,))
        cursor.execute('UPDATE repair_order SET deadline=finish_time WHERE id=%s', (on_time,))
        cursor.execute('UPDATE repair_order SET deadline=NULL WHERE id=%s', (no_sla,))
    moment = order_row(env, on_time)['finish_time'] + timedelta(days=5)
    with patch('app.services.report_service.now_local', return_value=moment):
        history = env[0].test_client().get('/api/orders/overtime?scope=history&pageSize=100', headers=auth(env, 'admin')).json['data']
        active = env[0].test_client().get('/api/orders/overtime?scope=active&pageSize=100', headers=auth(env, 'admin')).json['data']
    history_ids = {row['id'] for row in history['items']}
    active_ids = {row['id'] for row in active['items']}
    assert {late_done, late_cancel} <= history_ids
    assert not {late_done, late_cancel, on_time, no_sla} & active_ids
    assert on_time not in history_ids and no_sla not in history_ids
    scan(env, moment)
    assert order_row(env, late_done)['is_overtime'] == order_row(env, late_cancel)['is_overtime'] == 1
    assert order_row(env, on_time)['is_overtime'] == order_row(env, no_sla)['is_overtime'] == 0


def test_scanner_log_failure_rolls_back(env, monkeypatch):
    oid = create(env).json['data']['id']
    before = order_row(env, oid)
    original = workflow_service.order_repository.insert_event_log
    def fail(conn, order, *args, **kwargs):
        if str(order['id']) == oid:
            raise pymysql.IntegrityError(1452, 'Injected scanner log failure')
        return original(conn, order, *args, **kwargs)
    monkeypatch.setattr(workflow_service.order_repository, 'insert_event_log', fail)
    result = scan(env, before['deadline'] + timedelta(seconds=1))
    assert result['skipped'] >= 1 and order_row(env, oid) == before
    assert scalar(env, 'SELECT COUNT(*) FROM order_log WHERE order_id=%s', (oid,)) == 1


def test_scan_and_finish_race_preserves_completion(env, monkeypatch):
    oid = processing(env)
    before = order_row(env, oid)
    barrier = Barrier(2)
    original_find = workflow_service.order_repository.find_order
    original_visible = workflow_service.get_visible_order
    def scanner_read(conn, order_id):
        row = original_find(conn, order_id)
        if str(order_id) == oid:
            barrier.wait(timeout=10)
        return row
    def actor_read(conn, order_id, actor):
        # access_control holds a separate find_order reference, so synchronize independently.
        row = original_visible(conn, order_id, actor)
        if str(order_id) == oid:
            barrier.wait(timeout=10)
        return row
    monkeypatch.setattr(workflow_service.order_repository, 'find_order', scanner_read)
    monkeypatch.setattr(workflow_service, 'get_visible_order', actor_read)
    moment = before['deadline'] + timedelta(seconds=1)
    def system_update():
        with env[0].app_context():
            return workflow_service.change_status(int(oid), 2, 'OVERTIME', None, {'event_time': moment})
    with patch('app.services.workflow_service.now_local', return_value=moment):
        with ThreadPoolExecutor(max_workers=2) as pool:
            scanner = pool.submit(system_update)
            finisher = pool.submit(action, env, oid, 'finish', 2, 'worker1', repairRecord='完成')
            scanner_result, finish_response = scanner.result(), finisher.result()
    assert (scanner_result, finish_response.status_code) in ((True, 409), (False, 200))
    # Remove synchronization before retrying the legitimate operation after a version conflict.
    monkeypatch.setattr(workflow_service.order_repository, 'find_order', original_find)
    monkeypatch.setattr(workflow_service, 'get_visible_order', original_visible)
    if finish_response.status_code == 409:
        with patch('app.services.workflow_service.now_local', return_value=moment):
            assert action(env, oid, 'finish', 3, 'worker1', repairRecord='完成').status_code == 200
    row = order_row(env, oid)
    assert row['status'] == 'DONE' and row['is_overtime'] == 1 and row['repair_record'] == '完成'
    assert scalar(env, "SELECT COUNT(*) FROM order_log WHERE order_id=%s AND event_type='FINISH'", (oid,)) == 1


def test_scheduler_lock_prevents_duplicate_instances(env):
    one, two = OvertimeScheduler(env[0]), OvertimeScheduler(env[0])
    one.acquire()
    try:
        with pytest.raises(RuntimeError, match='already running'):
            two.acquire()
    finally:
        one.release()
    two.acquire()
    two.release()


def test_scheduler_runs_and_stops(env):
    from threading import Event
    ran = Event()
    app = env[0]
    scheduler = OvertimeScheduler(app)
    with patch('app.tasks.overtime.scan_once', side_effect=lambda: (ran.set() or {'marked': 0, 'skipped': 0})):
        scheduler.start()
        try:
            assert ran.wait(timeout=3)
            with pytest.raises(RuntimeError, match='already running'):
                scheduler.start()
            with pytest.raises(RuntimeError, match='already running'):
                scheduler.run_once()
        finally:
            scheduler.stop()
    assert not scheduler.thread.is_alive() and scheduler.lock is None
