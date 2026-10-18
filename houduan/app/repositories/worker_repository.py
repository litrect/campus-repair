def lock_worker(conn, worker_id):
    with conn.cursor() as cursor:
        # Current locking read protects the target against concurrent disable/role changes.
        cursor.execute('SELECT id,role,is_active FROM user WHERE id=%s FOR SHARE', (worker_id,))
        return cursor.fetchone()


def available_workers(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT u.id,u.real_name,u.skill,COALESCE(workload.n,0) AS active_count "
                       "FROM user u LEFT JOIN (SELECT worker_id,COUNT(*) AS n FROM repair_order "
                       "WHERE status IN ('ASSIGNED','PROCESSING') GROUP BY worker_id) workload "
                       "ON workload.worker_id=u.id WHERE u.role='WORKER' AND u.is_active=1")
        return cursor.fetchall()
