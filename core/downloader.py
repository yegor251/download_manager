import socket
import ssl
import os
from urllib.parse import urlparse
import certifi
import time
from .models import DownloadState

class Downloader:
    @staticmethod
    def download_file(url, save_path=None, progress_callback=None, max_redirects=5, pause_event=None, resume=False):
        redirect_count = 0
        while redirect_count < max_redirects:
            try:
                parsed_url = urlparse(url)
                host = parsed_url.hostname
                path = parsed_url.path if parsed_url.path else "/"
                port = parsed_url.port if parsed_url.port else (443 if parsed_url.scheme == "https" else 80)

                # Проверяем размер уже скачанного файла для докачки
                file_size = 0
                temp_path = save_path + '.part' if save_path else None
                if resume and temp_path and os.path.exists(temp_path):
                    file_size = os.path.getsize(temp_path)
                elif resume and save_path and os.path.exists(save_path):
                    file_size = os.path.getsize(save_path)

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10.0)

                if parsed_url.scheme == "https":
                    context = ssl.create_default_context(cafile=certifi.where())
                    sock = context.wrap_socket(sock, server_hostname=host)

                sock.connect((host, port))

                # Добавляем Range заголовок для докачки
                range_header = f"Range: bytes={file_size}-\r\n" if file_size > 0 else ""
                request = (f"GET {path} HTTP/1.1\r\n"
                           f"Host: {host}\r\n"
                           f"Connection: close\r\n"
                           f"{range_header}"
                           f"\r\n")
                sock.send(request.encode())

                response = b""
                while b"\r\n\r\n" not in response:
                    try:
                        data = sock.recv(4096)
                        if not data:
                            return DownloadState.FAILED, "Сервер закрыл соединение"
                        response += data
                    except socket.timeout:
                        return DownloadState.FAILED, "Timeout при получении заголовков"

                headers, _, body = response.partition(b"\r\n\r\n")
                status_line = headers.decode().split("\r\n")[0]
                status_code = int(status_line.split()[1])

                # Обработка редиректа
                if status_code in (301, 302, 303, 307, 308):
                    location = None
                    for line in headers.decode().split("\r\n"):
                        if line.lower().startswith("location:"):
                            location = line.split(":", 1)[1].strip()
                            break

                    if not location:
                        return DownloadState.FAILED, "Не найдено местоположение для редиректа"

                    url = location if location.startswith(('http://', 'https://')) else \
                        f"{parsed_url.scheme}://{parsed_url.netloc}{location}"
                    redirect_count += 1
                    sock.close()
                    continue

                # Проверяем поддержку докачки
                if file_size > 0 and status_code != 206:
                    return DownloadState.FAILED, "Сервер не поддерживает докачку"

                if status_code not in (200, 206):
                    return DownloadState.FAILED, f"Ошибка сервера: {status_line}"

                content_length = None
                for line in headers.decode().split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":")[1].strip())+file_size
                        break
                    elif line.lower().startswith("content-range:"):
                        content_length = int(line.split("/")[1].strip())+file_size

                if save_path is None:
                    save_path = os.path.basename(path) or "downloaded_file"

                # Используем временный файл для докачки
                temp_path = save_path + '.part'
                mode = "ab" if file_size > 0 else "wb"
                total_received = file_size

                try:
                    with open(temp_path, mode) as file:

                        if body:
                            file.write(body)
                            total_received += len(body)
                            if progress_callback:
                                progress_callback(total_received, content_length)

                        while True:
                            if pause_event and pause_event.is_set():
                                while pause_event.is_set():
                                    if not pause_event:
                                        sock.close()
                                        return DownloadState.PAUSED, "Загрузка приостановлена"
                                    time.sleep(0.1)

                            try:
                                data = sock.recv(4096)
                                if not data:
                                    # Проверяем, скачан ли весь файл
                                    if content_length and total_received >= content_length:
                                        # Переименовываем временный файл в конечный
                                        if os.path.exists(save_path):
                                            os.remove(save_path)
                                        os.rename(temp_path, save_path)
                                        return DownloadState.COMPLETED, "Файл успешно скачан"
                                    return DownloadState.FAILED, "Сервер закрыл соединение досрочно"

                                file.write(data)
                                total_received += len(data)

                                if progress_callback and content_length:
                                    progress_callback(total_received, content_length)

                                # Проверяем завершение загрузки
                                if content_length and total_received >= content_length:
                                    # Переименовываем временный файл в конечный
                                    if os.path.exists(save_path):
                                        os.remove(save_path)
                                    os.rename(temp_path, save_path)
                                    return DownloadState.COMPLETED, "Файл успешно скачан"

                            except socket.timeout:
                                if content_length and total_received >= content_length:
                                    if os.path.exists(save_path):
                                        os.remove(save_path)
                                    os.rename(temp_path, save_path)
                                    return DownloadState.COMPLETED, "Файл успешно скачан"
                                return DownloadState.FAILED, "Timeout при получении данных"

                except IOError as e:
                    return DownloadState.FAILED, f"Ошибка записи файла: {str(e)}"
                finally:
                    if 'sock' in locals():
                        sock.close()

            except socket.error as e:
                return DownloadState.FAILED, f"Ошибка соединения: {str(e)}"
            except Exception as e:
                return DownloadState.FAILED, f"Неизвестная ошибка: {str(e)}"

        return DownloadState.FAILED, f"Превышено максимальное количество редиректов ({max_redirects})"