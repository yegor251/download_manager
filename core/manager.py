from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex
from core.downloader import Downloader, DownloadState
import time
import os


class DownloadWorker(QObject):
    progress_updated = pyqtSignal(str, int)
    task_finished = pyqtSignal(str, bool, str)
    task_paused = pyqtSignal(str, bool)
    task_failed = pyqtSignal(str, str)

    def __init__(self, url, save_path):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self._is_running = True
        self._is_paused = False
        self.pause_event = None
        self.mutex = QMutex()
        self.attempts = 0
        self.max_attempts = 3

    def run(self):
        def progress_callback(received, total):
            if total and self._is_running:
                progress = int((received / total) * 100)
                self.progress_updated.emit(self.url, progress)

        try:
            self.pause_event = PauseEvent()
            temp_path = self.save_path + '.part'
            resume = os.path.exists(temp_path) or (os.path.exists(self.save_path) and not os.path.exists(temp_path))

            if os.path.exists(self.save_path) and not os.path.exists(temp_path):
                self.task_finished.emit(self.url, True, "Файл уже загружен")
                return

            while self.attempts < self.max_attempts and self._is_running:
                state, message = Downloader.download_file(
                    self.url,
                    self.save_path,
                    progress_callback,
                    pause_event=self.pause_event,
                    resume=resume
                )

                if state == DownloadState.COMPLETED:
                    self.task_finished.emit(self.url, True, message)
                    return
                elif state == DownloadState.PAUSED:
                    self.task_paused.emit(self.url, True)
                    return
                elif "не поддерживает докачку" in message:
                    break

                self.attempts += 1
                if self.attempts < self.max_attempts:
                    time.sleep(2)

            if self._is_running:
                self.task_failed.emit(self.url, message)

        except Exception as e:
            if self._is_running:
                self.task_failed.emit(self.url, str(e))
        finally:
            self.pause_event = None

    def stop(self):
        self._is_running = False
        if self.pause_event:
            self.pause_event.cancel()

    def pause(self):
        self.mutex.lock()
        try:
            if not self._is_paused and self.pause_event:
                self.pause_event.set()
                self._is_paused = True
                self.task_paused.emit(self.url, True)
        finally:
            self.mutex.unlock()

    def resume(self):
        self.mutex.lock()
        try:
            if self._is_paused and self.pause_event:
                self.pause_event.clear()
                self._is_paused = False
                self.task_paused.emit(self.url, False)
        finally:
            self.mutex.unlock()

    def is_paused(self):
        self.mutex.lock()
        try:
            return self._is_paused
        finally:
            self.mutex.unlock()

class PauseEvent:
    def __init__(self):
        self._is_set = False
        self._is_cancelled = False

    def set(self):
        self._is_set = True

    def clear(self):
        self._is_set = False

    def is_set(self):
        return self._is_set and not self._is_cancelled

    def cancel(self):
        self._is_cancelled = True

class DownloadManager(QObject):
    task_progress = pyqtSignal(str, int)
    task_completed = pyqtSignal(str, bool, str)
    task_paused = pyqtSignal(str, bool)
    task_failed = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.active_workers = {}
        self.failed_downloads = {}  # Для хранения неудачных загрузок
        self.max_parallel = 3

    def add_task(self, url, save_path, resume=False):
        if url in self.active_workers:
            return False

        if len(self.active_workers) >= self.max_parallel:
            return False

        thread = QThread()
        worker = DownloadWorker(url, save_path)
        worker.moveToThread(thread)

        worker.progress_updated.connect(self._handle_progress)
        worker.task_finished.connect(self._handle_finished)
        worker.task_failed.connect(self._handle_failed)
        worker.task_paused.connect(self._handle_paused)
        thread.started.connect(worker.run)

        worker.task_finished.connect(lambda: thread.quit())
        worker.task_failed.connect(lambda: thread.quit())
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self.active_workers[url] = {
            'thread': thread,
            'worker': worker
        }

        thread.start()
        return True

    def _handle_failed(self, url, message):
        if url in self.active_workers:
            worker_data = self.active_workers[url]
            save_path = worker_data['worker'].save_path
            self.failed_downloads[url] = {
                'save_path': save_path,
                'error': message
            }
            worker_data['worker'].stop()
            del self.active_workers[url]
        self.task_completed.emit(url, False, message)

    def retry_download(self, url):
        if url in self.failed_downloads:
            save_path = self.failed_downloads[url]['save_path']
            return self.add_task(url, save_path, resume=True)
        return False

    def _handle_progress(self, url, progress):
        self.task_progress.emit(url, progress)

    def _handle_finished(self, url, success, message):
        if url in self.active_workers:
            worker_data = self.active_workers[url]
            worker_data['worker'].stop()
            del self.active_workers[url]
        self.task_completed.emit(url, success, message)

    def _handle_paused(self, url, is_paused):
        self.task_paused.emit(url, is_paused)

    def pause_task(self, url):
        if url in self.active_workers:
            self.active_workers[url]['worker'].pause()
            return True
        return False

    def resume_task(self, url):
        if url in self.active_workers:
            self.active_workers[url]['worker'].resume()
            return True
        return False

    def is_task_paused(self, url):
        if url in self.active_workers:
            return self.active_workers[url]['worker'].is_paused()
        return False

    def __del__(self):
        for worker_data in self.active_workers.values():
            worker_data['worker'].stop()
            worker_data['thread'].quit()
            worker_data['thread'].wait()