import re

from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db
from ..errors import BusinessError
from ..repositories import user_repository

ROLES = frozenset(('STUDENT', 'WORKER', 'ADMIN'))
MAX_ID = 9_223_372_036_854_775_807
TOKEN_SALT = 'campus-repair-auth-v1'
# A missing username still performs a real password derivation.
DUMMY_HASH = generate_password_hash('dummy-account-not-used', method='pbkdf2:sha256:600000')


def serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=TOKEN_SALT)


def public_identity(user):
    return {'id': str(user['id']), 'realName': user['real_name'], 'role': user['role']}


def login(username, password):
    user = user_repository.find_login_user(get_db(), username)
    stored = user['password'] if user else DUMMY_HASH
    try:
        password_ok = check_password_hash(stored, password)
    except (ValueError, TypeError):
        password_ok = False
    if not password_ok or not user or user['is_active'] != 1 or user['role'] not in ROLES:
        raise BusinessError('账号或密码错误', 401)
    return {
        'token': serializer().dumps({'uid': str(user['id'])}),
        'expiresIn': current_app.config['TOKEN_MAX_AGE'],
        'user': public_identity(user),
    }


def authenticate(token):
    try:
        payload = serializer().loads(token, max_age=current_app.config['TOKEN_MAX_AGE'])
    except BadData:
        raise BusinessError('登录已失效，请重新登录', 401) from None
    uid = payload.get('uid') if isinstance(payload, dict) else None
    if (not isinstance(uid, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', uid)
            or int(uid) > MAX_ID or set(payload) != {'uid'}):
        raise BusinessError('登录已失效，请重新登录', 401)
    user = user_repository.find_active_identity(get_db(), int(uid))
    if not user or user['is_active'] != 1 or user['role'] not in ROLES:
        raise BusinessError('登录已失效，请重新登录', 401)
    return user
