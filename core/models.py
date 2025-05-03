from enum import Enum, auto

class DownloadState(Enum):
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()

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