from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "nhi_zues" / "web" / "assets" / "scanner-kabuki-spy-story-sheet.png"
FRAME_W = 256
FRAME_H = 192
FRAMES = 36


def main() -> None:
    sheet = Image.new("RGBA", (FRAME_W * FRAMES, FRAME_H), (0, 0, 0, 0))
    for index in range(FRAMES):
        frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        draw_frame(draw, index)
        sheet.alpha_composite(frame, (index * FRAME_W, 0))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUTPUT)
    print(f"wrote {OUTPUT}")


def draw_frame(draw: ImageDraw.ImageDraw, frame: int) -> None:
    draw_background(draw, frame)
    draw_houses(draw, frame)
    draw_props(draw, frame)
    actor_x, actor_y, pose = actor_path(frame)
    draw_actor(draw, actor_x, actor_y, frame, pose)
    draw_foreground(draw, frame)


def draw_background(draw: ImageDraw.ImageDraw, frame: int) -> None:
    draw.rectangle((0, 0, FRAME_W, FRAME_H), fill=(9, 13, 22, 255))
    for y in range(0, FRAME_H):
        blend = y / FRAME_H
        color = (
            int(10 + 16 * blend),
            int(15 + 12 * blend),
            int(28 + 8 * blend),
            255,
        )
        draw.line((0, y, FRAME_W, y), fill=color)
    moon_glow = 1 + (frame % 12 in (4, 5, 6))
    draw.ellipse((196 - moon_glow, 15 - moon_glow, 222 + moon_glow, 41 + moon_glow), fill=(207, 229, 221, 255))
    draw.ellipse((188, 11, 216, 39), fill=(10, 15, 26, 255))
    stars = [(30, 20), (62, 34), (91, 16), (150, 29), (235, 55), (177, 14), (118, 45)]
    for sx, sy in stars:
        pulse = 1 if (sx + frame) % 9 == 0 else 0
        draw.rectangle((sx, sy, sx + 1 + pulse, sy + 1 + pulse), fill=(161, 218, 226, 180))


def draw_houses(draw: ImageDraw.ImageDraw, frame: int) -> None:
    draw_house(draw, -18, 82, 82, accent=(104, 74, 126, 255), window_on=frame % 18 < 10)
    draw_house(draw, 74, 70, 106, accent=(73, 107, 123, 255), window_on=True)
    draw_house(draw, 178, 88, 90, accent=(116, 73, 69, 255), window_on=frame % 20 > 8)
    draw_bridge_planks(draw)


def draw_house(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    *,
    accent: tuple[int, int, int, int],
    window_on: bool,
) -> None:
    h = 78
    roof = (26, 29, 36, 255)
    wall = (35, 43, 49, 255)
    trim = (89, 99, 105, 255)
    paper = (218, 203, 164, 255) if window_on else (65, 78, 82, 255)
    glow = (226, 186, 97, 95) if window_on else (0, 0, 0, 0)
    draw.rectangle((x + 8, y + 18, x + w - 6, y + h), fill=wall, outline=(8, 11, 16, 255))
    draw.polygon(
        [(x, y + 25), (x + w // 2, y - 8), (x + w + 10, y + 25), (x + w, y + 34), (x + 8, y + 34)],
        fill=roof,
        outline=(90, 102, 112, 255),
    )
    for tx in range(x + 5, x + w + 4, 10):
        draw.line((tx, y + 24, tx + 10, y + 34), fill=(54, 62, 71, 255), width=2)
    draw.rectangle((x + 18, y + 38, x + 42, y + 68), fill=paper, outline=trim)
    draw.rectangle((x + 46, y + 38, x + 70, y + 68), fill=paper, outline=trim)
    draw.line((x + 30, y + 38, x + 30, y + 68), fill=trim)
    draw.line((x + 58, y + 38, x + 58, y + 68), fill=trim)
    draw.line((x + 18, y + 53, x + 70, y + 53), fill=trim)
    if glow[3]:
        draw.rectangle((x + 14, y + 34, x + 74, y + 72), fill=glow)
    draw.rectangle((x + w - 26, y + 46, x + w - 8, y + h), fill=(18, 22, 26, 255), outline=accent)
    draw.rectangle((x + w - 22, y + 50, x + w - 12, y + 58), fill=(11, 14, 18, 255))


def draw_bridge_planks(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((0, 152, FRAME_W, FRAME_H), fill=(16, 21, 25, 255))
    draw.rectangle((0, 148, FRAME_W, 158), fill=(36, 43, 39, 255))
    for x in range(-8, FRAME_W, 18):
        draw.line((x, 158, x + 12, FRAME_H), fill=(47, 55, 51, 255), width=2)
    for y in range(164, FRAME_H, 12):
        draw.line((0, y, FRAME_W, y), fill=(28, 35, 32, 255))


def draw_props(draw: ImageDraw.ImageDraw, frame: int) -> None:
    # Mailbox.
    draw.rectangle((47, 121, 71, 140), fill=(48, 60, 69, 255), outline=(126, 216, 255, 255), width=2)
    draw.rectangle((50, 115, 68, 123), fill=(32, 40, 48, 255), outline=(126, 216, 255, 220))
    draw.rectangle((55, 140, 61, 156), fill=(56, 45, 34, 255))
    if 10 <= frame <= 15:
        letter_y = 120 - (frame - 10)
        draw.rectangle((54, letter_y, 65, letter_y + 7), fill=(235, 226, 199, 255), outline=(96, 81, 61, 255))
        draw.line((55, letter_y + 1, 64, letter_y + 7), fill=(184, 35, 42, 255))
    # Window glint when the actor peeks.
    if 26 <= frame <= 33:
        glint = 2 + (frame % 3)
        draw.line((154, 104, 164 + glint, 94 - glint), fill=(126, 216, 255, 200), width=2)
        draw.line((155, 95, 164 + glint, 104 + glint), fill=(126, 216, 255, 160), width=1)


def actor_path(frame: int) -> tuple[int, int, str]:
    if frame < 10:
        return 12 + frame * 4, 104 + walk_bob(frame), "sneak"
    if frame < 17:
        return 54, 103 + walk_bob(frame), "mail"
    if frame < 26:
        return 58 + (frame - 17) * 9, 104 + walk_bob(frame), "dash"
    if frame < 34:
        return 142, 101 + walk_bob(frame), "peek"
    return 142 - (frame - 34) * 44, 104 + walk_bob(frame), "sneak"


def walk_bob(frame: int) -> int:
    return int(round(math.sin(frame * math.pi / 2) * 2))


def draw_actor(draw: ImageDraw.ImageDraw, x: int, y: int, frame: int, pose: str) -> None:
    step = 1 if frame % 4 in (1, 2) else -1
    crouch = 4 if pose in {"sneak", "peek"} else 0
    draw.ellipse((x - 10, y + 58, x + 52, y + 68), fill=(0, 0, 0, 90))
    draw_cloak(draw, x, y + crouch, frame, pose)
    draw_legs(draw, x, y + crouch, step, pose)
    draw_arms(draw, x, y + crouch, step, pose)
    draw_mask(draw, x + 13, y - 18 + crouch, pose)
    if pose == "peek":
        draw_magnifier(draw, x + 42, y + 8 + crouch, frame)
    if pose == "mail":
        draw_letter(draw, x + 39, y + 22 + crouch, frame)


def draw_cloak(draw: ImageDraw.ImageDraw, x: int, y: int, frame: int, pose: str) -> None:
    flutter = int(math.sin(frame * 0.9) * 3)
    draw.polygon(
        [(x + 6, y + 15), (x + 39, y + 13), (x + 49 + flutter, y + 53), (x + 22, y + 62), (x - 4, y + 52)],
        fill=(14, 18, 24, 255),
        outline=(3, 5, 8, 255),
    )
    draw.polygon(
        [(x + 9, y + 18), (x + 24, y + 14), (x + 20, y + 59), (x - 2, y + 51)],
        fill=(171, 33, 41, 255),
    )
    draw.polygon(
        [(x + 26, y + 14), (x + 39, y + 17), (x + 46, y + 50), (x + 22, y + 59)],
        fill=(225, 163, 58, 255),
    )
    draw.rectangle((x + 4, y + 34, x + 44, y + 42), fill=(5, 8, 12, 255))
    if pose == "dash":
        draw.line((x - 11, y + 18, x - 25, y + 7), fill=(57, 72, 80, 180), width=2)
        draw.line((x - 8, y + 32, x - 28, y + 26), fill=(57, 72, 80, 160), width=2)


def draw_legs(draw: ImageDraw.ImageDraw, x: int, y: int, step: int, pose: str) -> None:
    draw.line((x + 15, y + 55, x + 10 - step * 5, y + 72), fill=(222, 227, 220, 255), width=6)
    draw.line((x + 32, y + 54, x + 37 + step * 5, y + 71), fill=(222, 227, 220, 255), width=6)
    draw.rectangle((x + 3 - step * 5, y + 70, x + 18 - step * 5, y + 75), fill=(24, 27, 31, 255))
    draw.rectangle((x + 31 + step * 5, y + 69, x + 48 + step * 5, y + 74), fill=(24, 27, 31, 255))


def draw_arms(draw: ImageDraw.ImageDraw, x: int, y: int, step: int, pose: str) -> None:
    if pose == "peek":
        draw.line((x + 34, y + 22, x + 50, y + 15), fill=(225, 228, 220, 255), width=6)
        draw.line((x + 10, y + 23, x + 2, y + 39), fill=(225, 228, 220, 255), width=6)
    elif pose == "mail":
        draw.line((x + 35, y + 23, x + 55, y + 25), fill=(225, 228, 220, 255), width=6)
        draw.line((x + 9, y + 23, x - 2, y + 35), fill=(225, 228, 220, 255), width=6)
    else:
        draw.line((x + 10, y + 24, x - 3 - step * 3, y + 39), fill=(225, 228, 220, 255), width=6)
        draw.line((x + 35, y + 24, x + 48 + step * 3, y + 38), fill=(225, 228, 220, 255), width=6)


def draw_mask(draw: ImageDraw.ImageDraw, x: int, y: int, pose: str) -> None:
    draw.rectangle((x + 15, y + 36, x + 25, y + 45), fill=(232, 219, 200, 255))
    draw.polygon(
        [(x + 4, y + 0), (x + 36, y + 0), (x + 44, y + 25), (x + 21, y + 44), (x - 3, y + 25)],
        fill=(232, 229, 218, 255),
        outline=(16, 20, 26, 255),
    )
    draw.rectangle((x + 18, y - 7, x + 24, y - 1), fill=(109, 228, 238, 255))
    draw.polygon([(x + 9, y + 10), (x + 19, y + 18), (x + 9, y + 22)], fill=(177, 35, 43, 255))
    draw.polygon([(x + 33, y + 10), (x + 23, y + 18), (x + 33, y + 22)], fill=(177, 35, 43, 255))
    draw.polygon([(x + 10, y + 24), (x + 18, y + 27), (x + 10, y + 30)], fill=(6, 8, 12, 255))
    draw.polygon([(x + 32, y + 24), (x + 24, y + 27), (x + 32, y + 30)], fill=(6, 8, 12, 255))
    mouth_y = y + 35 if pose != "peek" else y + 33
    draw.arc((x + 13, mouth_y - 4, x + 30, mouth_y + 7), start=20, end=160, fill=(8, 10, 14, 255), width=3)
    draw.line((x + 21, y + 19, x + 19, y + 31), fill=(100, 76, 66, 255), width=2)


def draw_magnifier(draw: ImageDraw.ImageDraw, x: int, y: int, frame: int) -> None:
    pulse = 1 if frame % 4 in (1, 2) else 0
    draw.ellipse((x, y, x + 18 + pulse, y + 18 + pulse), outline=(126, 216, 255, 255), width=3)
    draw.line((x + 14, y + 14, x + 27, y + 28), fill=(126, 216, 255, 255), width=3)
    draw.line((x + 5, y + 8, x + 12, y + 4), fill=(255, 255, 255, 140), width=2)


def draw_letter(draw: ImageDraw.ImageDraw, x: int, y: int, frame: int) -> None:
    drop = max(0, frame - 10)
    draw.rectangle((x, y - drop, x + 15, y + 10 - drop), fill=(235, 226, 199, 255), outline=(96, 81, 61, 255))
    draw.line((x + 1, y + 1 - drop, x + 14, y + 9 - drop), fill=(184, 35, 42, 255))
    draw.line((x + 14, y + 1 - drop, x + 1, y + 9 - drop), fill=(184, 35, 42, 255))


def draw_foreground(draw: ImageDraw.ImageDraw, frame: int) -> None:
    for x in (6, 116, 222):
        sway = int(math.sin((frame + x) * 0.22) * 2)
        draw.rectangle((x, 120, x + 5, 156), fill=(31, 26, 21, 255))
        draw.ellipse((x - 11 + sway, 104, x + 18 + sway, 130), fill=(22, 51, 43, 225))
        draw.ellipse((x - 3 - sway, 96, x + 25 - sway, 120), fill=(25, 64, 51, 225))
    draw.rectangle((0, 154, FRAME_W, 158), fill=(95, 80, 50, 160))
    # Tiny drifting paper scraps make the loop feel alive.
    for n in range(4):
        px = (frame * 7 + n * 63) % (FRAME_W + 28) - 14
        py = 50 + ((frame * 3 + n * 17) % 84)
        draw.rectangle((px, py, px + 3, py + 2), fill=(222, 215, 185, 135))


if __name__ == "__main__":
    main()
