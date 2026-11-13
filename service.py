"""Бизнес-логика: валидация, сборка payload (текст / Wi-Fi / контакт), генерация."""
import re
from functools import lru_cache
from qrcore import encode, DataTooLong, LEVELS
from render import render_png, render_svg
from pngtools import decode_png

SIZES = (200, 500, 1000)
MAX_TEXT = 2000
MAX_CAPTION = 60
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _wifi_esc(s):
    return re.sub(r'([\\;,:"])', r"\\\1", s)


def build_payload(f):
    """f — dict-подобный объект. Возвращает (payload, label)."""
    kind = f.get("kind", "text")
    if kind == "wifi":
        ssid = (f.get("ssid") or "").strip()
        if not ssid:
            raise ValueError("Введите SSID")
        pw, enc = f.get("password") or "", f.get("enc", "WPA")
        if enc not in ("WPA", "WEP", "nopass") or not pw:
            enc = "nopass" if not pw else enc if enc in ("WPA", "WEP") else "WPA"
        p = f"WIFI:T:{enc};S:{_wifi_esc(ssid)};" + (f"P:{_wifi_esc(pw)};" if enc != "nopass" else "") + ";"
        return p, f"Wi-Fi: {ssid}"
    if kind == "contact":
        name, phone, mail = (f.get("c_name") or "").strip(), (f.get("c_phone") or "").strip(), (f.get("c_email") or "").strip()
        if not (name or phone or mail):
            raise ValueError("Заполните хотя бы одно поле контакта")
        lines = ["BEGIN:VCARD", "VERSION:3.0"]
        if name:
            lines += [f"N:;{name};;;", f"FN:{name}"]
        if phone:
            lines.append(f"TEL:{phone}")
        if mail:
            lines.append(f"EMAIL:{mail}")
        lines.append("END:VCARD")
        return "\n".join(lines), "Контакт: " + (name or phone or mail)
    text = f.get("text") or ""
    if not text.strip():
        raise ValueError("Введите текст")
    if len(text) > MAX_TEXT:
        raise ValueError(f"Слишком длинный текст: максимум {MAX_TEXT} символов (введено {len(text)})")
    return text, text


def parse_settings(f):
    ec = (f.get("ec") or "M").upper()
    if ec not in LEVELS:
        raise ValueError("Уровень коррекции: L, M, Q или H")
    mask = f.get("mask", "auto")
    if mask in (None, "", "auto"):
        mask = "auto"
    elif str(mask) not in list("01234567"):
        raise ValueError("Маска: 0–7 или auto")
    else:
        mask = int(mask)
    try:
        size = int(f.get("size", 500))
    except (TypeError, ValueError):
        size = 500
    if size not in SIZES:
        size = 500
    fg, bg = f.get("fg") or "#000000", f.get("bg") or "#ffffff"
    if not (_HEX.match(fg) and _HEX.match(bg)):
        raise ValueError("Цвет задаётся в формате #rrggbb")
    if fg.lower() == bg.lower():
        raise ValueError("QR-код будет нечитаем: цвета модулей и фона совпадают")
    caption = (f.get("caption") or "").strip()
    if len(caption) > MAX_CAPTION:
        raise ValueError(f"Подпись не длиннее {MAX_CAPTION} символов")
    frame = str(f.get("frame", "")).lower() in ("1", "true", "on", "yes")
    fmt = f.get("fmt", "png")
    return {"ec": ec, "mask": mask, "size": size, "fg": fg, "bg": bg,
            "caption": caption, "frame": frame, "fmt": fmt if fmt in ("png", "svg") else "png"}


@lru_cache(maxsize=4)
def _decode_cached(data):  # логотип не декодируется заново при каждом предпросмотре
    return decode_png(data)


def load_logo(data):
    """data — байты PNG или None. Возвращает (w, h, rows) или None."""
    return _decode_cached(bytes(data)) if data else None


def render(payload, s, logo=None, fmt="png"):
    """Возвращает (bytes, mimetype)."""
    ec = "H" if logo is not None else s["ec"]  # логотип закрывает модули — нужен максимум коррекции
    try:
        matrix, _ = encode(payload, ec, s["mask"])
    except DataTooLong:
        hint = "" if ec == "L" else " — выберите уровень L"
        raise ValueError("Текст слишком длинный для QR-кода (лимит ёмкости; кириллица занимает 2 байта на символ)" + hint)
    if fmt == "svg":
        return render_svg(matrix, s["size"], s["fg"], s["bg"]).encode(), "image/svg+xml"
    return render_png(matrix, s["size"], s["fg"], s["bg"], logo, s["caption"], s["frame"]), "image/png"


def make_qr(form, logo_bytes=None, fmt="png"):
    payload, label = build_payload(form)
    s = parse_settings(form)
    data, mime = render(payload, s, load_logo(logo_bytes), fmt)
    return data, mime, payload, label, s
