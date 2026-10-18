import pymysql
from werkzeug.exceptions import HTTPException

from .responses import failure


class BusinessError(Exception):
    def __init__(self, message, status=422, code=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def init_app(app):
    @app.errorhandler(BusinessError)
    def business_error(error):
        return failure(error.status, error.message, error.code)

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {
            400: '请求参数格式错误', 401: '请先登录', 403: '无权执行此操作',
            404: '资源不存在或不可访问', 405: '请求方法不支持',
            413: '上传内容超过限制', 415: '请求必须使用 JSON 格式',
        }
        response, status = failure(error.code, messages.get(error.code, '请求失败'))
        # Retain protocol headers such as Allow for a 405 response.
        for key, value in error.get_headers():
            if key.lower() not in ('content-type', 'content-length'):
                response.headers[key] = value
        return response, status

    @app.errorhandler(pymysql.MySQLError)
    def database_error(error):
        # Do not log exception arguments: SQL errors can contain user data.
        app.logger.error('Database request failed (%s)', type(error).__name__)
        return failure(503, '数据库暂时不可用，请稍后重试')

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.error('Unhandled request error (%s)', type(error).__name__)
        return failure(500, '服务暂时不可用，请稍后重试')
