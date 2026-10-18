"""Central authentication guard and route-level role authorization."""
from functools import wraps

from flask import g, request

from .errors import BusinessError
from .services.auth_service import authenticate

PUBLIC_ENDPOINTS = frozenset(('api.login', 'api.health', 'api.ready'))


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = g.get('current_user')
            if user is None:
                raise BusinessError('请先登录', 401)
            if user['role'] not in roles:
                raise BusinessError('无权执行此操作', 403)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def init_app(app):
    @app.before_request
    def authenticate_api():
        if request.blueprint != 'api' or request.endpoint in PUBLIC_ENDPOINTS or request.method == 'OPTIONS':
            return
        authorization = request.headers.get('Authorization', '')
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer' or len(parts[1]) > 4096:
            raise BusinessError('请先登录', 401)
        g.current_user = authenticate(parts[1])
