from . import api
from ..errors import BusinessError
from ..responses import success
from ..services.auth_service import login as login_user
from ..validation import json_object


@api.post('/auth/login')
def login():
    data = json_object(required=('username', 'password'))
    username, password = data['username'], data['password']
    if (not isinstance(username, str) or not username.strip() or len(username.strip()) > 50
            or not isinstance(password, str) or not password):
        raise BusinessError('请填写有效的用户名和密码', 400)
    # Passwords are deliberately not trimmed.
    return success(login_user(username.strip(), password), message='登录成功')
