#!/usr/bin/env python3
"""Создание QR одной командой:  python cli.py "https://example.com" -o qr.png --size 500 --ec M"""
import argparse
import sys
from service import make_qr


def main(argv=None):
    p = argparse.ArgumentParser(description="QR-генератор (без внешних QR-библиотек)")
    p.add_argument("text", nargs="?", default="")
    p.add_argument("-o", "--output", default="qr.png")
    p.add_argument("--size", type=int, default=500, help="200 | 500 | 1000")
    p.add_argument("--ec", default="M", choices=list("LMQH"))
    p.add_argument("--mask", default="auto", help="auto или 0..7")
    p.add_argument("--fg", default="#000000")
    p.add_argument("--bg", default="#ffffff")
    p.add_argument("--caption", default="")
    p.add_argument("--logo", help="путь к файлу логотипа")
    a = p.parse_args(argv)
    fmt = "svg" if a.output.lower().endswith(".svg") else "png"
    logo = open(a.logo, "rb").read() if a.logo else None
    try:
        data, *_ = make_qr({"kind": "text", "text": a.text, "ec": a.ec, "mask": a.mask, "size": a.size,
                            "fg": a.fg, "bg": a.bg, "caption": a.caption}, logo, fmt)
    except ValueError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    with open(a.output, "wb") as fh:
        fh.write(data)
    print(f"Сохранено: {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
