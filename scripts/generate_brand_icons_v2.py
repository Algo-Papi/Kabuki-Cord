"""Build Kabuki-Cord's desktop/web icon family from the generated mask mark."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
MARK_PATH = ROOT / "src" / "nhi_zues" / "web" / "assets" / "kabuki-mask-mark-v2.png"
WEB_ASSETS = MARK_PATH.parent
APP_ASSETS = ROOT / "src" / "nhi_zues" / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 180, 192, 256, 512)


def rounded_icon(size: int, *, badge: bool = False) -> Image.Image:
    scale = 4
    canvas_size = size * scale
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = max(4 * scale, round(canvas_size * 0.22))

    # The background keeps the white mask readable on both light and dark chrome.
    draw.rounded_rectangle(
        (0, 0, canvas_size - 1, canvas_size - 1),
        radius=radius,
        fill=(15, 24, 34, 255),
        outline=(91, 218, 236, 255),
        width=max(scale, round(canvas_size * 0.025)),
    )

    mark = Image.open(MARK_PATH).convert("RGBA")
    mark = ImageEnhance.Contrast(mark).enhance(1.08)
    inset = round(canvas_size * (0.12 if size >= 32 else 0.1))
    available = canvas_size - inset * 2
    mark.thumbnail((available, available), Image.Resampling.LANCZOS)
    x = (canvas_size - mark.width) // 2
    y = (canvas_size - mark.height) // 2
    image.alpha_composite(mark, (x, y))

    if badge:
        dot = round(canvas_size * 0.22)
        margin = round(canvas_size * 0.07)
        left = canvas_size - margin - dot
        top = canvas_size - margin - dot
        draw.ellipse(
            (left - scale, top - scale, left + dot + scale, top + dot + scale),
            fill=(15, 24, 34, 255),
        )
        draw.ellipse((left, top, left + dot, top + dot), fill=(239, 74, 92, 255))

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    if not MARK_PATH.exists():
        raise SystemExit(f"Missing source mark: {MARK_PATH}")
    WEB_ASSETS.mkdir(parents=True, exist_ok=True)
    APP_ASSETS.mkdir(parents=True, exist_ok=True)

    rendered = {size: rounded_icon(size) for size in SIZES}
    for size, image in rendered.items():
        image.save(WEB_ASSETS / f"app-icon-{size}.png", optimize=True)
    rendered[512].save(WEB_ASSETS / "app-icon.png", optimize=True)
    rounded_icon(32, badge=True).save(WEB_ASSETS / "app-icon-badge-32.png", optimize=True)

    rendered[512].save(APP_ASSETS / "app-icon.png", optimize=True)
    rendered[256].save(APP_ASSETS / "app-icon-256.png", optimize=True)
    rendered[256].save(
        APP_ASSETS / "app.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    rounded_icon(32, badge=True).save(
        APP_ASSETS / "taskbar-badge.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32)],
    )


if __name__ == "__main__":
    main()
