from datetime import datetime
import json
import os
from unittest.mock import patch
import uuid

import pymysql
import pytest

from app import create_app
from app.db import get_db, transaction
from app.errors import BusinessError
from app.responses import success


@pytest.fixture
def app(tmp_path):
    app = create_app({'TESTING': True}, instance_path=tmp_path)

    @app.get('/test/business')
    def business():
        raise BusinessError('版本冲突，请刷新', 409)

    @app.get('/test/unexpected')
    def unexpected():
        raise RuntimeError('sensitive-password-must-not-leak')

    @app.post('/test/json')
    def parse_json():
        from flask import request
        return success(request.get_json())

    @app.get('/test/time')
    def time_value():
        return success({'at': datetime(2026, 10, 15, 12, 30, 0), 'id': '9223372036854775807'})

    return app


def test_health_and_error_envelopes(app):
    client = app.test_client()
    assert client.get('/api/health').json == {'code': 0, 'message': '成功', 'data': {'status': 'ok'}}
    for path, code in [('/not-found', 404), ('/test/business', 409), ('/test/unexpected', 500)]:
        response = client.get(path)
        assert response.status_code == code
        assert response.json['code'] == code
        assert response.json['data'] is None
        assert 'sensitive-password' not in response.get_data(as_text=True)
    response = client.post('/api/health')
    assert response.status_code == 405
    assert 'GET' in response.headers['Allow']


def test_json_validation_and_time(app):
    client = app.test_client()
    response = client.post('/test/json', data='{', content_type='application/json')
    assert response.status_code == 400
    assert client.post('/test/json', data='hello').status_code == 415
    assert client.get('/test/time').json['data'] == {
        'at': '2026-10-15T12:30:00+08:00', 'id': '9223372036854775807'}


def test_cors_allowlist_and_preflight(app):
    client = app.test_client()
    response = client.options('/api/health', headers={
        'Origin': 'http://127.0.0.1:5173', 'Access-Control-Request-Method': 'GET'})
    assert response.headers['Access-Control-Allow-Origin'] == 'http://127.0.0.1:5173'
    assert 'Authorization' in response.headers['Access-Control-Allow-Headers']
    denied = client.get('/api/health', headers={'Origin': 'https://untrusted.example'})
    assert 'Access-Control-Allow-Origin' not in denied.headers
    assert 'Origin' in denied.headers['Vary']


def test_secret_persistence_and_no_root_config(tmp_path):
    (tmp_path / 'mysql-local.json').write_text(json.dumps({
        'user': 'campus_app', 'password': 'app-only', 'root_password': 'not-imported'}))
    first = create_app(instance_path=tmp_path)
    second = create_app(instance_path=tmp_path)
    assert first.secret_key == second.secret_key
    assert len(first.secret_key) >= 32
    assert 'root_password' not in first.config
    assert 'not-imported' not in str(dict(first.config))


def test_database_failure_is_generic(app):
    with patch('app.db.pymysql.connect', side_effect=pymysql.OperationalError(2003, 'private credentials')):
        response = app.test_client().get('/api/health/ready')
    assert response.status_code == 503
    assert response.json['code'] == 503
    assert 'private credentials' not in response.get_data(as_text=True)


@pytest.mark.database
@pytest.mark.skipif(os.environ.get('RUN_DB_TESTS') != '1', reason='Set RUN_DB_TESTS=1 for local MySQL checks')
def test_real_database_transaction_and_connection_cleanup():
    app = create_app({'TESTING': True})
    assert app.test_client().get('/api/health/ready').status_code == 200
    username = 'rollback_' + uuid.uuid4().hex
    with app.app_context():
        conn = get_db()
        assert get_db() is conn
        with conn.cursor() as cursor:
            cursor.execute('SELECT @@session.time_zone AS tz, @@autocommit AS ac, @@sql_mode AS mode')
            session = cursor.fetchone()
        assert session['tz'] == '+08:00' and session['ac'] == 0
        assert 'STRICT_TRANS_TABLES' in session['mode']
        with pytest.raises(RuntimeError, match='rollback probe'):
            with transaction() as transaction_conn:
                with transaction_conn.cursor() as cursor:
                    cursor.execute('INSERT INTO user(username,password,real_name,role) VALUES (%s,%s,%s,%s)',
                                   (username, 'not-a-login-hash', 'rollback probe', 'STUDENT'))
                raise RuntimeError('rollback probe')
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM user WHERE username=%s', (username,))
            assert cursor.fetchone()['n'] == 0
        with transaction():
            with pytest.raises(RuntimeError, match='Nested'):
                with transaction():
                    pass
    assert not conn.open
