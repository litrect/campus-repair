def find_order(conn, order_id):
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM repair_order WHERE id=%s', (order_id,))
        return cursor.fetchone()


def find_idempotent(conn, student_id, token):
    with conn.cursor() as cursor:
        cursor.execute('SELECT id,order_no,status,version,request_hash FROM repair_order '
                       'WHERE student_id=%s AND request_token=%s', (student_id, token))
        return cursor.fetchone()


def insert_order(conn, student_id, token, digest, data, order_no, event_time, deadline):
    with conn.cursor() as cursor:
        cursor.execute('INSERT INTO repair_order '
                       '(order_no,student_id,request_token,request_hash,category,location,description,'
                       'urgency,image_url,create_time,deadline) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                       (order_no, student_id, token, digest, data['category'], data['location'],
                        data['description'], data['urgency'], data['imageUrl'], event_time, deadline))
        return cursor.lastrowid


def insert_create_log(conn, order_id, student_id, event_time):
    with conn.cursor() as cursor:
        cursor.execute('INSERT INTO order_log '
                       '(order_id,event_type,to_status,order_version,operator_id,create_time) '
                       'VALUES (%s,%s,%s,%s,%s,%s)', (order_id, 'CREATE', 'CREATED', 0, student_id, event_time))


def list_owned(conn, actor, page, page_size, status=None):
    # Column is selected from trusted server-side role values, never client SQL.
    column = 'student_id' if actor['role'] == 'STUDENT' else 'worker_id'
    where = f'{column}=%s'
    params = [actor['id']]
    if status is not None:
        where += ' AND status=%s'
        params.append(status)
    with conn.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) AS total FROM repair_order WHERE {where}', params)
        total = cursor.fetchone()['total']
        cursor.execute(f'SELECT * FROM repair_order WHERE {where} '
                       'ORDER BY create_time DESC,id DESC LIMIT %s OFFSET %s',
                       params + [page_size, (page - 1) * page_size])
        return cursor.fetchall(), total


def get_evaluation(conn, order_id):
    with conn.cursor() as cursor:
        cursor.execute('SELECT id,score,content,create_time FROM evaluation WHERE order_id=%s', (order_id,))
        return cursor.fetchone()


def get_logs(conn, order_id):
    with conn.cursor() as cursor:
        cursor.execute('SELECT id,event_type,from_status,to_status,order_version,operator_id,'
                       'from_worker_id,to_worker_id,remark,create_time FROM order_log '
                       'WHERE order_id=%s ORDER BY order_version ASC', (order_id,))
        return cursor.fetchall()


def cancellation_time(conn, order_id):
    with conn.cursor() as cursor:
        cursor.execute("SELECT create_time FROM order_log WHERE order_id=%s AND event_type='CANCEL' "
                       'ORDER BY order_version DESC LIMIT 1', (order_id,))
        row = cursor.fetchone()
        return row['create_time'] if row else None


def worker_can_read_image(conn, image_url, worker_id):
    with conn.cursor() as cursor:
        cursor.execute('SELECT id FROM repair_order WHERE image_url=%s AND worker_id=%s LIMIT 1',
                       (image_url, worker_id))
        return cursor.fetchone() is not None


def list_pending(conn, page, page_size):
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM repair_order WHERE status='CREATED'")
        total = cursor.fetchone()['total']
        cursor.execute("SELECT * FROM repair_order WHERE status='CREATED' "
                       'ORDER BY create_time DESC,id DESC LIMIT %s OFFSET %s',
                       (page_size, (page - 1) * page_size))
        return cursor.fetchall(), total


def update_for_event(conn, order, expected_version, actor, fields):
    allowed = {'status', 'worker_id', 'assign_time', 'accept_time', 'finish_time',
               'repair_record', 'close_time', 'is_overtime'}
    if not fields or set(fields) - allowed:
        raise ValueError('Unexpected order update fields')
    assignments = ','.join(f'{column}=%s' for column in fields)
    query = f'UPDATE repair_order SET {assignments},version=version+1 WHERE id=%s AND status=%s AND version=%s'
    params = list(fields.values()) + [order['id'], order['status'], expected_version]
    if actor is not None and actor['role'] == 'WORKER':
        query += ' AND worker_id=%s'
        params.append(actor['id'])
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.rowcount


def insert_event_log(conn, order, event, target_status, actor_id, version, event_time,
                     *, remark=None, from_worker=None, to_worker=None):
    with conn.cursor() as cursor:
        cursor.execute('INSERT INTO order_log '
                       '(order_id,event_type,from_status,to_status,order_version,operator_id,'
                       'from_worker_id,to_worker_id,remark,create_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                       (order['id'], event, order['status'], target_status, version, actor_id,
                        from_worker, to_worker, remark, event_time))
