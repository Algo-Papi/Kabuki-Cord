from __future__ import annotations

import json
import math
import shutil
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design_assets" / "kabuki-actor-reference.png"
OUTPUT_DIR = ROOT / "src" / "nhi_zues" / "web" / "assets" / "monitor_spy_frames"
FRAME_W = 960
FRAME_H = 720
FRAMES = 48
FRAME_MS = 180


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing source reference: {SOURCE}")
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    actor = actor_cutout(SOURCE)
    for frame_index in range(FRAMES):
        frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 255))
        draw_scene(frame, frame_index)
        draw_actor_scene(frame, actor, frame_index)
        draw_foreground(frame, frame_index)
        out = OUTPUT_DIR / f"frame_{frame_index:03d}.png"
        frame.save(out, optimize=True)
    manifest = {
        "frame_count": FRAMES,
        "frame_ms": FRAME_MS,
        "width": FRAME_W,
        "height": FRAME_H,
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {FRAMES} frames to {OUTPUT_DIR}")


def actor_cutout(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    pixels = image.load()
    width, height = image.size
    background = [[False] * height for _ in range(width)]
    queue: deque[tuple[int, int]] = deque()

    def is_background(x: int, y: int) -> bool:
        r, g, b, a = pixels[x, y]
        if a < 8:
            return True
        # Only remove border-connected near-white pixels so the mask stays intact.
        return r > 238 and g > 238 and b > 238 and max(r, g, b) - min(r, g, b) < 18

    for x in range(width):
        for y in (0, height - 1):
            if is_background(x, y) and not background[x][y]:
                background[x][y] = True
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            if is_background(x, y) and not background[x][y]:
                background[x][y] = True
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height or background[nx][ny]:
                continue
            if is_background(nx, ny):
                background[nx][ny] = True
                queue.append((nx, ny))

    alpha = Image.new("L", image.size, 255)
    alpha_pixels = alpha.load()
    for x in range(width):
        for y in range(height):
            if background[x][y]:
                alpha_pixels[x, y] = 0
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.35))
    image.putalpha(alpha)
    bbox = image.getbbox()
    if not bbox:
        return image
    left, top, right, bottom = bbox
    pad = 18
    return image.crop((
        max(0, left - pad),
        max(0, top - pad),
        min(width, right + pad),
        min(height, bottom + pad),
    ))


def draw_scene(frame: Image.Image, frame_index: int) -> None:
    draw = ImageDraw.Draw(frame, "RGBA")
    draw_sky(draw, frame_index)
    draw_moon_and_clouds(draw, frame_index)
    draw_house(draw, 34, 270, 290, 270, accent=(126, 84, 118, 255), lit=frame_index % 18 < 11)
    draw_house(draw, 330, 230, 330, 305, accent=(75, 111, 125, 255), lit=True)
    draw_house(draw, 654, 278, 280, 260, accent=(132, 71, 70, 255), lit=frame_index % 22 > 8)
    draw_mailbox(draw, frame_index)
    draw_ground(draw)


def draw_sky(draw: ImageDraw.ImageDraw, frame_index: int) -> None:
    for y in range(FRAME_H):
        t = y / FRAME_H
        color = (
            int(7 + 21 * t),
            int(12 + 15 * t),
            int(24 + 13 * t),
            255,
        )
        draw.line((0, y, FRAME_W, y), fill=color)
    stars = [
        (54, 44), (112, 91), (183, 48), (258, 126), (379, 68), (452, 104),
        (574, 57), (626, 122), (716, 42), (820, 92), (899, 55), (930, 148),
    ]
    for sx, sy in stars:
        pulse = 1 if (sx + frame_index * 7) % 19 in (0, 1) else 0
        draw.rectangle((sx, sy, sx + 2 + pulse, sy + 2 + pulse), fill=(170, 228, 236, 160))


def draw_moon_and_clouds(draw: ImageDraw.ImageDraw, frame_index: int) -> None:
    pulse = 2 if frame_index % 12 in (5, 6, 7) else 0
    draw.ellipse((760 - pulse, 42 - pulse, 836 + pulse, 118 + pulse), fill=(205, 224, 218, 255))
    draw.ellipse((734, 32, 815, 111), fill=(9, 14, 25, 255))
    drift = frame_index % 32
    for cx, cy, scale in ((130 + drift, 118, 1.0), (512 - drift // 2, 84, 0.74), (838 - drift, 175, 0.88)):
        draw_cloud(draw, int(cx), cy, scale)


def draw_cloud(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float) -> None:
    color = (49, 62, 74, 120)
    for ox, oy, w, h in ((0, 8, 90, 24), (22, -2, 56, 30), (56, 6, 70, 22)):
        draw.ellipse(
            (
                x + int(ox * scale),
                y + int(oy * scale),
                x + int((ox + w) * scale),
                y + int((oy + h) * scale),
            ),
            fill=color,
        )


def draw_house(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    accent: tuple[int, int, int, int],
    lit: bool,
) -> None:
    wall = (32, 41, 47, 255)
    trim = (88, 100, 105, 255)
    roof = (24, 27, 35, 255)
    paper = (224, 203, 151, 255) if lit else (63, 76, 82, 255)
    glow = (232, 178, 72, 70) if lit else (0, 0, 0, 0)

    draw.rectangle((x + 18, y + 72, x + w - 16, y + h), fill=wall, outline=(8, 11, 16, 255), width=3)
    draw.polygon(
        [(x, y + 80), (x + w // 2, y), (x + w + 26, y + 82), (x + w + 4, y + 111), (x + 12, y + 110)],
        fill=roof,
        outline=(99, 110, 120, 255),
    )
    for tile in range(x + 4, x + w + 18, 30):
        draw.line((tile, y + 78, tile + 24, y + 105), fill=(54, 62, 71, 255), width=3)
    for beam_x in range(x + 34, x + w - 30, 54):
        draw.rectangle((beam_x, y + 82, beam_x + 8, y + h), fill=(22, 28, 31, 255))

    window_y = y + 128
    window_w = 56
    for wx in (x + 54, x + 126):
        if glow[3]:
            draw.rectangle((wx - 10, window_y - 12, wx + window_w + 10, window_y + 78), fill=glow)
        draw.rectangle((wx, window_y, wx + window_w, window_y + 66), fill=paper, outline=trim, width=3)
        draw.line((wx + window_w // 2, window_y, wx + window_w // 2, window_y + 66), fill=trim, width=2)
        draw.line((wx, window_y + 33, wx + window_w, window_y + 33), fill=trim, width=2)
        for slat in range(wx + 9, wx + window_w, 18):
            draw.line((slat, window_y + 3, slat, window_y + 63), fill=(117, 122, 119, 125), width=1)

    door_x = x + w - 76
    draw.rectangle((door_x, y + 145, door_x + 52, y + h), fill=(15, 18, 22, 255), outline=accent, width=3)
    draw.rectangle((door_x + 16, y + 166, door_x + 34, y + 186), fill=(8, 10, 13, 255), outline=(91, 70, 55, 255))
    draw.rectangle((x + 34, y + h - 22, x + w - 32, y + h - 12), fill=(18, 22, 25, 255))


def draw_mailbox(draw: ImageDraw.ImageDraw, frame_index: int) -> None:
    x, y = 292, 515
    draw.rectangle((x + 22, y + 54, x + 34, y + 112), fill=(64, 49, 35, 255))
    draw.rectangle((x, y + 24, x + 76, y + 64), fill=(45, 58, 67, 255), outline=(126, 216, 255, 255), width=3)
    draw.rectangle((x + 8, y + 8, x + 68, y + 28), fill=(28, 36, 43, 255), outline=(126, 216, 255, 210), width=3)
    draw.rectangle((x + 62, y + 33, x + 72, y + 56), fill=(160, 53, 58, 255))
    if 12 <= frame_index <= 19:
        t = (frame_index - 12) / 7
        lx = int(404 - 82 * t)
        ly = int(480 + 38 * t)
        draw_letter(draw, lx, ly, angle=-10 + int(18 * t))


def draw_ground(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((0, 560, FRAME_W, FRAME_H), fill=(14, 18, 20, 255))
    draw.rectangle((0, 546, FRAME_W, 572), fill=(39, 47, 42, 255))
    for x in range(-20, FRAME_W + 30, 42):
        draw.line((x, 572, x + 28, FRAME_H), fill=(48, 58, 52, 255), width=3)
    for y in range(586, FRAME_H, 28):
        draw.line((0, y, FRAME_W, y), fill=(26, 33, 30, 255), width=2)
    draw.line((0, 546, FRAME_W, 546), fill=(136, 98, 56, 120), width=3)


def draw_actor_scene(frame: Image.Image, actor: Image.Image, frame_index: int) -> None:
    x, y, height, rotation, flip, alpha = actor_pose(frame_index)
    draw_shadow(frame, x, y, height, alpha)
    actor_frame = actor_variant(actor, height=height, rotation=rotation, flip=flip, alpha=alpha)
    frame.alpha_composite(actor_frame, (int(x - actor_frame.width / 2), int(y - actor_frame.height)))
    draw = ImageDraw.Draw(frame, "RGBA")
    if 12 <= frame_index <= 19:
        # Held envelope before it reaches the mailbox.
        if frame_index < 16:
            draw_letter(draw, int(x - 28), int(y - height * 0.38), angle=-12)
    if 31 <= frame_index <= 40:
        draw_magnifier(draw, int(x + 70), int(y - height * 0.58), frame_index)
        draw_window_glint(draw, frame_index)


def actor_pose(frame_index: int) -> tuple[int, int, int, float, bool, int]:
    bob = int(math.sin(frame_index * math.pi / 2) * 5)
    if frame_index < 12:
        return 80 + frame_index * 24, 570 + bob, 270, -5 + math.sin(frame_index * 0.7) * 3, False, 255
    if frame_index < 20:
        return 378, 570 + bob // 2, 288, -2 + math.sin(frame_index) * 2, False, 255
    if frame_index < 31:
        return 382 + (frame_index - 20) * 28, 570 + bob, 268, 5 + math.sin(frame_index * 0.8) * 4, False, 255
    if frame_index < 41:
        return 714, 566 + bob // 2, 292, -8 + math.sin(frame_index * 0.4) * 2, True, 255
    # Exit behind the right-side foreground so the loop can restart cleanly.
    fade = max(70, 255 - (frame_index - 41) * 30)
    return 714 + (frame_index - 40) * 43, 570 + bob, 270, 3, False, fade


def actor_variant(actor: Image.Image, *, height: int, rotation: float, flip: bool, alpha: int) -> Image.Image:
    width = max(1, int(actor.width * (height / actor.height)))
    rendered = actor.resize((width, height), Image.Resampling.LANCZOS)
    rendered = ImageEnhance.Contrast(rendered).enhance(1.08)
    rendered = ImageEnhance.Color(rendered).enhance(1.04)
    if flip:
        rendered = rendered.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if alpha < 255:
        alpha_layer = rendered.getchannel("A").point(lambda value: int(value * alpha / 255))
        rendered.putalpha(alpha_layer)
    return rendered.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)


def draw_shadow(frame: Image.Image, x: int, y: int, height: int, alpha: int) -> None:
    shadow = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow, "RGBA")
    width = int(height * 0.58)
    draw.ellipse((x - width // 2, y - 30, x + width // 2, y + 10), fill=(0, 0, 0, min(alpha, 150)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(9))
    frame.alpha_composite(shadow)


def draw_letter(draw: ImageDraw.ImageDraw, x: int, y: int, *, angle: int = 0) -> None:
    letter = Image.new("RGBA", (60, 38), (0, 0, 0, 0))
    ld = ImageDraw.Draw(letter, "RGBA")
    ld.rectangle((2, 2, 58, 36), fill=(236, 226, 197, 255), outline=(98, 76, 54, 255), width=2)
    ld.line((4, 4, 30, 23), fill=(170, 46, 54, 255), width=2)
    ld.line((56, 4, 30, 23), fill=(170, 46, 54, 255), width=2)
    ld.line((4, 34, 25, 18), fill=(170, 46, 54, 150), width=1)
    ld.line((56, 34, 35, 18), fill=(170, 46, 54, 150), width=1)
    letter = letter.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    draw.bitmap((x, y), letter)


def draw_magnifier(draw: ImageDraw.ImageDraw, x: int, y: int, frame_index: int) -> None:
    pulse = 2 if frame_index % 4 in (1, 2) else 0
    draw.ellipse((x, y, x + 44 + pulse, y + 44 + pulse), outline=(126, 216, 255, 255), width=6)
    draw.line((x + 36, y + 36, x + 68, y + 70), fill=(126, 216, 255, 255), width=7)
    draw.line((x + 13, y + 17, x + 27, y + 10), fill=(255, 255, 255, 160), width=4)


def draw_window_glint(draw: ImageDraw.ImageDraw, frame_index: int) -> None:
    pulse = frame_index % 5
    draw.line((826, 392, 858 + pulse * 2, 360 - pulse), fill=(126, 216, 255, 190), width=4)
    draw.line((828, 362, 856 + pulse * 2, 394 + pulse), fill=(126, 216, 255, 130), width=3)


def draw_foreground(frame: Image.Image, frame_index: int) -> None:
    draw = ImageDraw.Draw(frame, "RGBA")
    for x, h in ((15, 175), (236, 135), (900, 205)):
        sway = int(math.sin((frame_index + x) * 0.2) * 5)
        draw.rectangle((x, 430, x + 18, 568), fill=(31, 25, 20, 255))
        draw.ellipse((x - 50 + sway, 350, x + 70 + sway, 456), fill=(20, 52, 42, 225))
        draw.ellipse((x - 28 - sway, 318, x + 90 - sway, 420), fill=(26, 67, 52, 235))
        draw.line((x + 8, 428, x + 8 + sway, 568), fill=(59, 48, 34, 180), width=3)
    # Right building post masks the actor during the peek and exit.
    draw.rectangle((843, 330, 873, 568), fill=(18, 23, 27, 245), outline=(90, 102, 112, 220), width=2)
    draw.rectangle((0, 562, FRAME_W, 570), fill=(122, 88, 52, 170))
    for i in range(8):
        px = (frame_index * 11 + i * 119) % (FRAME_W + 40) - 20
        py = 120 + ((frame_index * 5 + i * 41) % 340)
        draw.rectangle((px, py, px + 6, py + 4), fill=(225, 214, 176, 105))


if __name__ == "__main__":
    main()
