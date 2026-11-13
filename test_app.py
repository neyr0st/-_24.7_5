"""Тесты веб-слоя: поднимается настоящий сервер на свободном порту (только stdlib)."""
import http.cookiejar, io, json, os, tempfile, threading, urllib.error, urllib.parse, urllib.request, zipfile
os.environ["QR_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
import app

srv = app.make_server(port=0)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % PORT


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect)

    def req(self, path, data=None, js=None):
        if js is not None:
            data, h = json.dumps(js).encode(), {"Content-Type": "application/json"}
        else:
            h = {"Content-Type": "application/x-www-form-urlencoded"}
            data = urllib.parse.urlencode(data).encode() if data is not None else None
        try:
            r = self.op.open(urllib.request.Request(BASE + path, data=data, headers=h))
        except urllib.error.HTTPError as e:
            r = e
        return r.status if hasattr(r, "status") else r.code, r.read(), dict(r.headers)

    def j(self, path, js):
        s, b, _ = self.req(path, js=js)
        return s, json.loads(b)


def check(cond, msg):
    assert cond, msg
    print("ok", msg)


c = Client()
s, j = c.j("/api/preview", {"kind": "text", "text": ""})
check(s == 400 and "Введите текст" in j["error"], "пустой текст -> ошибка")
s, j = c.j("/api/preview", {"kind": "text", "text": "x" * 2001})
check(s == 400 and "2000" in j["error"], ">2000 -> лимит")
s, j = c.j("/api/preview", {"kind": "text", "text": "x" * 2000, "ec": "L"})
check(j["ok"] and j["image"].startswith("data:image/png;base64,"), "2000 символов генерируется")
check(c.req("/download?fmt=svg", js={"text": "a"})[0] == 401, "SVG без входа закрыт")
check(c.req("/download?fmt=png", js={"text": "a", "size": 200})[1][:4] == b"\x89PNG", "PNG скачивается")
check(c.req("/history")[0] == 303, "история требует входа")
check("Введите текст" in c.req("/")[1].decode(), "главная страница открывается")

check(c.req("/register", {"email": "a@b.ru", "password": "secret1"})[0] == 303, "регистрация")
c.req("/logout")
c2 = Client()
check("email занят" in c2.req("/register", {"email": "a@b.ru", "password": "secret1"})[1].decode(), "повторный email")
check("Неверный" in c2.req("/login", {"email": "a@b.ru", "password": "bad"})[1].decode(), "неверный пароль")
check(c2.req("/history")[0] == 303, "после неверного пароля истории нет")
check(c2.req("/login", {"email": "a@b.ru", "password": "secret1"})[0] == 303, "вход")
c = c2

check("Нет сохранённых кодов" in c.req("/history")[1].decode(), "пустая история")
check(b"<svg" in c.req("/download?fmt=svg", js={"text": "a"})[1], "SVG после входа")
for i in range(55):
    c.j("/api/generate", {"kind": "text", "text": "code %d" % i})
html = c.req("/history")[1].decode()
check(html.count("/delete") == 50 and "code 54" in html and ">code 4<" not in html, "ровно 50 последних")
check(c.req("/history/55/file.png")[1][:4] == b"\x89PNG", "повторное открытие")
c.req("/history/55/delete", {})
check("code 54" not in c.req("/history")[1].decode(), "удаление записи")
check(c.req("/history.csv")[1].decode("utf-8-sig").splitlines()[0] == "дата;текст;размер;формат", "CSV истории")

check(c.j("/api/templates", {"name": "афиша", "settings": {"fg": "#112233", "bg": "#ffffff", "size": 1000}})[1]["ok"], "шаблон сохранён")
check(json.loads(c.req("/api/templates")[1])["templates"][0]["settings"]["size"] == 1000, "шаблон в списке")

s, b, h = c.req("/batch", js={"csv": "text,name\nhttp://a.ru,A\n,B\n\nhttp://b.ru,C\n", "size": 200})
check(len(zipfile.ZipFile(io.BytesIO(b)).namelist()) == 2 and h["X-Skipped"] == "1", "CSV: пустая строка пропущена")
rows = "text\n" + "\n".join("http://x.ru/%d" % i for i in range(100))
check(len(zipfile.ZipFile(io.BytesIO(c.req("/batch", js={"csv": rows, "size": 200})[1])).namelist()) == 100, "CSV: 100 строк -> 100 PNG")
check("text" in c.j("/batch", {"csv": "url\nx\n"})[1]["error"], "CSV без колонки text")
check("500" in c.j("/batch", {"csv": "text\n" + "a\n" * 501})[1]["error"], "CSV >500 строк")

# логотип через веб-API (регресс: раньше PNG декодировался дважды и падал)
import base64, struct, zlib
def _ch(tp, d): return struct.pack(">I", len(d)) + tp + d + struct.pack(">I", zlib.crc32(tp + d) & 0xFFFFFFFF)
_raw = b"".join(b"\x00" + bytes([51, 102, 204, 255]) * 512 for _ in range(512))
ICON = b"\x89PNG\r\n\x1a\n" + _ch(b"IHDR", struct.pack(">IIBBBBB", 512, 512, 8, 6, 0, 0, 0)) + _ch(b"IDAT", zlib.compress(_raw)) + _ch(b"IEND", b"")
logo = "data:image/png;base64," + base64.b64encode(ICON).decode()
s, j = c.j("/api/preview", {"kind": "text", "text": "https://example.com", "size": 500, "logo": logo})
check(s == 200 and j["ok"], "иконка PNG 512x512 принимается через веб")
s, b, _ = c.req("/download?fmt=png", js={"text": "https://example.com", "size": 500, "logo": logo})
check(s == 200 and b[:4] == b"\x89PNG", "PNG со вложенным логотипом скачивается")
s, j = c.j("/api/preview", {"kind": "text", "text": "x", "logo": "data:image/png;base64," + base64.b64encode(b"\xff\xd8\xff\xe0abcdefgh").decode()})
check(s == 400 and "JPEG" in j["error"], "JPEG вместо PNG -> понятная ошибка")
srv.shutdown()
print("ALL OK")
