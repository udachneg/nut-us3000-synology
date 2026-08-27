#!/usr/bin/env python3

import os
import struct
import sys
import tempfile
import zlib


SIGNATURE = b"\x89PNG\r\n\x1a\n"
ICONS = (("PACKAGE_ICON.PNG", 64), ("PACKAGE_ICON_256.PNG", 256))
BACKGROUND = (20, 42, 74)
SHADOW = (10, 27, 49)
CASE = (31, 62, 96)
PANEL = (15, 38, 67)
ACCENT = (63, 201, 123)
LIGHT = (232, 244, 238)
SOFT_GREEN = (134, 231, 178)
AMBER = (245, 181, 67)


def chunk(kind, payload):
    checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def rounded_rect(x, y, left, top, right, bottom, radius):
    if not left <= x < right or not top <= y < bottom:
        return False
    inner_left = left + radius
    inner_right = right - radius - 1
    inner_top = top + radius
    inner_bottom = bottom - radius - 1
    if inner_left <= x <= inner_right or inner_top <= y <= inner_bottom:
        return True
    center_x = inner_left if x < inner_left else inner_right
    center_y = inner_top if y < inner_top else inner_bottom
    dx = x - center_x
    dy = y - center_y
    return dx * dx + dy * dy <= radius * radius


def rgb(value):
    return bytes(value)


def pixel(size, x, y):
    left = size * 3 // 16
    right = size * 13 // 16
    top = size // 8
    bottom = size * 7 // 8
    radius = max(2, size // 12)
    edge = max(1, size // 32)

    if rounded_rect(x, y, left + edge, top + edge * 2, right + edge, bottom + edge * 2,
                    radius):
        color = SHADOW
    else:
        color = BACKGROUND

    if not rounded_rect(x, y, left, top, right, bottom, radius):
        return rgb(color)
    if not rounded_rect(
        x, y, left + edge, top + edge, right - edge, bottom - edge, max(1, radius - edge)
    ):
        return rgb(ACCENT)

    color = CASE
    panel_left = size * 9 // 32
    panel_right = size * 23 // 32
    panel_top = size * 7 // 32
    panel_bottom = size * 24 // 32
    if rounded_rect(x, y, panel_left, panel_top, panel_right, panel_bottom, radius // 2):
        color = PANEL

    battery_left = size * 5 // 16
    battery_right = size * 11 // 16
    battery_top = size * 10 // 32
    battery_bottom = size * 22 // 32
    terminal_left = size * 7 // 16
    terminal_right = size * 9 // 16
    terminal_top = size * 8 // 32
    terminal_bottom = battery_top
    if terminal_left <= x < terminal_right and terminal_top <= y < terminal_bottom:
        color = LIGHT
    if battery_left <= x < battery_right and battery_top <= y < battery_bottom:
        if (
            x < battery_left + edge
            or x >= battery_right - edge
            or y < battery_top + edge
            or y >= battery_bottom - edge
        ):
            color = LIGHT
        elif y >= size * 14 // 32:
            color = ACCENT
        else:
            color = LIGHT

    dot_y = size * 25 // 32
    dot_radius = max(1, size // 48)
    for dot_x, dot_color in (
        (size * 13 // 32, SOFT_GREEN),
        (size // 2, ACCENT),
        (size * 19 // 32, AMBER),
    ):
        dx = x - dot_x
        dy = y - dot_y
        if dx * dx + dy * dy <= dot_radius * dot_radius:
            color = dot_color
    return rgb(color)


def png_bytes(size):
    rows = []
    for y in range(size):
        rows.append(b"\x00" + b"".join(pixel(size, x, y) for x in range(size)))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def main(argv):
    if len(argv) != 2:
        return 64
    output_dir = os.path.abspath(argv[1])
    if os.path.lexists(output_dir):
        if os.path.islink(output_dir) or not os.path.isdir(output_dir):
            return 1
    else:
        os.makedirs(output_dir, mode=0o755)

    targets = [(os.path.join(output_dir, name), size) for name, size in ICONS]
    if any(os.path.lexists(target) for target, _ in targets):
        return 1

    staged = []
    published = []
    try:
        for _, size in targets:
            descriptor, stage = tempfile.mkstemp(prefix=".nut-us3000-icon.", dir=output_dir)
            staged.append(stage)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(png_bytes(size))
            os.chmod(stage, 0o644)
        for (target, _), stage in zip(targets, staged):
            os.link(stage, target)
            published.append(target)
    except OSError:
        for target in published:
            try:
                os.unlink(target)
            except FileNotFoundError:
                pass
        return 1
    finally:
        for stage in staged:
            try:
                os.unlink(stage)
            except FileNotFoundError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
