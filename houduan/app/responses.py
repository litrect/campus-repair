from datetime import datetime, timezone, timedelta

from flask import jsonify
from flask.json.provider import DefaultJSONProvider

CHINA_TZ = timezone(timedelta(hours=8))


class APIJSONProvider(DefaultJSONProvider):
    ensure_ascii = False
    sort_keys = False

    @staticmethod
    def default(value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=CHINA_TZ)
            return value.astimezone(CHINA_TZ).isoformat(timespec='seconds')
        return DefaultJSONProvider.default(value)


def success(data=None, message='成功', status=200):
    return jsonify(code=0, message=message, data=data), status


def failure(status, message, code=None):
    return jsonify(code=code if code is not None else status, message=message, data=None), status
