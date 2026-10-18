"""Install the official downloaded ZIP into this project and initialize a new instance."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools'
INSTANCE = ROOT / 'instance'
HOME = TOOLS / 'mysql-8.0.46-winx64'
DATA = INSTANCE / 'mysql-data'
CREDS = INSTANCE / 'mysql-local.json'


def mysql_path(path):
    return Path(path).as_posix()


def main():
    if DATA.exists() or CREDS.exists():
        raise RuntimeError('Existing data/config found; refusing to initialize again.')
    if not HOME.exists():
        with zipfile.ZipFile(TOOLS / 'mysql-8.0.46-winx64.zip') as archive:
            archive.extractall(TOOLS)
    server = HOME / 'bin/mysqld.exe'
    client = HOME / 'bin/mysql.exe'
    server = Path(mysql_path(server))
    client = Path(mysql_path(client))
    subprocess.run([str(server), '--version'], check=True)
    INSTANCE.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    subprocess.run([str(server), '--no-defaults', '--initialize-insecure',
                    f'--basedir={mysql_path(HOME)}', f'--datadir={mysql_path(DATA)}',
                    '--console'], check=True)
    args = [str(server), '--no-defaults', f'--basedir={mysql_path(HOME)}',
            f'--datadir={mysql_path(DATA)}', '--bind-address=127.0.0.1', '--port=3306',
            '--mysqlx=OFF', '--default-time-zone=+08:00',
            f'--log-error={mysql_path(INSTANCE)}/mysql-error.log',
            '--sql-mode=STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION']
    root_password = secrets.token_hex(24)
    app_password = secrets.token_hex(24)
    # Save recovery credentials before launching; never print passwords.
    config = dict(host='127.0.0.1', port=3306, database='campus_repair',
                  user='campus_app', password=app_password, root_password=root_password,
                  mysql=str(client), mysqld=str(server), server_args=args[1:])
    CREDS.write_text(json.dumps(config, indent=2), encoding='utf-8')
    process = subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    base = [str(client), '--no-defaults', '--protocol=TCP', '--host=127.0.0.1',
            '--port=3306', '--user=root', '--default-character-set=utf8mb4', '--batch']
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError('MySQL exited; inspect instance/mysql-error.log.')
        ready = subprocess.run(base + ['--execute=SELECT 1'], capture_output=True)
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('MySQL startup timed out.')
    subprocess.run(base, input=f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{root_password}';",
                   text=True, encoding='utf-8', check=True, capture_output=True)
    env = dict(os.environ, MYSQL_PWD=root_password)
    for name in ('schema.sql', 'seed.sql'):
        subprocess.run(base, input=(ROOT / 'sql' / name).read_text(encoding='utf-8'),
                       text=True, encoding='utf-8', check=True, env=env, capture_output=True)
    permissions = f"""CREATE USER 'campus_app'@'127.0.0.1' IDENTIFIED BY '{app_password}';
GRANT SELECT, INSERT, UPDATE ON campus_repair.* TO 'campus_app'@'127.0.0.1';"""
    subprocess.run(base, input=permissions, text=True, check=True, env=env, capture_output=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/verify_delivery.py'),
                    '--mysql', str(client), '--database', 'a2_verify_20261015',
                    '--report', str(ROOT / 'docs/database-verification-results.json')],
                   check=True, env=env)
    subprocess.run(base + ['--execute=USE campus_repair; SHOW TABLES; SELECT username,role,is_active FROM user;'],
                   check=True, env=env)
    print('Local MySQL ready on 127.0.0.1:3306. Credentials saved in instance/mysql-local.json.')


if __name__ == '__main__':
    main()
