from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QLineEdit, QPushButton,
    QFileDialog, QProgressBar, QLabel, QScrollArea, QMessageBox,
    QHBoxLayout
)
from PyQt6.QtCore import Qt
import os
from core.manager import DownloadManager


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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Менеджер закачки файлов")
        self.setGeometry(100, 100, 800, 600)

        # Основные элементы
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Введите URL файла")

        self.save_path_button = QPushButton("Выбрать путь сохранения")
        self.save_path_label = QLabel("Путь не выбран")
        self.download_button = QPushButton("Добавить загрузку")

        # Область отображения загрузок
        self.scroll_area = QScrollArea()
        self.downloads_container = QWidget()
        self.downloads_layout = QVBoxLayout()
        self.downloads_container.setLayout(self.downloads_layout)
        self.scroll_area.setWidget(self.downloads_container)
        self.scroll_area.setWidgetResizable(True)

        # Основной layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.url_input)
        main_layout.addWidget(self.save_path_button)
        main_layout.addWidget(self.save_path_label)
        main_layout.addWidget(self.download_button)
        main_layout.addWidget(self.scroll_area)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Менеджер загрузок
        self.download_manager = DownloadManager()
        self.download_manager.task_progress.connect(self.update_progress)
        self.download_manager.task_completed.connect(self.update_status)
        self.download_manager.task_paused.connect(self.update_pause_status)

        # Хранилище элементов загрузок
        self.download_items = {}
        self.save_path = None

        # Подключение сигналов
        self.save_path_button.clicked.connect(self.choose_save_path)
        self.download_button.clicked.connect(self.start_download)

    def choose_save_path(self):
        # Диалог выбора файла с возможностью ввода имени
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Выберите файл для сохранения",
            "",
            "Все файлы (*)"
        )

        if save_path:
            try:
                dir_path = os.path.dirname(save_path)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)

                test_file = save_path + '.test'
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)

                self.save_path = save_path
                self.save_path_label.setText(save_path)
                self.save_path_label.setToolTip(save_path)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    f"Невозможно сохранить файл по указанному пути:\n{str(e)}"
                )
                self.save_path = None
                self.save_path_label.setText("Путь не выбран (ошибка)")

    def start_download(self):
        url = self.url_input.text().strip()
        if not url.startswith(('http://', 'https://')):
            QMessageBox.warning(self, "Ошибка", "URL должен начинаться с http:// или https://")
            return

        if not self.save_path:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите путь сохранения")
            return

        # Если в save_path указана папка (без имени файла), используем имя из URL
        if os.path.isdir(self.save_path):
            filename = url.split('/')[-1] or "downloaded_file"
            save_path = os.path.join(self.save_path, filename)
        else:
            save_path = self.save_path

        # Создаем элемент для отображения загрузки
        item = DownloadItem(url, self.download_manager)  # Передаем менеджер в конструктор
        self.download_items[url] = item
        self.downloads_layout.addWidget(item)

        # Добавляем задачу в менеджер
        if not self.download_manager.add_task(url, save_path):
            item.status_label.setText("В очереди (ожидание свободного слота)")

    def update_progress(self, url, progress):
        if url in self.download_items:
            item = self.download_items[url]
            item.progress_bar.setValue(progress)
            item.status_label.setText(f"Загружается... {progress}%")

    def update_status(self, url, success, message):
        if url in self.download_items:
            item = self.download_items[url]
            if success:
                item.status_label.setText("Завершено успешно")
                item.progress_bar.setValue(100)
                item.pause_button.setVisible(False)
                item.retry_button.setVisible(False)
            else:
                item.status_label.setText(f"Ошибка: {message}")
                item.pause_button.setVisible(False)
                item.retry_button.setVisible(True)
                item.retry_button.setEnabled(True)

    def update_pause_status(self, url, is_paused):
        if url in self.download_items:
            item = self.download_items[url]
            if is_paused:
                item.status_label.setText("На паузе")
                item.pause_button.setText("Продолжить")
            else:
                item.status_label.setText("Загружается...")
                item.pause_button.setText("Пауза")