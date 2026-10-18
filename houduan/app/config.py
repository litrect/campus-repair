"""Load local configuration without importing database administrator credentials."""
import json
import os
from pathlib import Path
import secrets

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


def load_config(instance: Path) -> dict:
    values = {**dotenv_values(ROOT / '.env'), **os.environ}
    local_path = instance / 'mysql-local.json'
    local = json.loads(local_path.read_text(encoding='utf-8')) if local_path.exists() else {}

    def setting(name, default=None):
        return values.get(name) or default

    secret = setting('APP_SECRET_KEY')
    if not secret:
        secret_path = instance / 'secret.key'
        try:
            with secret_path.open('x', encoding='utf-8') as file:
                file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = secret_path.read_text(encoding='utf-8').strip()
    if len(secret) < 32:
        raise ValueError('APP_SECRET_KEY must contain at least 32 characters.')

    origins = tuple(origin.strip() for origin in setting(
        'CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173'
    ).split(',') if origin.strip())
    if '*' in origins:
        raise ValueError('CORS_ORIGINS must list explicit origins.')
    return {
        'SECRET_KEY': secret,
        'DB_HOST': setting('DB_HOST', local.get('host', '127.0.0.1')),
        'DB_PORT': int(setting('DB_PORT', local.get('port', 3306))),
        'DB_NAME': setting('DB_NAME', local.get('database', 'campus_repair')),
        'DB_USER': setting('DB_USER', local.get('user', 'campus_app')),
        'DB_PASSWORD': setting('DB_PASSWORD', local.get('password')),
        'DB_CONNECT_TIMEOUT': 5,
        'DB_READ_TIMEOUT': 10,
        'DB_WRITE_TIMEOUT': 10,
        'CORS_ORIGINS': origins,
        'TOKEN_MAX_AGE': 8 * 60 * 60,
        'ORDER_CATEGORIES': ('水电', '门锁', '网络', '家具', '其他'),
        'SLA_HOURS': {'HIGH': 4, 'NORMAL': 24, 'LOW': 72},
        'RECOMMENDATION_SKILL_WEIGHT': 100,
        'RECOMMENDATION_LOAD_PENALTY': 10,
        'OVERTIME_SCAN_SECONDS': 60,
        'IMAGE_MAX_BYTES': 2_097_152,
        # Multipart metadata requires headroom; the image itself is checked separately.
        'MAX_CONTENT_LENGTH': 2_097_152 + 65_536,
        'UPLOAD_FOLDER': str(instance / 'uploads'),
        'JSON_SORT_KEYS': False,
    }
