"""Run one scanner pass when the API's automatic scanner is stopped."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app
from app.tasks.overtime import OvertimeScheduler

if __name__ == '__main__':
    print(OvertimeScheduler(create_app()).run_once())
