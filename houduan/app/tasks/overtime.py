import msvcrt
from pathlib import Path
from threading import Event, Thread

from ..services.overtime_service import scan_once


class OvertimeScheduler:
    """Windows file lock ensures a single scanner for this project instance."""
    def __init__(self, app):
        self.app = app
        self.stop_event = Event()
        self.thread = None
        self.lock = None

    def acquire(self):
        if self.lock is not None:
            return
        path = Path(self.app.instance_path) / 'overtime.lock'
        self.lock = path.open('a+b')
        self.lock.seek(0, 2)
        if self.lock.tell() == 0:
            self.lock.write(b'0')
            self.lock.flush()
        self.lock.seek(0)
        try:
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.lock.close()
            self.lock = None
            raise RuntimeError('An overtime scanner is already running for this instance.') from None

    def release(self):
        if self.lock is not None:
            self.lock.seek(0)
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
            self.lock.close()
            self.lock = None

    def run_once(self):
        if self.thread is not None and self.thread.is_alive():
            raise RuntimeError('This scanner is already running.')
        self.acquire()
        try:
            with self.app.app_context():
                return scan_once()
        finally:
            self.release()

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            raise RuntimeError('This scanner is already running.')
        self.acquire()
        self.stop_event.clear()
        self.thread = Thread(target=self._run, name='overtime-scanner', daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                with self.app.app_context():
                    result = scan_once()
                    self.app.logger.info('Overtime scan marked=%s skipped=%s', result['marked'], result['skipped'])
            except Exception as error:
                self.app.logger.error('Overtime scan failed (%s)', type(error).__name__)
            self.stop_event.wait(self.app.config['OVERTIME_SCAN_SECONDS'])

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                # Keep ownership until the in-flight scan finishes or process exits.
                return
        self.release()
