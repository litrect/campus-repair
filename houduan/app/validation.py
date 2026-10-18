import re

from flask import request

from .errors import BusinessError


def json_object(*, required=(), optional=()):
    data = request.get_json()
    if not isinstance(data, dict):
        raise BusinessError('请求体必须是 JSON 对象', 400)
    if set(data) - set(required) - set(optional):
        raise BusinessError('请求包含未知字段', 400)
    if set(required) - set(data):
        raise BusinessError('缺少必填字段', 400)
    return data


def positive_id(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', value)
            or int(value) > 9_223_372_036_854_775_807):
        raise BusinessError('ID 必须是有效的正十进制整数字符串', 400)
    return int(value)


def text_field(value, name, maximum, *, required=True):
    if not isinstance(value, str):
        raise BusinessError(f'{name}必须是字符串', 400)
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise BusinessError(f'{name}不能为空且最多 {maximum} 字符', 400)
    return value


def query_fields(allowed):
    if set(request.args) - set(allowed) or any(len(request.args.getlist(key)) != 1 for key in request.args):
        raise BusinessError('查询参数不合法', 400)
    return request.args


def pagination(args):
    def number(name, default, maximum):
        value = args.get(name, str(default))
        if not re.fullmatch(r'[1-9][0-9]{0,9}', value) or int(value) > maximum:
            raise BusinessError(f'{name}参数不合法', 400)
        return int(value)
    return number('page', 1, 2_147_483_647), number('pageSize', 20, 100)


def version_number(value):
    if type(value) is not int or not 0 <= value <= 2_147_483_646:
        raise BusinessError('version 必须是 0 至 2147483646 的整数', 400)
    return value
