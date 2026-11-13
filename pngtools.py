"""Свой кодировщик/декодер PNG на zlib+struct (без Pillow)."""
import struct
import zlib

SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def encode_png(rows, width):
    """rows — список bytes/bytearray RGB длиной width*3."""
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    return (SIG + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, len(rows), 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 6)) + _chunk(b"IEND", b""))


_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
_CH = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _not_png_reason(data):
    if data[:3] == b"\xff\xd8\xff":
        return "Это JPEG, а не PNG (файл переименован). Сохраните иконку как настоящий PNG"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "Это WebP, а не PNG. Сохраните иконку как PNG"
    if data[:3] == b"GIF":
        return "Это GIF, а не PNG. Сохраните иконку как PNG"
    if data[:2] == b"BM":
        return "Это BMP, а не PNG. Сохраните иконку как PNG"
    if data[:4] in (b"\x00\x00\x01\x00",):
        return "Это ICO, а не PNG. Сохраните иконку как PNG"
    if data.lstrip()[:4] in (b"<svg", b"<?xm"):
        return "Это SVG, а не PNG. Сохраните иконку как PNG"
    return "Файл не является PNG (нет сигнатуры PNG)"


def _unfilter(raw, pos, ph, stride, bpp):
    prev = bytearray(stride)
    out = []
    for _ in range(ph):
        f = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += stride + 1
        if len(line) != stride:
            raise ValueError("Повреждённый файл логотипа (обрезан)")
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        elif f != 0:
            raise ValueError("Повреждённый файл логотипа (неизвестный фильтр)")
        prev = line
        out.append(line)
    return out, pos


def _to_rgba(line, pw, ct, bd, plte, trns):
    ch = _CH[ct]
    n = pw * ch
    if bd == 8:
        v = line[:n]
    elif bd == 16:
        v = line[0:2 * n:2]  # берём старший байт
    else:
        per, mask, v = 8 // bd, (1 << bd) - 1, []
        for b in line:
            for k in range(per - 1, -1, -1):
                v.append((b >> (k * bd)) & mask)
        v = v[:n]
        if ct == 0:
            v = [x * 255 // mask for x in v]
    out = bytearray()
    if ct == 6:
        return bytes(v)
    if ct == 2:
        for i in range(0, n, 3):
            out += bytes((v[i], v[i + 1], v[i + 2], 255))
    elif ct == 0:
        for g in v:
            out += bytes((g, g, g, 255))
    elif ct == 4:
        for i in range(0, n, 2):
            out += bytes((v[i], v[i], v[i], v[i + 1]))
    else:
        for idx in v:
            if idx * 3 + 3 > len(plte):
                raise ValueError("Повреждённая палитра логотипа")
            out += plte[idx * 3:idx * 3 + 3] + bytes((trns[idx] if idx < len(trns) else 255,))
    return bytes(out)


def decode_png(data, max_dim=1024):
    """Возвращает (w, h, rows[bytes RGBA]). Поддержка: любая глубина 1/2/4/8/16 бит,
    типы 0/2/3/4/6, чересстрочная развёртка Adam7."""
    if data[:8] != SIG:
        raise ValueError(_not_png_reason(data))
    pos, idat, plte, trns, hdr = 8, b"", b"", b"", None
    while pos + 8 <= len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR" and len(body) == 13:
            hdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat += body
    if hdr is None or not idat:
        raise ValueError("Повреждённый файл логотипа (нет заголовка или данных)")
    w, h, bd, ct, _, _, il = hdr
    if ct not in _CH or bd not in (1, 2, 4, 8, 16) or w < 1 or h < 1 or (ct == 3 and bd == 16):
        raise ValueError("Логотип: неподдерживаемый вариант PNG (глубина %d бит, тип %d)" % (bd, ct))
    if w > max_dim or h > max_dim:
        raise ValueError("Логотип слишком большой (%d×%d): до %d×%d px" % (w, h, max_dim, max_dim))
    try:
        raw = zlib.decompress(idat)
    except zlib.error:
        raise ValueError("Повреждённый файл логотипа (ошибка сжатия)")
    bpp_bits = _CH[ct] * bd
    bpp = max(1, bpp_bits // 8)
    img = [bytearray(w * 4) for _ in range(h)]
    pos = 0
    passes = _ADAM7 if il == 1 else ((0, 0, 1, 1),)
    for xs, ys, dx, dy in passes:
        pw, ph = (w - xs + dx - 1) // dx, (h - ys + dy - 1) // dy
        if pw <= 0 or ph <= 0:
            continue
        lines, pos = _unfilter(raw, pos, ph, (pw * bpp_bits + 7) // 8, bpp)
        for j, line in enumerate(lines):
            px = _to_rgba(line, pw, ct, bd, plte, trns)
            if dx == 1:
                img[ys + j * dy][:] = px
            else:
                row = img[ys + j * dy]
                for i in range(pw):
                    o = (xs + i * dx) * 4
                    row[o:o + 4] = px[i * 4:i * 4 + 4]
    return w, h, [bytes(r) for r in img]
