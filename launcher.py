"""Запуск для обычного пользователя: поднимает сервис и открывает браузер."""
import sys
import threading
import webbrowser

import app


def main():
    srv = None
    for port in range(8000, 8020):  # если порт занят — пробуем следующий
        try:
            srv = app.make_server(port=port)
            break
        except OSError:
            continue
    if srv is None:
        print("Не удалось занять ни один порт 8000–8019. Закройте другие программы и повторите.")
        input("Нажмите Enter для выхода")
        return 1
    url = "http://127.0.0.1:%d" % srv.server_address[1]
    print("QR-генератор запущен:", url)
    print("Не закрывайте это окно, пока работаете. Чтобы выйти — закройте окно или нажмите Ctrl+C.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
