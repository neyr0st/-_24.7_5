"""Веб-сервис на чистой стандартной библиотеке (http.server + sqlite3).
Запуск:  python app.py   ->  http://127.0.0.1:8000"""
import base64, csv, hashlib, hmac, io, json, os, re, secrets, sqlite3, sys, zipfile
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pages
from service import make_qr, build_payload, parse_settings, render, MAX_TEXT

# в собранном .exe данные (база, ключ) хранятся рядом с exe, а не во временной папке
BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
HISTORY_LIMIT, BATCH_LIMIT, MAX_BODY = 50, 500, 8 * 1024 * 1024


def db_path():
    return os.environ.get("QR_DB", os.path.join(BASE, "qr.db"))


def secret_key():
    p = os.path.join(BASE, ".secret")
    if not os.path.exists(p):
        with open(p, "wb") as f:
            f.write(secrets.token_bytes(32))
    with open(p, "rb") as f:
        return f.read()


KEY = secret_key()


def init_db():
    c = sqlite3.connect(db_path())
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL,
        payload TEXT NOT NULL, label TEXT NOT NULL, settings TEXT NOT NULL, size INTEGER, fmt TEXT);
    CREATE TABLE IF NOT EXISTS templates(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL,
        settings TEXT NOT NULL, UNIQUE(user_id, name));""")
    c.commit()
    c.close()


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()


def check_pw(pw, stored):
    salt = stored.split("$")[0]
    return hmac.compare_digest(hash_pw(pw, salt), stored)


def sign(data):
    b = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return b + "." + hmac.new(KEY, b.encode(), "sha256").hexdigest()


def unsign(tok):
    try:
        b, sig = tok.rsplit(".", 1)
        if hmac.compare_digest(hmac.new(KEY, b.encode(), "sha256").hexdigest(), sig):
            return json.loads(base64.urlsafe_b64decode(b))
    except Exception:
        pass
    return None


class Err(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.msg, self.code = msg, code


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "QRGen"

    def log_message(self, *a):
        pass

    # ----- инфраструктура -----
    def session(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return (unsign(c["s"].value) if "s" in c else None) or {}

    def send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def redirect(self, to, cookie=None):
        h = {"Location": to}
        if cookie is not None:
            h["Set-Cookie"] = cookie
        self.send(303, b"", headers=h)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise Err("Слишком большой запрос (максимум 8 МБ)", 413)
        return self.rfile.read(n)

    def jbody(self):
        try:
            j = json.loads(self.body() or b"{}")
            return j if isinstance(j, dict) else {}
        except ValueError:
            raise Err("Некорректный запрос")

    def require_login(self):
        uid = self.session().get("uid")
        if not uid:
            raise Err("Войдите в аккаунт", 401)
        return uid

    def logo(self, j):
        v = j.get("logo") or ""
        if not v:
            return None
        try:
            raw = base64.b64decode(v.split(",", 1)[-1])
        except Exception:
            raise Err("Не удалось прочитать логотип")
        if len(raw) > 2 * 1024 * 1024:
            raise Err("Логотип больше 2 МБ")
        return raw  # декодирует make_qr (с кэшем); здесь только проверка размера

    def dispatch(self, method):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        try:
            self.route(method, path, q)
        except Err as e:
            if path.startswith(("/api", "/download", "/batch")):
                self.json({"ok": False, "error": e.msg}, e.code)
            elif e.code == 401:
                self.redirect("/login")
            else:
                self.send(e.code, pages.layout("<div class='card'>%s</div>" % pages.E(e.msg), self.session().get("email")))
        except ValueError as e:
            self.json({"ok": False, "error": str(e)}, 400)

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    # ----- маршруты -----
    def route(self, m, path, q):
        s = self.session()
        user, uid = s.get("email"), s.get("uid")
        db = sqlite3.connect(db_path())
        db.row_factory = sqlite3.Row
        try:
            self._route(m, path, q, db, user, uid)
        finally:
            db.close()

    def _route(self, m, path, q, db, user, uid):
        if m == "GET" and path == "/":
            return self.send(200, pages.layout(pages.index_page(user, MAX_TEXT), user))
        if path in ("/login", "/register"):
            mode = path[1:]
            if m == "GET":
                return self.send(200, pages.layout(pages.auth_page(mode), user))
            f = {k: v[0] for k, v in parse_qs(self.body().decode("utf-8", "replace")).items()}
            email, pw = f.get("email", "").strip().lower(), f.get("password", "")
            err = None
            if mode == "register":
                if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                    err = "Неверный email"
                elif len(pw) < 6:
                    err = "Пароль — минимум 6 символов"
                else:
                    try:
                        cur = db.execute("INSERT INTO users(email,pw) VALUES(?,?)", (email, hash_pw(pw)))
                        db.commit()
                        return self.login_ok(cur.lastrowid, email)
                    except sqlite3.IntegrityError:
                        err = "email занят"
            else:
                r = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                if r and check_pw(pw, r["pw"]):
                    return self.login_ok(r["id"], email)
                err = "Неверный email или пароль"
            return self.send(200, pages.layout(pages.auth_page(mode, err), user))
        if m == "GET" and path == "/logout":
            return self.redirect("/", "s=; Path=/; Max-Age=0")

        if m == "POST" and path in ("/api/preview", "/api/generate"):
            j = self.jbody()
            data, _, payload, label, st = make_qr(j, self.logo(j), "png")
            rec = None
            if path.endswith("generate") and uid:
                cur = db.execute(
                    "INSERT INTO history(user_id,created_at,payload,label,settings,size,fmt) VALUES(?,?,?,?,?,?,?)",
                    (uid, datetime.now().isoformat(timespec="seconds"), payload, label,
                     json.dumps({k: st[k] for k in ("ec", "mask", "fg", "bg", "caption", "frame", "size")}), st["size"], st["fmt"]))
                db.commit()
                rec = cur.lastrowid
            return self.json({"ok": True, "label": label, "size": st["size"], "fmt": st["fmt"], "id": rec,
                              "image": "data:image/png;base64," + base64.b64encode(data).decode()})
        if m == "POST" and path == "/download":
            fmt = (q.get("fmt") or ["png"])[0]
            if fmt not in ("png", "svg"):
                raise Err("Формат: png или svg")
            if fmt == "svg" and not uid:
                raise Err("SVG доступен только зарегистрированным организаторам", 401)
            j = self.jbody()
            data, mime, *_ = make_qr(j, self.logo(j), fmt)
            return self.send(200, data, mime, {"Content-Disposition": "attachment; filename=qr." + fmt})
        if m == "POST" and path == "/batch":
            return self.batch(self.jbody())

        if path.startswith("/history") or path == "/api/templates":
            if not uid:
                raise Err("Войдите в аккаунт", 401)
            return self.account_routes(m, path, q, db, user, uid)
        raise Err("Страница не найдена", 404)

    def login_ok(self, uid, email):
        c = "s=%s; Path=/; HttpOnly; SameSite=Lax" % sign({"uid": uid, "email": email})
        self.redirect("/", c)

    def batch(self, j):
        text = j.get("csv") or ""
        if text.startswith("\ufeff"):
            text = text[1:]
        if not text.strip():
            raise Err("Загрузите CSV-файл")
        delim = ";" if text[:2048].count(";") > text[:2048].count(",") else ","
        rd = csv.DictReader(io.StringIO(text), delimiter=delim)
        if not rd.fieldnames or "text" not in [h.strip() for h in rd.fieldnames]:
            raise Err("Ожидается CSV с заголовком-колонкой «text» (по одной ссылке/тексту в строке)")
        rd.fieldnames = [h.strip() for h in rd.fieldnames]
        rows = list(rd)
        if len(rows) > BATCH_LIMIT:
            raise Err("Слишком большой файл: максимум %d строк (в файле %d)" % (BATCH_LIMIT, len(rows)))
        st = parse_settings(j)
        buf, n, skipped = io.BytesIO(), 0, 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for r in rows:
                try:
                    payload, _ = build_payload({"kind": "text", "text": r.get("text") or ""})
                    png, _ = render(payload, st, None, "png")
                except ValueError:
                    skipped += 1
                    continue
                n += 1
                z.writestr("qr_%03d.png" % n, png)
        if n == 0:
            raise Err("В файле нет непустых строк в колонке text")
        self.send(200, buf.getvalue(), "application/zip",
                  {"Content-Disposition": "attachment; filename=qr_codes.zip", "X-Generated": str(n),
                   "X-Skipped": str(skipped), "Access-Control-Expose-Headers": "X-Generated, X-Skipped"})

    def account_routes(self, m, path, q, db, user, uid):
        if m == "GET" and path == "/history":
            rows = db.execute("SELECT * FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, HISTORY_LIMIT)).fetchall()
            return self.send(200, pages.layout(pages.history_page(rows), user))
        if m == "GET" and path == "/history.csv":
            rows = db.execute("SELECT * FROM history WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
            out = io.StringIO()
            w = csv.writer(out, delimiter=";")  # «;» + BOM: корректно открывается в Excel (рус. локаль)
            w.writerow(["дата", "текст", "размер", "формат"])
            for r in rows:
                w.writerow([r["created_at"], r["label"], r["size"], r["fmt"]])
            return self.send(200, "\ufeff" + out.getvalue(), "text/csv; charset=utf-8",
                             {"Content-Disposition": "attachment; filename=history.csv"})
        mt = re.match(r"^/history/(\d+)(?:/(delete)|/file\.(png|svg))?$", path)
        if mt:
            hid = int(mt.group(1))
            row = db.execute("SELECT * FROM history WHERE id=? AND user_id=?", (hid, uid)).fetchone()
            if not row:
                raise Err("Запись не найдена", 404)
            if m == "POST" and mt.group(2):
                db.execute("DELETE FROM history WHERE id=?", (hid,))
                db.commit()
                return self.redirect("/history")
            if m == "GET" and mt.group(3):
                st = {**parse_settings({}), **json.loads(row["settings"])}
                data, mime = render(row["payload"], st, None, mt.group(3))
                h = {"Content-Disposition": "attachment; filename=qr_%d.%s" % (hid, mt.group(3))} if q.get("dl") else {}
                return self.send(200, data, mime, h)
            if m == "GET":
                return self.send(200, pages.layout(pages.item_page(row), user))
        if path == "/api/templates":
            if m == "GET":
                rows = db.execute("SELECT name,settings FROM templates WHERE user_id=? ORDER BY name", (uid,)).fetchall()
                return self.json({"ok": True, "templates": [{"name": r["name"], "settings": json.loads(r["settings"])} for r in rows]})
            j = self.jbody()
            name = (j.get("name") or "").strip()
            if not name or len(name) > 40:
                raise Err("Введите имя шаблона (до 40 символов)")
            st = parse_settings(j.get("settings") or {})
            db.execute("INSERT INTO templates(user_id,name,settings) VALUES(?,?,?) "
                       "ON CONFLICT(user_id,name) DO UPDATE SET settings=excluded.settings",
                       (uid, name, json.dumps({k: st[k] for k in ("fg", "bg", "size", "fmt", "ec", "mask")})))
            db.commit()
            return self.json({"ok": True})
        raise Err("Страница не найдена", 404)


def make_server(host="127.0.0.1", port=8000):
    init_db()
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = make_server(port=port)
    print("Сервис запущен: http://127.0.0.1:%d  (Ctrl+C — остановить)" % port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено")
