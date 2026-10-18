"""Only the login lookup may retrieve a password hash."""


def find_login_user(conn, username):
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT id, username, password, real_name, role, is_active FROM user WHERE username=%s',
            (username,),
        )
        return cursor.fetchone()


def find_active_identity(conn, user_id):
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT id, real_name, role, is_active FROM user WHERE id=%s', (user_id,),
        )
        return cursor.fetchone()
