from __future__ import annotations

"""Generate the Sarman TRANSLATE Windows icon using only the Python standard library."""

import math
import struct
from pathlib import Path

SIZE = 256
SUPERSAMPLE = 4
OUT = Path(__file__).resolve().parents[1] / "assets" / "sarman-translate.ico"


def distance_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if not length_sq:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def cubic_points(p0, p1, p2, p3, steps=96):
    points = []
    for index in range(steps + 1):
        t = index / steps
        u = 1.0 - t
        x = u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0]
        y = u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]
        points.append((x, y))
    return points


def rounded_rect(x, y, left=8, top=8, right=248, bottom=248, radius=54):
    cx = min(max(x, left + radius), right - radius)
    cy = min(max(y, top + radius), bottom - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def render_pixels():
    curves = [
        cubic_points((176, 76), (158, 58), (126, 53), (101, 60)),
        cubic_points((101, 60), (75, 67), (63, 84), (67, 103)),
        cubic_points((67, 103), (71, 122), (89, 132), (119, 141)),
        cubic_points((119, 141), (148, 149), (176, 157), (181, 190)),
        cubic_points((181, 190), (174, 210), (148, 220), (120, 216)),
        cubic_points((120, 216), (100, 214), (84, 205), (74, 192)),
    ]
    segments = [(curve[i], curve[i + 1]) for curve in curves for i in range(len(curve) - 1)]
    pixels = bytearray(SIZE * SIZE * 4)
    samples = range(SUPERSAMPLE)
    for y in range(SIZE):
        for x in range(SIZE):
            accum = [0, 0, 0, 0]
            for sy in samples:
                for sx in samples:
                    px = x + (sx + .5) / SUPERSAMPLE
                    py = y + (sy + .5) / SUPERSAMPLE
                    if rounded_rect(px, py):
                        edge = not rounded_rect(px, py, 10, 10, 246, 246, 52)
                        color = (56, 50, 56) if edge else (20, 21, 26)
                        alpha = 255
                    else:
                        color, alpha = (0, 0, 0), 0
                    nearest = min(
                        distance_to_segment(px, py, a[0], a[1], b[0], b[1])
                        for a, b in segments
                    )
                    # Round caps at both ends.
                    nearest = min(nearest, math.hypot(px - 176, py - 76), math.hypot(px - 74, py - 192))
                    if nearest <= 12.5:
                        blend = max(0.0, min(1.0, (py - 50) / 180))
                        copper = (
                            int(243 * (1 - blend) + 201 * blend),
                            int(178 * (1 - blend) + 102 * blend),
                            int(124 * (1 - blend) + 50 * blend),
                        )
                        color, alpha = copper, 255
                    for channel in range(3):
                        accum[channel] += color[channel]
                    accum[3] += alpha
            offset = ((SIZE - 1 - y) * SIZE + x) * 4
            for channel in range(3):
                pixels[offset + channel] = accum[2 - channel] // (SUPERSAMPLE * SUPERSAMPLE)
            pixels[offset + 3] = accum[3] // (SUPERSAMPLE * SUPERSAMPLE)
    return pixels


def write_ico(path: Path, pixels: bytes):
    mask_stride = ((SIZE + 31) // 32) * 4
    mask = bytes(mask_stride * SIZE)
    dib = struct.pack(
        "<IIIHHIIIIII",
        40, SIZE, SIZE * 2, 1, 32, 0, len(pixels) + len(mask),
        0, 0, 0, 0,
    )
    image = dib + pixels + mask
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(image), 22)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entry + image)


if __name__ == "__main__":
    write_ico(OUT, render_pixels())
    print(f"Created {OUT}")
