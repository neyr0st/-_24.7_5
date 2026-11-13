"""Тесты ядра без внешних пакетов. Если установлен opencv-python — дополнительно
проверяется сканирование (необязательно, в сервис не входит)."""
import struct, time, zlib
from qrcore import encode, rs_remainder, DataTooLong
from pngtools import decode_png, encode_png
from render import render_png, BORDER
from service import make_qr

try:
    import cv2, numpy as np
except ImportError:
    cv2 = None


def scan(png):
    if cv2 is None:
        return None
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    for det in (cv2.QRCodeDetectorAruco(), cv2.QRCodeDetector()):
        v = det.detectAndDecode(img)[0]
        if v:
            return v
    return ""


def size_of(png):
    return struct.unpack(">II", png[16:24])


def gen(text, **kw):
    return make_qr({"kind": "text", "text": text, **kw})[0]


def check_scan(png, expected):
    got = scan(png)
    assert got is None or got == expected, "не читается сканером"


def test_reed_solomon_known_vector():
    # эталон из спецификации: «HELLO WORLD» 1-M, 10 слов коррекции
    data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
    assert rs_remainder(data, 10) == [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]


def test_png_matches_matrix():
    m, _ = encode("hello", "M")
    n = len(m)
    for size in (200, 500, 1000):
        png = render_png(m, size, "#102030", "#f0e0d0")
        assert size_of(png) == (size, size)
        w, h, rows = decode_png(png, 1000)
        scale = size // (n + 2 * BORDER)
        off = (size - scale * (n + 2 * BORDER)) // 2
        for y in range(n):
            for x in range(n):
                px = rows[off + (y + BORDER) * scale + scale // 2][(off + (x + BORDER) * scale + scale // 2) * 4:][:3]
                assert tuple(px) == ((0x10, 0x20, 0x30) if m[y][x] else (0xF0, 0xE0, 0xD0))


def test_levels_masks_versions():
    for ec in "LMQH":
        for mask in ["auto", 0, 1, 2, 3, 4, 5, 6, 7]:
            check_scan(gen("https://example.com/test?x=1", ec=ec, mask=mask), "https://example.com/test?x=1")
    for n in (5, 20, 50, 120, 300, 700, 1200, 2000):
        t = ("abc123" * 400)[:n]
        m, info = encode(t, "L")
        assert info["modules"] == info["version"] * 4 + 17
        check_scan(gen(t, ec="L", size=1000), t)
    m, info = encode("x" * 2000, "L")
    assert info["version"] <= 40


def test_limits_utf8():
    t = ("0123456789abcdef" * 200)[:2000]
    assert len(t) == 2000 and gen(t, ec="L", size=1000)
    assert gen(("Привет, мир! " * 100)[:1300], ec="L")
    try:
        gen("я" * 2000, ec="L"); assert False
    except ValueError as e:
        assert "слишком длинный" in str(e).lower()
    for bad in ({"text": ""}, {"text": "x" * 2001}, {"text": "a", "fg": "#000000", "bg": "#000000"},
                {"text": "a", "caption": "x" * 61}, {"text": "a", "ec": "Z"}, {"text": "a", "mask": 9}):
        try:
            make_qr({"kind": "text", **bad}); assert False, bad
        except ValueError:
            pass
    assert size_of(gen("hello", size=333)) == (500, 500)


def test_wifi_contact_caption_logo():
    d = make_qr({"kind": "wifi", "ssid": "Home;Net", "password": "p:w"})
    check_scan(d[0], "WIFI:T:WPA;S:Home\\;Net;P:p\\:w;;")
    assert d[2] == "WIFI:T:WPA;S:Home\\;Net;P:p\\:w;;"
    try:
        make_qr({"kind": "wifi", "ssid": ""}); assert False
    except ValueError:
        pass
    assert "BEGIN:VCARD" in make_qr({"kind": "contact", "c_name": "Иван", "c_phone": "+4670123"})[2]
    cap = make_qr({"text": "hello", "caption": "Вход здесь", "frame": True})[0]
    assert size_of(cap)[0] == 500 and size_of(cap)[1] > 500
    check_scan(cap, "hello")
    # логотип: PNG 40x40 красный с альфой
    rows = [bytes([255, 0, 0, 255]) * 40] * 40
    raw = b"".join(b"\x00" + r for r in rows)
    def ch(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    logo = b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 40, 40, 8, 6, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")
    from service import load_logo
    from service import render, parse_settings
    png, _ = render("https://example.com", parse_settings({}), load_logo(logo), "png")
    w, h, r = decode_png(png, 1000)
    c = (w // 2) * 4
    assert tuple(r[h // 2][c:c + 3]) == (255, 0, 0), "логотип в центре"
    check_scan(png, "https://example.com")
    try:
        load_logo(b"GIF89a....."); assert False
    except ValueError as e:
        assert "PNG" in str(e)


def _png(w, h, ct, bd, raw_rows_by_pass, interlace):
    ch = lambda tp, d: struct.pack(">I", len(d)) + tp + d + struct.pack(">I", zlib.crc32(tp + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in raw_rows_by_pass)
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, bd, ct, 0, 0, interlace))
            + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))


def test_logo_png_variants():
    from pngtools import decode_png
    # 16-бит RGB 2x1: (0xFF00,0x8000,0x0000), (0x1234,0x5678,0x9ABC)
    row = struct.pack(">6H", 0xFF00, 0x8000, 0, 0x1234, 0x5678, 0x9ABC)
    w, h, rows = decode_png(_png(2, 1, 2, 16, [row], 0))
    assert rows[0] == bytes([0xFF, 0x80, 0, 255, 0x12, 0x56, 0x9A, 255])
    # чересстрочный 1x1 (Adam7: все остальные проходы пустые)
    w, h, rows = decode_png(_png(1, 1, 6, 8, [bytes([1, 2, 3, 4])], 1))
    assert rows[0] == bytes([1, 2, 3, 4])
    # не-PNG файлы дают понятное сообщение
    for data, word in ((b"\xff\xd8\xff\xe0" + b"0" * 9, "JPEG"), (b"RIFF0000WEBP", "WebP"), (b"GIF89a", "GIF")):
        try:
            decode_png(data); assert False
        except ValueError as e:
            assert word in str(e)


def test_svg_and_speed():
    svg = make_qr({"text": "hello"}, fmt="svg")[0].decode()
    assert svg.startswith("<?xml") and "<path" in svg and 'width="500"' in svg
    t0 = time.time(); gen("x" * 500); assert time.time() - t0 < 2, "дольше 2 секунд"


if __name__ == "__main__":
    print("сканер OpenCV:", "есть" if cv2 else "нет (проверка сканирования пропущена)")
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
