"""Request-scoped MySQL connections and explicit service transaction boundaries."""
from contextlib import contextmanager

from flask import current_app, g
import pymysql

SQL_MODE = 'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'


def get_db():
    if 'db' not in g:
        cfg = current_app.config
        g.db = pymysql.connect(
            host=cfg['DB_HOST'], port=cfg['DB_PORT'], user=cfg['DB_USER'],
            password=cfg['DB_PASSWORD'], database=cfg['DB_NAME'], charset='utf8mb4',
            autocommit=False, cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=cfg['DB_CONNECT_TIMEOUT'], read_timeout=cfg['DB_READ_TIMEOUT'],
            write_timeout=cfg['DB_WRITE_TIMEOUT'],
            init_command=f"SET time_zone='+08:00', SESSION sql_mode='{SQL_MODE}'",
        )
    return g.db


@contextmanager
def transaction():
    """One business action commits once; any exception rolls back the entire action."""
    if g.get('transaction_active', False):
        raise RuntimeError('Nested service transactions are not supported.')
    conn = get_db()
    g.transaction_active = True
    try:
        conn.begin()
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        g.transaction_active = False


def close_db(error=None):
    conn = g.pop('db', None)
    if conn is not None:
        try:
            conn.rollback()
        finally:
            conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
