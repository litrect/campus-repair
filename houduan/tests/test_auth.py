import os
import time
from unittest.mock import patch

from flask import g, request
from itsdangerous import URLSafeTimedSerializer
import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.auth import roles_required
from app.responses import success
from app.services import auth_service
from app.services.access_control import get_visible_order


def add_probes(app):
    # These routes exist only in test applications, never in the running API.
    def identity():
        return success(auth_service.public_identity(g.current_user))

    @roles_required('ADMIN')
    def admin():
        if request.method == 'POST':
            request.get_json()
        return success()

    @roles_required('WORKER')
    def worker():
        return success()

    def order(order_id):
        row = get_visible_order(object(), order_id, g.current_user)
        return success({'id': str(row['id'])})

    app.add_url_rule('/api/_test/identity', 'api.test_identity', identity)
    app.add_url_rule('/api/_test/admin', 'api.test_admin', admin, methods=['GET', 'POST'])
    app.add_url_rule('/api/_test/worker', 'api.test_worker', worker)
    app.add_url_rule('/api/_test/orders/<order_id>', 'api.test_order', order)


@pytest.fixture
def auth_app(tmp_path, monkeypatch):
    app = create_app({'TESTING': True}, instance_path=tmp_path)
    password = generate_password_hash(' secret ', method='pbkdf2:sha256:1000')
    users = {
        1: dict(id=1, username='student', real_name='同学', role='STUDENT', is_active=1, password=password),
        2: dict(id=2, username='worker', real_name='师傅', role='WORKER', is_active=1, password=password),
        3: dict(id=3, username='admin', real_name='管理员', role='ADMIN', is_active=1, password=password),
        4: dict(id=4, username='other', real_name='另一位同学', role='STUDENT', is_active=1, password=password),
        5: dict(id=5, username='old-worker', real_name='原师傅', role='WORKER', is_active=1, password=password),
    }
    order = dict(id=101, student_id=1, worker_id=2)
    monkeypatch.setattr(auth_service, 'get_db', lambda: object())
    monkeypatch.setattr(auth_service.user_repository, 'find_login_user',
                        lambda conn, username: next((u for u in users.values() if u['username'] == username), None))
    monkeypatch.setattr(auth_service.user_repository, 'find_active_identity', lambda conn, uid: users.get(uid))
    monkeypatch.setattr('app.services.access_control.find_order', lambda conn, oid: order if oid == 101 else None)
    add_probes(app)
    return app, users, order


def token_for(app, uid):
    with app.app_context():
        return auth_service.serializer().dumps({'uid': str(uid)})


def headers(app, uid):
    return {'Authorization': 'Bearer ' + token_for(app, uid)}


def test_login_contract_and_password_preservation(auth_app):
    app, users, _ = auth_app
    client = app.test_client()
    response = client.post('/api/auth/login', json={'username': ' student ', 'password': ' secret '})
    assert response.status_code == 200
    data = response.json['data']
    assert data['user'] == {'id': '1', 'realName': '同学', 'role': 'STUDENT'}
    assert data['expiresIn'] == 28800
    with app.app_context():
        assert auth_service.serializer().loads(data['token']) == {'uid': '1'}
    assert 'password' not in response.get_data(as_text=True)
    assert client.post('/api/auth/login', json={'username': 'student', 'password': 'secret'}).status_code == 401
    wrong = client.post('/api/auth/login', json={'username': 'student', 'password': 'wrong'})
    missing = client.post('/api/auth/login', json={'username': 'missing', 'password': 'wrong'})
    users[1]['is_active'] = 0
    disabled = client.post('/api/auth/login', json={'username': 'student', 'password': ' secret '})
    assert wrong.json == missing.json == disabled.json


@pytest.mark.parametrize('payload', [None, [], 'hello', {}, {'username': 'student'},
    {'username': 'student', 'password': True}, {'username': 1, 'password': 'x'},
    {'username': ' ', 'password': 'x'}, {'username': 'x' * 51, 'password': 'x'},
    {'username': 'student', 'password': ''},
    {'username': 'student', 'password': ' secret ', 'role': 'ADMIN'},
    {'username': 'student', 'password': ' secret ', 'studentId': '1'}])
def test_login_invalid_fields(auth_app, payload):
    app, _, _ = auth_app
    # Explicit JSON null should still produce a 400 JSON object validation error.
    import json
    response = app.test_client().post('/api/auth/login', data=json.dumps(payload), content_type='application/json')
    assert response.status_code == 400


@pytest.mark.parametrize('header', ['', 'Basic abc', 'Bearer', 'Bearer a b', 'Bearer ' + 'a' * 4097])
def test_missing_or_malformed_authorization(auth_app, header):
    app, _, _ = auth_app
    response = app.test_client().get('/api/_test/identity', headers={'Authorization': header})
    assert response.status_code == 401


def test_bad_expired_and_forged_tokens(auth_app):
    app, _, _ = auth_app
    with app.app_context():
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp', return_value=int(time.time()) - 28801):
            expired = auth_service.serializer().dumps({'uid': '1'})
        forged = URLSafeTimedSerializer('different-key', salt=auth_service.TOKEN_SALT).dumps({'uid': '1'})
        bad_payloads = [auth_service.serializer().dumps(value) for value in (
            {'uid': True}, {'uid': 1}, {'uid': '0'}, {'uid': '-1'}, {'uid': '9223372036854775808'},
            {'uid': '1', 'role': 'ADMIN'}, {}, [], {'uid': '999'},
        )]
    for token in ['broken-token', expired, forged] + bad_payloads:
        response = app.test_client().get('/api/_test/identity', headers={'Authorization': 'Bearer ' + token})
        assert response.status_code == 401


def test_current_role_and_disabled_state_rechecked(auth_app):
    app, users, _ = auth_app
    client = app.test_client()
    auth = headers(app, 1)
    assert client.get('/api/_test/identity', headers=auth).status_code == 200
    assert client.get('/api/_test/admin', headers=auth).status_code == 403
    # Role must come from the current database row, not the token.
    users[1]['role'] = 'ADMIN'
    assert client.get('/api/_test/admin', headers=auth).status_code == 200
    users[1]['is_active'] = 0
    assert client.get('/api/_test/admin', headers=auth).status_code == 401
    del users[1]
    assert client.get('/api/_test/identity', headers=auth).status_code == 401


def test_role_checks_precede_business_body_validation(auth_app):
    app, _, _ = auth_app
    client = app.test_client()
    assert client.post('/api/_test/admin', data='{', content_type='application/json').status_code == 401
    assert client.post('/api/_test/admin', headers=headers(app, 1), data='{', content_type='application/json').status_code == 403
    assert client.post('/api/_test/admin', headers=headers(app, 3), data='{', content_type='application/json').status_code == 400
    assert client.get('/api/_test/worker', headers=headers(app, 1)).status_code == 403
    assert client.get('/api/_test/worker', headers=headers(app, 2)).status_code == 200
    assert client.options('/api/_test/admin', headers={'Origin': 'http://127.0.0.1:5173'}).status_code == 200


def test_order_ownership_and_reassignment(auth_app):
    app, _, order = auth_app
    client = app.test_client()
    for uid in (1, 2, 3):
        assert client.get('/api/_test/orders/101', headers=headers(app, uid)).status_code == 200
    forbidden = client.get('/api/_test/orders/101', headers=headers(app, 4))
    missing = client.get('/api/_test/orders/102', headers=headers(app, 4))
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json == missing.json
    order['worker_id'] = 5
    assert client.get('/api/_test/orders/101', headers=headers(app, 2)).status_code == 404
    assert client.get('/api/_test/orders/101', headers=headers(app, 5)).status_code == 200
    assert client.get('/api/_test/orders/0', headers=headers(app, 1)).status_code == 400


@pytest.mark.database
@pytest.mark.skipif(os.environ.get('RUN_DB_TESTS') != '1', reason='Set RUN_DB_TESTS=1')
@pytest.mark.parametrize('username,role', [('stu1', 'STUDENT'), ('worker1', 'WORKER'),
                                         ('worker2', 'WORKER'), ('admin', 'ADMIN')])
def test_real_seeded_login_and_identity(username, role):
    app = create_app({'TESTING': True})
    add_probes(app)
    client = app.test_client()
    response = client.post('/api/auth/login', json={'username': username, 'password': 'Demo@123456'})
    assert response.status_code == 200
    user = response.json['data']['user']
    assert user['role'] == role and isinstance(user['id'], str)
    auth = {'Authorization': 'Bearer ' + response.json['data']['token']}
    assert client.get('/api/_test/identity', headers=auth).json['data'] == user
    assert client.get('/api/_test/admin', headers=auth).status_code == (200 if role == 'ADMIN' else 403)
    wrong = client.post('/api/auth/login', json={'username': username, 'password': 'wrong'})
    assert wrong.status_code == 401
