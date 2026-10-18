"""Run isolated database checks using the local configuration without exposing passwords."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
config = json.loads((root / 'instance/mysql-local.json').read_text(encoding='utf-8'))
client = root / 'tools/mysql-8.0.46-winx64/bin/mysql.exe'
database = 'a2_verify_' + datetime.now().strftime('%Y%m%d_%H%M%S')
subprocess.run([
    sys.executable, str(root / 'scripts/verify_delivery.py'), '--mysql', str(client),
    '--host', config['host'], '--port', str(config['port']), '--database', database,
    '--report', str(root / 'docs/database-verification-results.json'),
], env=dict(os.environ, MYSQL_PWD=config['root_password']), check=True)
subprocess.run([
    str(client), '--no-defaults', '--protocol=TCP', f"--host={config['host']}",
    f"--port={config['port']}", f"--user={config['user']}",
    f"--database={config['database']}", '--batch',
    '--execute=SELECT COUNT(*) AS users FROM user; SELECT COUNT(*) AS orders FROM repair_order;',
], env=dict(os.environ, MYSQL_PWD=config['password']), check=True)
