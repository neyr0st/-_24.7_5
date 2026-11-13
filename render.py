"""Рендер матрицы в PNG (свой кодировщик) и SVG. Подпись — встроенный шрифт 5×7."""
from pngtools import encode_png

BORDER = 4  # тихая зона, модулей

_FONT = """
  00 00 00 00 00 00 00
. 00 00 00 00 00 0C 0C
, 00 00 00 00 0C 04 08
- 00 00 00 1F 00 00 00
! 04 04 04 04 04 00 04
? 0E 11 01 02 04 00 04
: 00 0C 0C 00 0C 0C 00
/ 01 01 02 04 08 10 10
+ 00 04 04 1F 04 04 00
( 02 04 08 08 08 04 02
) 08 04 02 02 02 04 08
_ 00 00 00 00 00 00 1F
= 00 00 1F 00 1F 00 00
* 00 15 0E 1F 0E 15 00
' 04 04 08 00 00 00 00
0 0E 11 13 15 19 11 0E
1 04 0C 04 04 04 04 0E
2 0E 11 01 02 04 08 1F
3 1F 02 04 02 01 11 0E
4 02 06 0A 12 1F 02 02
5 1F 10 1E 01 01 11 0E
6 06 08 10 1E 11 11 0E
7 1F 01 02 04 08 08 08
8 0E 11 11 0E 11 11 0E
9 0E 11 11 0F 01 02 0C
A 0E 11 11 1F 11 11 11
B 1E 11 11 1E 11 11 1E
C 0E 11 10 10 10 11 0E
D 1E 11 11 11 11 11 1E
E 1F 10 10 1E 10 10 1F
F 1F 10 10 1E 10 10 10
G 0E 11 10 17 11 11 0F
H 11 11 11 1F 11 11 11
I 0E 04 04 04 04 04 0E
J 07 02 02 02 02 12 0C
K 11 12 14 18 14 12 11
L 10 10 10 10 10 10 1F
M 11 1B 15 15 11 11 11
N 11 11 19 15 13 11 11
O 0E 11 11 11 11 11 0E
P 1E 11 11 1E 10 10 10
Q 0E 11 11 11 15 12 0D
R 1E 11 11 1E 14 12 11
S 0F 10 10 0E 01 01 1E
T 1F 04 04 04 04 04 04
U 11 11 11 11 11 11 0E
V 11 11 11 11 11 0A 04
W 11 11 11 15 15 15 0A
X 11 11 0A 04 0A 11 11
Y 11 11 0A 04 04 04 04
Z 1F 01 02 04 08 10 1F
Б 1F 10 10 1E 11 11 1E
Г 1F 10 10 10 10 10 10
Д 0F 09 09 09 09 1F 11
Ё 0A 1F 10 1E 10 10 1F
Ж 15 15 15 0E 15 15 15
З 0E 11 01 06 01 11 0E
И 11 11 13 15 19 11 11
Й 0A 11 13 15 19 11 11
Л 07 09 09 09 09 09 19
П 1F 11 11 11 11 11 11
У 11 11 0A 04 04 08 10
Ф 04 0E 15 15 15 0E 04
Ц 12 12 12 12 12 1F 01
Ч 11 11 11 0F 01 01 01
Ш 15 15 15 15 15 15 1F
Щ 15 15 15 15 15 1F 01
Ъ 18 08 08 0E 09 09 0E
Ы 11 11 11 19 15 15 19
Ь 10 10 10 1E 11 11 1E
Э 0E 11 01 07 01 11 0E
Ю 12 15 15 1D 15 15 12
Я 0F 11 11 0F 05 09 11
"""
_G = {}
for _ln in _FONT.strip("\n").split("\n"):
    _G[_ln[0]] = [int(h, 16) for h in _ln[2:].split()]
assert all(len(v) == 7 for v in _G.values())
_LAT = dict(zip("АВЕКМНОРСТХ", "ABEKMHOPCTX"))


def _glyph(ch):
    ch = ch.upper()
    ch = _LAT.get(ch, ch)
    return _G.get(ch) or _G["?"]


def _rgb(h):
    return bytes(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _fill(rows, x, y, w, h, col, W):
    for yy in range(max(0, y), min(len(rows), y + h)):
        x0, x1 = max(0, x), min(W, x + w)
        if x1 > x0:
            rows[yy][x0 * 3:x1 * 3] = col * (x1 - x0)


def render_png(matrix, size, fg, bg, logo=None, caption="", frame=False):
    F, B = _rgb(fg), _rgb(bg)
    n = len(matrix)
    total = n + 2 * BORDER

    def cell(x, y):
        return BORDER <= x < BORDER + n and BORDER <= y < BORDER + n and matrix[y - BORDER][x - BORDER]

    rows, scale = [], max(1, size // total)
    if size < total:  # очень маленький размер: ближайший сосед
        idx = [x * total // size for x in range(size)]
        for y in range(size):
            my = y * total // size
            rows.append(bytearray(b"".join(F if cell(i, my) else B for i in idx)))
    else:
        off = (size - total * scale) // 2
        pad_l, pad_r = B * off, B * (size - total * scale - off)
        blank = bytearray(B * size)
        rows = [bytearray(blank) for _ in range(off)]
        for my in range(total):
            line = bytearray(pad_l + b"".join((F if cell(mx, my) else B) * scale for mx in range(total)) + pad_r)
            rows.extend(bytearray(line) for _ in range(scale))
        rows.extend(bytearray(blank) for _ in range(size - len(rows)))
    if logo is not None:
        lw, lh, lrows = logo
        side = max(1, int(n * scale * 0.2) if size >= total else size // 5)
        k = min(side / lw, side / lh)
        nw, nh = max(1, int(lw * k)), max(1, int(lh * k))
        pad = max(2, scale)
        bx, by = (size - nw) // 2, (size - nh) // 2
        _fill(rows, bx - pad, by - pad, nw + 2 * pad, nh + 2 * pad, B, size)
        for y in range(nh):
            src = lrows[min(lh - 1, int(y / k))]
            row = rows[by + y]
            for x in range(nw):
                p = int(x / k) * 4
                a = src[p + 3]
                if a:
                    o = (bx + x) * 3
                    for c in range(3):
                        row[o + c] = (src[p + c] * a + row[o + c] * (255 - a)) // 255
    if caption:
        sc = max(1, min(size // 100, (size * 92 // 100) // (6 * len(caption))))
        strip = 11 * sc
        rows.extend(bytearray(B * size) for _ in range(strip))
        tw = 6 * sc * len(caption) - sc
        x0, y0 = (size - tw) // 2, size + 2 * sc
        for ci, ch in enumerate(caption):
            for gy, bits in enumerate(_glyph(ch)):
                for gx in range(5):
                    if bits >> (4 - gx) & 1:
                        _fill(rows, x0 + (ci * 6 + gx) * sc, y0 + gy * sc, sc, sc, F, size)
    if frame:
        bw, h = (2 if size <= 200 else max(2, size // 150)), len(rows)
        _fill(rows, 0, 0, size, bw, F, size)
        _fill(rows, 0, h - bw, size, bw, F, size)
        _fill(rows, 0, 0, bw, h, F, size)
        _fill(rows, size - bw, 0, bw, h, F, size)
    return encode_png(rows, size)


def render_svg(matrix, size, fg, bg):
    n = len(matrix)
    total = n + 2 * BORDER
    parts = []
    for y, row in enumerate(matrix):
        x = 0
        while x < n:
            if row[x]:
                s = x
                while x < n and row[x]:
                    x += 1
                parts.append(f"M{s + BORDER},{y + BORDER}h{x - s}v1h-{x - s}z")
            else:
                x += 1
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'viewBox="0 0 {total} {total}" shape-rendering="crispEdges">'
            f'<rect width="{total}" height="{total}" fill="{bg}"/>'
            f'<path d="{"".join(parts)}" fill="{fg}"/></svg>')
