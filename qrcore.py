"""QR-генератор «с нуля»: кодирование (byte-mode, UTF-8), Рид–Соломон, маски, штрафы.
Никаких внешних QR-библиотек. Версии 1–40, уровни коррекции L/M/Q/H."""
import itertools
from functools import lru_cache


class DataTooLong(ValueError):
    pass


LEVELS = ("L", "M", "Q", "H")
_FMT_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}

_ECC_PER_BLOCK = {
    "L": [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
    "M": [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
    "Q": [-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
    "H": [-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
}
_NUM_BLOCKS = {
    "L": [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25],
    "M": [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49],
    "Q": [-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68],
    "H": [-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81],
}


# ---------- Галуа GF(256) и Рид–Соломон ----------
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gmul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


@lru_cache(maxsize=None)
def _rs_generator(degree):
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        for j, c in enumerate(poly):
            nxt[j] ^= c
            nxt[j + 1] ^= _gmul(c, _EXP[i])
        poly = nxt
    return poly[1:]  # старший коэффициент (1) опущен


def rs_remainder(data, degree):
    gen = _rs_generator(degree)
    rem = [0] * degree
    for b in data:
        factor = b ^ rem.pop(0)
        rem.append(0)
        if factor:
            for i, g in enumerate(gen):
                rem[i] ^= _gmul(g, factor)
    return rem


# ---------- Размеры и ёмкость ----------
def _align_positions(ver):
    if ver == 1:
        return []
    n = ver // 7 + 2
    size = ver * 4 + 17
    step = 26 if ver == 32 else (ver * 4 + n * 2 + 1) // (n * 2 - 2) * 2
    return [6] + [size - 7 - step * i for i in range(n - 2, -1, -1)]


def _raw_modules(ver):
    r = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        r -= (25 * n - 10) * n - 55
        if ver >= 7:
            r -= 36
    return r


def _data_codewords(ver, ec):
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ec][ver] * _NUM_BLOCKS[ec][ver]


# ---------- Данные -> кодовые слова ----------
def _make_codewords(data, ver, ec):
    cap = _data_codewords(ver, ec) * 8
    bits = []

    def put(val, n):
        bits.extend((val >> i) & 1 for i in range(n - 1, -1, -1))

    put(0b0100, 4)
    put(len(data), 8 if ver <= 9 else 16)
    for b in data:
        put(b, 8)
    put(0, min(4, cap - len(bits)))
    put(0, -len(bits) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    for pad in itertools.cycle((0xEC, 0x11)):
        if len(words) >= cap // 8:
            break
        words.append(pad)
    return words


def _interleave(words, ver, ec):
    nb, ecl = _NUM_BLOCKS[ec][ver], _ECC_PER_BLOCK[ec][ver]
    raw = _raw_modules(ver) // 8
    short = nb - raw % nb
    short_len = raw // nb
    blocks, k = [], 0
    for i in range(nb):
        dat = words[k:k + short_len - ecl + (0 if i < short else 1)]
        k += len(dat)
        ecc = rs_remainder(dat, ecl)
        if i < short:
            dat = dat + [0]  # выравнивание, пропускается при чередовании
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != short_len - ecl or j >= short:
                out.append(blk[i])
    return out


# ---------- Матрица ----------
def _draw_format(mod, fn, ec, mask, size):
    data = (_FMT_BITS[ec] << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = ((data << 10) | rem) ^ 0x5412

    def setf(x, y, d):
        mod[y][x] = d
        fn[y][x] = True

    bit = lambda i: (bits >> i) & 1 == 1
    for i in range(6):
        setf(8, i, bit(i))
    setf(8, 7, bit(6))
    setf(8, 8, bit(7))
    setf(7, 8, bit(8))
    for i in range(9, 15):
        setf(14 - i, 8, bit(i))
    for i in range(8):
        setf(size - 1 - i, 8, bit(i))
    for i in range(8, 15):
        setf(8, size - 15 + i, bit(i))
    setf(8, size - 8, True)


@lru_cache(maxsize=None)
def _template(ver):
    size = ver * 4 + 17
    mod = [[False] * size for _ in range(size)]
    fn = [[False] * size for _ in range(size)]

    def setf(x, y, d):
        mod[y][x] = d
        fn[y][x] = True

    for i in range(size):
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    setf(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    pos = _align_positions(ver)
    n = len(pos)
    for i, cx in enumerate(pos):
        for j, cy in enumerate(pos):
            if (i == 0 and j == 0) or (i == 0 and j == n - 1) or (i == n - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setf(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
    _draw_format(mod, fn, "L", 0, size)  # резерв областей
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = (ver << 12) | rem
        for i in range(18):
            d = (bits >> i) & 1 == 1
            a, b = size - 11 + i % 3, i // 3
            setf(a, b, d)
            setf(b, a, d)
    return mod, fn


def _place_data(mod, fn, cw, size):
    i, total = 0, len(cw) * 8
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        upward = ((right + 1) & 2) == 0
        for vert in range(size):
            y = size - 1 - vert if upward else vert
            for j in (0, 1):
                x = right - j
                if not fn[y][x] and i < total:
                    mod[y][x] = (cw[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2


_MASKS = (
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
)


def _apply_mask(mod, fn, mask, size):
    f = _MASKS[mask]
    for y in range(size):
        row, frow = mod[y], fn[y]
        for x in range(size):
            if not frow[x] and f(x, y):
                row[x] = not row[x]


def _penalty(m):
    n = len(m)
    rows = ["".join("1" if c else "0" for c in r) for r in m]
    cols = ["".join(rows[y][x] for y in range(n)) for x in range(n)]
    p = 0
    for line in rows + cols:
        for _, g in itertools.groupby(line):
            ln = len(list(g))
            if ln >= 5:
                p += 3 + ln - 5
        s = "0000" + line + "0000"
        for pat in ("10111010000", "00001011101"):
            i = s.find(pat)
            while i != -1:
                p += 40
                i = s.find(pat, i + 1)
    for y in range(n - 1):
        a, b = rows[y], rows[y + 1]
        for x in range(n - 1):
            if a[x] == a[x + 1] == b[x] == b[x + 1]:
                p += 3
    dark = sum(r.count("1") for r in rows)
    total = n * n
    k = -(-abs(dark * 20 - total * 10) // total) - 1
    return p + max(k, 0) * 10


def encode(text, ec="M", mask=None):
    """Возвращает (matrix[list[list[bool]]], info). mask: None/'auto' или 0..7."""
    if ec not in LEVELS:
        raise ValueError("Уровень коррекции должен быть L, M, Q или H")
    if mask in (None, "auto", ""):
        mask = None
    else:
        mask = int(mask)
        if not 0 <= mask <= 7:
            raise ValueError("Маска должна быть от 0 до 7 или auto")
    data = text.encode("utf-8")
    for ver in range(1, 41):
        if 4 + (8 if ver <= 9 else 16) + 8 * len(data) <= _data_codewords(ver, ec) * 8:
            break
    else:
        raise DataTooLong("Текст не помещается в QR-код выбранного уровня коррекции")
    cw = _interleave(_make_codewords(data, ver, ec), ver, ec)
    base, fn = _template(ver)
    size = ver * 4 + 17
    placed = [r[:] for r in base]
    _place_data(placed, fn, cw, size)
    best = None
    for m in ([mask] if mask is not None else range(8)):
        grid = [r[:] for r in placed]
        _apply_mask(grid, fn, m, size)
        _draw_format(grid, [r[:] for r in fn], ec, m, size)
        score = _penalty(grid) if mask is None else 0
        if best is None or score < best[0]:
            best = (score, m, grid)
    return best[2], {"version": ver, "mask": best[1], "ec": ec, "modules": size}
