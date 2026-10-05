"""Генерация иконок приложения (PWA) без внешних библиотек.

Рисует PNG вручную: zlib + struct. Ни PIL, ни ImageMagick не нужны —
важно, чтобы скрипт работал на любой машине.

Запуск:  python tests/make_icons.py
"""
import struct
import zlib
from pathlib import Path

OUT = Path("web/static/icons")
OUT.mkdir(parents=True, exist_ok=True)

BG = (26, 32, 44)        # тёмно-синий фон
ACCENT = (124, 156, 255)  # голубой акцент
DARK = (13, 15, 20)      # почти чёрный


def png(width: int, height: int, pixels: bytes) -> bytes:
    """Собирает PNG из RGBA-пикселей."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # фильтр строки: None
        raw.extend(pixels[y * stride:(y + 1) * stride])

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def draw(size: int, rounded: bool, maskable: bool = False) -> bytes:
    """Рисует иконку: тёмный фон, голубая рамка, точка-«лампа»."""
    px = bytearray(size * size * 4)
    r = size * 0.22 if rounded else 0  # радиус скругления
    cx = cy = size / 2

    # Рамка-индикатор и точка по центру
    ring_outer = size * 0.30
    ring_inner = size * 0.20
    dot_r = size * (0.085 if maskable else 0.10)

    for y in range(size):
        for x in range(size):
            i = (y * size + x) * 4
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            dist = (dx * dx + dy * dy) ** 0.5

            # Фон со скруглением
            if r:
                # Проверяем, внутри ли скруглённый прямоугольник
                ox = max(abs(dx) - (size / 2 - r), 0)
                oy = max(abs(dy) - (size / 2 - r), 0)
                inside = (ox * ox + oy * oy) <= r * r
            else:
                inside = True

            if not inside:
                px[i:i + 4] = bytes((0, 0, 0, 0))
                continue

            color = BG
            # Кольцо
            if ring_inner <= dist <= ring_outer:
                color = ACCENT
            # Центральная точка
            if dist <= dot_r:
                color = (255, 255, 255) if not maskable else ACCENT
            # Верхняя дуга кольца делает «лампу» живой
            elif ring_inner <= dist <= ring_outer and dy < -size * 0.06:
                color = (168, 200, 255)

            px[i:i + 4] = bytes((*color, 255))

    return png(size, size, bytes(px))


# 72 добавляем: он нужен манифесту как «одно из» уведомлений Android
SIZES = [16, 32, 48, 64, 72, 96, 128, 144, 152, 180, 192, 384, 512]

lines = []
for s in SIZES:
    # maskable нужны для Android: с запасом от обрезки
    data = draw(s, rounded=False if s <= 48 else True)
    (OUT / f"icon-{s}.png").write_bytes(data)
    lines.append(f"icon-{s}.png  {len(data)} Б")

# Иконка с маской для Android (весь квадрат залит, центр — 60%)
for s in (192, 512):
    data = draw(s, rounded=False, maskable=True)
    (OUT / f"maskable-{s}.png").write_bytes(data)
    lines.append(f"maskable-{s}.png  {len(data)} Б")

# Фавиконка для вкладки браузера
(OUT / "favicon.ico").write_bytes(draw(32, rounded=False))
lines.append("favicon.ico")

# Монохромная иконка для maskable в Android (системная)
lines.append("")
lines.append(f"всего файлов: {len(list(OUT.iterdir()))}")

with open("reports/icons.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("written reports/icons.txt")
print("\n".join(lines))