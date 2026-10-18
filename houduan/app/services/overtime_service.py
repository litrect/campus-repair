import pymysql

from flask import current_app

from ..db import get_db
from ..repositories.report_repository import scan_candidates
from .order_service import now_local
from .workflow_service import change_status


def scan_once():
    event_time = now_local()
    after_id = marked = skipped = 0
    while True:
        candidates = scan_candidates(get_db(), event_time, after_id)
        if not candidates:
            break
        for row in candidates:
            after_id = row['id']
            try:
                changed = change_status(row['id'], row['version'], 'OVERTIME', None, {'event_time': event_time})
                marked += int(changed)
                skipped += int(not changed)
            except pymysql.MySQLError as error:
                current_app.logger.error('Overtime update failed (order_id=%s, error=%s)',
                                         row['id'], type(error).__name__)
                skipped += 1
    return {'marked': marked, 'skipped': skipped}
