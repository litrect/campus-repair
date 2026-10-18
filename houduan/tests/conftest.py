"""Real API tests use a fresh isolated database per test module."""
import json
import uuid

import pymysql
import pytest

from app import create_app
from app.config import ROOT


@pytest.fixture(scope='module')
def env(tmp_path_factory):
    local = json.loads((ROOT / 'instance/mysql-local.json').read_text(encoding='utf-8'))
    name = 'a2_api_' + uuid.uuid4().hex
    admin = pymysql.connect(host=local['host'], port=local['port'], user='root',
                            password=local['root_password'], charset='utf8mb4', autocommit=True,
                            cursorclass=pymysql.cursors.DictCursor)
    with admin.cursor() as cursor:
        for script in ('schema.sql', 'seed.sql'):
            sql = (ROOT / 'sql' / script).read_text(encoding='utf-8').replace('campus_repair', name)
            for statement in sql.split(';'):
                if statement.strip():
                    cursor.execute(statement)
        cursor.execute(f"GRANT SELECT,INSERT,UPDATE ON `{name}`.* TO 'campus_app'@'127.0.0.1'")
        cursor.execute("INSERT INTO user(username,password,real_name,role) "
                       "SELECT 'stu2',password,'另一位学生','STUDENT' FROM user WHERE username='stu1'")
        cursor.execute('SELECT id,username FROM user')
        users = {row['username']: row['id'] for row in cursor.fetchall()}
    app = create_app({'TESTING': True, 'DB_HOST': local['host'], 'DB_PORT': local['port'],
                      'DB_USER': local['user'], 'DB_PASSWORD': local['password'], 'DB_NAME': name},
                     instance_path=tmp_path_factory.mktemp('api-app'))
    yield app, admin, users
    admin.close()
