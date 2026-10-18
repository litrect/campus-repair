def insert_evaluation(conn, order_id, score, content):
    with conn.cursor() as cursor:
        cursor.execute('INSERT INTO evaluation(order_id,score,content) VALUES (%s,%s,%s)',
                       (order_id, score, content))
        return cursor.lastrowid


def evaluations(conn, worker_id, page, page_size):
    where = 'o.worker_id=%s' if worker_id is not None else '1=1'
    params = [worker_id] if worker_id is not None else []
    with conn.cursor() as cursor:
        cursor.execute('SELECT AVG(e.score) AS average,COUNT(*) AS n FROM evaluation e '
                       f'JOIN repair_order o ON o.id=e.order_id WHERE {where}', params)
        aggregate = cursor.fetchone()
        cursor.execute('SELECT e.id,e.order_id,e.score,e.content,e.create_time,o.worker_id '
                       f'FROM evaluation e JOIN repair_order o ON o.id=e.order_id WHERE {where} '
                       'ORDER BY e.create_time DESC,e.id DESC LIMIT %s OFFSET %s',
                       params + [page_size, (page - 1) * page_size])
        return aggregate, cursor.fetchall()


def order_statistics(conn, metric, group_by, filters):
    time_column = 'o.close_time' if metric == 'completed' else 'o.create_time'
    where, params = [], []
    if metric == 'completed':
        where.append("o.status='CLOSED'")
    for name, operator in (('from', '>='), ('to', '<')):
        if filters[name] is not None:
            where.append(f'{time_column}{operator}%s')
            params.append(filters[name])
    for name in ('category', 'status'):
        if filters[name] is not None:
            where.append(f'o.{name}=%s')
            params.append(filters[name])
    expression = {'category': 'o.category', 'status': 'o.status',
                  'worker': 'o.worker_id', 'day': f'DATE({time_column})'}[group_by]
    join = 'LEFT JOIN user u ON u.id=o.worker_id' if group_by == 'worker' else ''
    extra_select = ',u.real_name AS worker_name' if group_by == 'worker' else ''
    extra_group = ',u.real_name' if group_by == 'worker' else ''
    with conn.cursor() as cursor:
        cursor.execute(f'SELECT {expression} AS bucket_key,COUNT(*) AS n{extra_select} '
                       f'FROM repair_order o {join} WHERE ' + (' AND '.join(where) or '1=1')
                       + f' GROUP BY {expression}{extra_group} ORDER BY {expression}', params)
        return cursor.fetchall()


def overtime_filter(scope, now):
    if scope == 'active':
        return "o.status IN ('CREATED','ASSIGNED','PROCESSING') AND o.deadline IS NOT NULL AND %s>o.deadline", [now]
    return ("(o.is_overtime=1 OR (o.deadline IS NOT NULL AND ("
            "(o.status IN ('CREATED','ASSIGNED','PROCESSING') AND %s>o.deadline) OR "
            "(o.status IN ('DONE','CLOSED') AND o.finish_time>o.deadline) OR "
            "(o.status='CANCELLED' AND EXISTS (SELECT 1 FROM order_log l WHERE l.order_id=o.id "
            "AND l.event_type='CANCEL' AND l.create_time>o.deadline)))))"), [now]


def overtime_orders(conn, scope, now, page, page_size):
    where, params = overtime_filter(scope, now)
    with conn.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) AS n FROM repair_order o WHERE {where}', params)
        total = cursor.fetchone()['n']
        cursor.execute(f'SELECT o.* FROM repair_order o WHERE {where} '
                       'ORDER BY o.create_time DESC,o.id DESC LIMIT %s OFFSET %s',
                       params + [page_size, (page - 1) * page_size])
        return cursor.fetchall(), total


def scan_candidates(conn, now, after_id, limit=200):
    where, params = overtime_filter('history', now)
    with conn.cursor() as cursor:
        cursor.execute(f'SELECT o.id,o.version FROM repair_order o WHERE {where} '
                       'AND o.is_overtime=0 AND o.deadline IS NOT NULL AND o.id>%s '
                       'ORDER BY o.id LIMIT %s', params + [after_id, limit])
        return cursor.fetchall()
