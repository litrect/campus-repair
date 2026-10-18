def ping(conn):
    with conn.cursor() as cursor:
        cursor.execute('SELECT 1 AS ready')
        return cursor.fetchone()['ready'] == 1
