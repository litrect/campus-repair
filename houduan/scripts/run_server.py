"""Run the local API with Waitress, without the Flask debug reloader."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from waitress import serve
from app import create_app
from app.tasks.overtime import OvertimeScheduler


if __name__ == '__main__':
    app = create_app()
    scheduler = OvertimeScheduler(app)
    scheduler.start()
    try:
        print('Campus repair API: http://127.0.0.1:5000', flush=True)
        serve(app, host='127.0.0.1', port=5000, threads=8)
    finally:
        scheduler.stop()
