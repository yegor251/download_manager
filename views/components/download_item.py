from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PyQt6.QtCore import Qt

class DownloadItem(QWidget):
    def __init__(self, url, manager, parent=None):
        super().__init__(parent)
        self.url = url
        self.manager = manager
        self.main_layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        self.url_label = QLabel(url)
        self.url_label.setWordWrap(True)

        self.control_layout = QHBoxLayout()
        self.pause_button = QPushButton("Пауза")
        self.pause_button.setFixedWidth(80)
        self.pause_button.clicked.connect(self.toggle_pause)

        self.retry_button = QPushButton("Возобновить")
        self.retry_button.setFixedWidth(100)
        self.retry_button.clicked.connect(self.retry_download)
        self.retry_button.setVisible(False)

        self.control_layout.addWidget(self.pause_button)
        self.control_layout.addWidget(self.retry_button)

        top_layout.addWidget(self.url_label, stretch=1)
        top_layout.addLayout(self.control_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("В очереди")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.main_layout.addLayout(top_layout)
        self.main_layout.addWidget(self.progress_bar)
        self.main_layout.addWidget(self.status_label)

        self.setLayout(self.main_layout)

    def toggle_pause(self):
        if self.manager.is_task_paused(self.url):
            self.manager.resume_task(self.url)
            self.pause_button.setText("Пауза")
        else:
            self.manager.pause_task(self.url)
            self.pause_button.setText("Продолжить")

    def retry_download(self):
        if self.manager.retry_download(self.url):
            self.retry_button.setVisible(False)
            self.pause_button.setVisible(True)
            self.pause_button.setEnabled(True)
            self.status_label.setText("Повторная попытка...")
