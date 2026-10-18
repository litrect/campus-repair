"""Start, stop or inspect the project-local MySQL server without displaying credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parent.parent
config = json.loads((root / 'instance/mysql-local.json').read_text(encoding='utf-8'))
home = root / 'tools/mysql-8.0.46-winx64'
config['mysql'] = str(home / 'bin/mysql.exe')
config['mysqld'] = str(home / 'bin/mysqld.exe')
config['server_args'] = [
    '--no-defaults', f'--basedir={home.as_posix()}',
    f'--datadir={(root / "instance/mysql-data").as_posix()}',
    '--bind-address=127.0.0.1', '--port=3306', '--mysqlx=OFF',
    '--default-time-zone=+08:00',
    f'--log-error={(root / "instance/mysql-error.log").as_posix()}',
    '--sql-mode=STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION',
]
# Refresh only installation paths; preserve database credentials when the project moves.
(root / 'instance/mysql-local.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
env = dict(os.environ, MYSQL_PWD=config['root_password'])
client = [config['mysql'], '--no-defaults', '--protocol=TCP', '--host=127.0.0.1',
          '--port=3306', '--user=root']
action = sys.argv[1] if len(sys.argv) > 1 else 'status'

def status():
    return subprocess.run(client + ['--execute=SELECT VERSION();'], env=env, capture_output=True)

if action == 'start':
    if status().returncode == 0:
        print('MySQL is already running.')
    else:
        proc = subprocess.Popen([config['mysqld']] + config['server_args'],
                                creationflags=subprocess.CREATE_NO_WINDOW,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        for _ in range(60):
            if status().returncode == 0:
                print('MySQL started on 127.0.0.1:3306.')
                break
            if proc.poll() is not None:
                raise SystemExit('Startup failed; inspect instance/mysql-error.log.')
            time.sleep(1)
        else:
            raise SystemExit('Startup timed out.')
elif action == 'stop':
    subprocess.run(client + ['--execute=SHUTDOWN;'], env=env, check=True)
    print('Shutdown requested.')
elif action == 'status':
    result = status()
    print(result.stdout.decode(errors='replace') if result.returncode == 0 else 'MySQL not available.')
    sys.exit(result.returncode)
else:
    raise SystemExit('Usage: local_mysql.py start|stop|status')
