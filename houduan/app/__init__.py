import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, abort, request, send_from_directory

from .config import ROOT, load_config
from .responses import APIJSONProvider


def create_app(test_config=None, *, instance_path=None):
    instance = Path(instance_path or ROOT / 'instance').resolve()
    instance.mkdir(parents=True, exist_ok=True)
    frontend_dist = ROOT.parent / 'qianduan' / 'campus-repair-frontend' / 'dist'
    app = Flask(__name__, instance_path=str(instance),
                static_folder=str(frontend_dist / 'assets'), static_url_path='/assets')
    app.json = APIJSONProvider(app)
    app.config.from_mapping(load_config(instance))
    if test_config:
        app.config.update(test_config)

    from . import auth, db, errors
    from .api import api
    db.init_app(app)
    errors.init_app(app)
    auth.init_app(app)
    app.register_blueprint(api)

    @app.get('/')
    def frontend_index():
        if not (frontend_dist / 'index.html').is_file():
            abort(404)
        return send_from_directory(frontend_dist, 'index.html')

    Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
    logs = instance / 'logs'
    logs.mkdir(exist_ok=True)
    log_path = str(logs / 'app.log')
    if not any(isinstance(handler, RotatingFileHandler) and handler.baseFilename == log_path
               for handler in app.logger.handlers):
        handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    @app.after_request
    def response_headers(response):
        origin = request.headers.get('Origin')
        if origin:
            response.vary.add('Origin')
            if origin in app.config['CORS_ORIGINS']:
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, Idempotency-Key'
                response.headers['Access-Control-Max-Age'] = '600'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response

    return app
