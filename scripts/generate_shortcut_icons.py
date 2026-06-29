"""Generate modern Windows 11-style shortcut icons for J & R Construction Manager."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def _font(size: int):
    for name in ("segoeui.ttf", "Segoe UI.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rounded_rect(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _save_icon(path: Path, draw_fn):
    path.parent.mkdir(parents=True, exist_ok=True)
    images = []
    for size in SIZES:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw_fn(ImageDraw.Draw(img), size)
        images.append(img)
    images[0].save(path, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[1:])


def icon_manager(draw, size):
  bg = (10, 22, 40, 255)
  accent = (45, 212, 191, 255)
  _rounded_rect(draw, (1, 1, size - 2, size - 2), max(2, size // 8), bg)
  pad = size // 5
  _rounded_rect(draw, (pad, pad, size - pad, size - pad), max(2, size // 10), accent)
  f = _font(max(8, size // 3))
  text = "J&R"
  bbox = draw.textbbox((0, 0), text, font=f)
  tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
  draw.text(((size - tw) / 2, (size - th) / 2 - size * 0.02), text, fill=(3, 17, 10, 255), font=f)


def icon_installer(draw, size):
  bg = (15, 23, 42, 255)
  gear = (96, 165, 250, 255)
  _rounded_rect(draw, (1, 1, size - 2, size - 2), max(2, size // 8), bg)
  c = size // 2
  r = size // 4
  draw.ellipse((c - r, c - r, c + r, c + r), fill=gear)
  draw.ellipse((c - r // 2, c - r // 2, c + r // 2, c + r // 2), fill=bg)
  for i in range(6):
    import math
    ang = math.radians(i * 60)
    x1 = c + int(math.cos(ang) * r * 0.55)
    y1 = c + int(math.sin(ang) * r * 0.55)
    x2 = c + int(math.cos(ang) * r * 1.15)
    y2 = c + int(math.sin(ang) * r * 1.15)
    draw.rectangle((min(x1, x2) - 1, min(y1, y2) - 1, max(x1, x2) + 1, max(y1, y2) + 1), fill=gear)


def icon_host(draw, size):
  bg = (17, 24, 39, 255)
  node = (56, 189, 248, 255)
  line = (148, 163, 184, 255)
  _rounded_rect(draw, (1, 1, size - 2, size - 2), max(2, size // 8), bg)
  pts = [(size * 0.25, size * 0.35), (size * 0.75, size * 0.35), (size * 0.5, size * 0.72)]
  for i, (x, y) in enumerate(pts):
    for j, (x2, y2) in enumerate(pts):
      if i < j:
        draw.line((x, y, x2, y2), fill=line, width=max(1, size // 16))
  r = max(3, size // 8)
  for x, y in pts:
    draw.ellipse((x - r, y - r, x + r, y + r), fill=node)


def icon_security(draw, size):
  bg = (6, 24, 20, 255)
  shield = (52, 211, 153, 255)
  _rounded_rect(draw, (1, 1, size - 2, size - 2), max(2, size // 8), bg)
  w = size
  poly = [(w * 0.5, w * 0.18), (w * 0.78, w * 0.3), (w * 0.72, w * 0.62), (w * 0.5, w * 0.82), (w * 0.28, w * 0.62), (w * 0.22, w * 0.3)]
  draw.polygon(poly, fill=shield)
  draw.line((w * 0.38, w * 0.52, w * 0.47, w * 0.62, w * 0.64, w * 0.42), fill=bg, width=max(2, size // 12))


def main():
  specs = {
    "jrc_manager_app.ico": icon_manager,
    "jrc_installer.ico": icon_installer,
    "jrc_host_server.ico": icon_host,
    "jrc_system_check.ico": icon_security,
  }
  for name, fn in specs.items():
    out = ASSETS / name
    _save_icon(out, fn)
    print(f"Wrote {out}")
  legacy = ASSETS / "j_and_r_manager_icon.ico"
  if not legacy.exists():
    import shutil
    shutil.copy2(ASSETS / "jrc_manager_app.ico", legacy)
    print(f"Wrote {legacy} (legacy alias)")


if __name__ == "__main__":
  main()
