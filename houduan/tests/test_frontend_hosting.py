from pathlib import Path
import re

from app import create_app
from app.config import ROOT


def test_built_frontend_and_assets_are_served_without_api_fallback(tmp_path):
    dist = ROOT.parent / 'qianduan/campus-repair-frontend/dist'
    assert (dist / 'index.html').is_file(), 'Build the frontend before deployment verification.'
    app = create_app({'TESTING': True}, instance_path=tmp_path)
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200 and response.mimetype == 'text/html'
    html = response.get_data(as_text=True)
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
    assert assets
    for asset in assets:
        assert client.get(asset).status_code == 200
    missing = client.get('/api/no-such-endpoint')
    assert missing.status_code == 404 and missing.is_json
    assert client.get('/assets/../../instance/mysql-local.json').status_code == 404
    assert client.get('/instance/mysql-local.json').status_code == 404
