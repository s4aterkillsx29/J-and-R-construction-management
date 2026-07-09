"""Generate crisp multi-resolution Windows shortcut icons for J & R Construction Manager."""
from __future__ import annotations

import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
MASTER = 256
ICO_SIZES = [(256, 256), (128, 128), (96, 96), (72, 72), (64, 64), (48, 48), (40, 40), (32, 32), (24, 24), (20, 20), (16, 16)]


def _font(size: int):
    px = max(7, size // 3)
    for name in ("segoeui.ttf", "Segoe UI Bold.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def _rounded_rect(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _save_icon(path: Path, draw_fn):
    path.parent.mkdir(parents=True, exist_ok=True)
    master = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(master), MASTER)
    master.save(path, format="ICO", sizes=ICO_SIZES)


def _save_png(path: Path, draw_fn):
    master = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(master), MASTER)
    master.save(path, format="PNG", optimize=True)


def icon_manager(draw, size):
    bg = (8, 18, 32, 255)
    accent = (132, 204, 22, 255)
    inner = (190, 242, 100, 255)
    pad = max(1, size // 10)
    _rounded_rect(draw, (pad, pad, size - pad, size - pad), max(2, size // 6), bg)
    inset = size // 5
    _rounded_rect(draw, (inset, inset, size - inset, size - inset), max(2, size // 8), accent)
    if size >= 32:
        mid = size // 2
        _rounded_rect(draw, (mid - size // 6, mid - size // 10, mid + size // 6, mid + size // 10), max(1, size // 16), inner)
        f = _font(size)
        text = "J&R"
        bbox = draw.textbbox((0, 0), text, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((size - tw) / 2, (size - th) / 2 - size * 0.02), text, fill=(6, 12, 4, 255), font=f)
    elif size >= 20:
        c = size // 2
        r = size // 5
        draw.ellipse((c - r, c - r, c + r, c + r), fill=inner)


def icon_installer(draw, size):
    bg = (12, 20, 36, 255)
    gear = (96, 165, 250, 255)
    pad = max(1, size // 10)
    _rounded_rect(draw, (pad, pad, size - pad, size - pad), max(2, size // 6), bg)
    c = size // 2
    r = max(3, size // 4)
    draw.ellipse((c - r, c - r, c + r, c + r), fill=gear)
    draw.ellipse((c - r // 2, c - r // 2, c + r // 2, c + r // 2), fill=bg)
    if size >= 24:
        for i in range(6):
            ang = math.radians(i * 60)
            x1 = c + int(math.cos(ang) * r * 0.55)
            y1 = c + int(math.sin(ang) * r * 0.55)
            x2 = c + int(math.cos(ang) * r * 1.12)
            y2 = c + int(math.sin(ang) * r * 1.12)
            w = max(1, size // 14)
            draw.rectangle((min(x1, x2) - w, min(y1, y2) - w, max(x1, x2) + w, max(y1, y2) + w), fill=gear)


def icon_host(draw, size):
    bg = (14, 22, 38, 255)
    node = (56, 189, 248, 255)
    line = (148, 163, 184, 255)
    pad = max(1, size // 10)
    _rounded_rect(draw, (pad, pad, size - pad, size - pad), max(2, size // 6), bg)
    pts = [(size * 0.25, size * 0.35), (size * 0.75, size * 0.35), (size * 0.5, size * 0.72)]
    lw = max(1, size // 14)
    if size >= 20:
        for i, (x, y) in enumerate(pts):
            for j, (x2, y2) in enumerate(pts):
                if i < j:
                    draw.line((x, y, x2, y2), fill=line, width=lw)
    r = max(2, size // 8)
    for x, y in pts:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=node)


def icon_security(draw, size):
    bg = (6, 22, 18, 255)
    shield = (52, 211, 153, 255)
    pad = max(1, size // 10)
    _rounded_rect(draw, (pad, pad, size - pad, size - pad), max(2, size // 6), bg)
    w = size
    poly = [
        (w * 0.5, w * 0.18),
        (w * 0.78, w * 0.3),
        (w * 0.72, w * 0.62),
        (w * 0.5, w * 0.82),
        (w * 0.28, w * 0.62),
        (w * 0.22, w * 0.3),
    ]
    draw.polygon(poly, fill=shield)
    if size >= 24:
        draw.line(
            (w * 0.38, w * 0.52, w * 0.47, w * 0.62, w * 0.64, w * 0.42),
            fill=bg,
            width=max(2, size // 12),
        )


def main():
    specs = {
        "jrc_manager_app.ico": icon_manager,
        "jrc_installer.ico": icon_installer,
        "jrc_host_server.ico": icon_host,
        "jrc_system_check.ico": icon_security,
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, fn in specs.items():
        out = ASSETS / name
        _save_icon(out, fn)
        print(f"Wrote {out} ({out.stat().st_size} bytes)")
    legacy = ASSETS / "j_and_r_manager_icon.ico"
    shutil.copy2(ASSETS / "jrc_manager_app.ico", legacy)
    png = ASSETS / "j_and_r_manager_icon.png"
    _save_png(png, icon_manager)
    print(f"Wrote {legacy} (legacy alias, {legacy.stat().st_size} bytes)")
    print(f"Wrote {png} ({png.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
