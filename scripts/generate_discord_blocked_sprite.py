from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web" / "assets" / "scanner-kabuki-discord-blocked-sheet.png"
FRAME = 128
FRAMES = 20


def main() -> None:
    sheet = Image.new("RGBA", (FRAME * FRAMES, FRAME), (0, 0, 0, 0))
    for frame in range(FRAMES):
        draw = ImageDraw.Draw(sheet)
        x = frame * FRAME
        local = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        local_draw = ImageDraw.Draw(local)
        draw_frame(local_draw, frame)
        sheet.alpha_composite(local, (x, 0))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUTPUT)
    print(f"wrote {OUTPUT}")


def draw_frame(draw: ImageDraw.ImageDraw, frame: int) -> None:
    phase = frame / max(1, FRAMES - 1)
    bob = int(round((frame % 4 in (1, 2)) * 2))
    slump = max(0.0, (phase - 0.42) / 0.58)
    actor_x = 24 + min(frame, 6) * 2
    actor_y = 39 + bob + int(slump * 9)

    draw_gate(draw, frame)
    draw_denied_badge(draw, frame)
    draw_actor(draw, actor_x, actor_y, slump, frame)
    if frame >= 9:
        draw_tears(draw, actor_x, actor_y, frame)


def draw_gate(draw: ImageDraw.ImageDraw, frame: int) -> None:
    shake = -1 if frame in (5, 7) else 1 if frame == 6 else 0
    gx = 78 + shake
    # Door shadow and frame.
    draw.rectangle((gx + 2, 24, gx + 39, 102), fill=(7, 11, 17, 210))
    draw.rectangle((gx, 20, gx + 36, 104), fill=(22, 30, 39, 255), outline=(120, 152, 169, 255), width=3)
    draw.rectangle((gx + 7, 29, gx + 29, 96), fill=(11, 17, 24, 255), outline=(42, 58, 72, 255), width=2)
    for y in range(34, 94, 12):
        draw.line((gx + 8, y, gx + 29, y + 8), fill=(37, 52, 65, 255), width=2)
    draw.rectangle((gx + 15, 57, gx + 22, 65), fill=(234, 184, 79, 255), outline=(78, 54, 24, 255))
    draw.rectangle((gx + 17, 64, gx + 20, 73), fill=(234, 184, 79, 255))
    # Little threshold line reinforces blocked entry.
    draw.line((gx - 8, 106, gx + 44, 106), fill=(149, 101, 255, 150), width=2)


def draw_denied_badge(draw: ImageDraw.ImageDraw, frame: int) -> None:
    pulse = 1 if frame % 6 in (1, 2) else 0
    cx, cy, r = 96, 21, 13 + pulse
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(28, 9, 15, 255), outline=(239, 107, 120, 255), width=3)
    draw.line((cx - 8, cy + 8, cx + 8, cy - 8), fill=(239, 107, 120, 255), width=4)
    draw.rectangle((16, 99, 72, 108), fill=(14, 21, 28, 220), outline=(239, 107, 120, 190))
    draw.line((23, 103, 65, 103), fill=(239, 107, 120, 220), width=2)


def draw_actor(draw: ImageDraw.ImageDraw, x: int, y: int, slump: float, frame: int) -> None:
    head_drop = int(slump * 6)
    shoulder_drop = int(slump * 8)
    # Shadow.
    draw.ellipse((x - 9, 104, x + 39, 111), fill=(0, 0, 0, 90))

    # Legs.
    draw.rectangle((x + 6, y + 52 + shoulder_drop, x + 15, y + 72 + shoulder_drop), fill=(24, 28, 33, 255))
    draw.rectangle((x + 21, y + 51 + shoulder_drop, x + 30, y + 72 + shoulder_drop), fill=(24, 28, 33, 255))
    draw.rectangle((x + 1, y + 72 + shoulder_drop, x + 17, y + 76 + shoulder_drop), fill=(221, 226, 225, 255))
    draw.rectangle((x + 20, y + 72 + shoulder_drop, x + 37, y + 76 + shoulder_drop), fill=(221, 226, 225, 255))

    # Robe.
    draw.rectangle((x + 3, y + 30 + shoulder_drop, x + 33, y + 58 + shoulder_drop), fill=(26, 29, 33, 255), outline=(8, 10, 13, 255))
    draw.rectangle((x + 5, y + 35 + shoulder_drop, x + 14, y + 58 + shoulder_drop), fill=(184, 35, 42, 255))
    draw.rectangle((x + 20, y + 34 + shoulder_drop, x + 32, y + 58 + shoulder_drop), fill=(214, 156, 58, 255))
    draw.rectangle((x + 2, y + 45 + shoulder_drop, x + 34, y + 50 + shoulder_drop), fill=(7, 11, 17, 255))

    # Slumped arms.
    left_arm_y = y + 38 + shoulder_drop + int(slump * 8)
    right_arm_y = y + 36 + shoulder_drop + int(slump * 10)
    draw.line((x + 4, y + 35 + shoulder_drop, x - 5, left_arm_y + 17), fill=(218, 226, 226, 255), width=5)
    draw.line((x + 32, y + 35 + shoulder_drop, x + 42, right_arm_y + 18), fill=(218, 226, 226, 255), width=5)
    draw.rectangle((x - 7, left_arm_y + 15, x - 2, left_arm_y + 21), fill=(255, 236, 212, 255))
    draw.rectangle((x + 40, right_arm_y + 16, x + 45, right_arm_y + 22), fill=(255, 236, 212, 255))

    # Neck and mask.
    draw.rectangle((x + 14, y + 25 + head_drop, x + 22, y + 33 + head_drop), fill=(236, 226, 205, 255))
    draw.polygon(
        [
            (x + 4, y + 4 + head_drop),
            (x + 32, y + 4 + head_drop),
            (x + 37, y + 28 + head_drop),
            (x + 18, y + 39 + head_drop),
            (x, y + 28 + head_drop),
        ],
        fill=(232, 230, 221, 255),
        outline=(24, 31, 38, 255),
    )
    draw.rectangle((x + 15, y - 2 + head_drop, x + 20, y + 3 + head_drop), fill=(100, 224, 236, 255))
    draw.line((x + 8, y + 13 + head_drop, x + 16, y + 19 + head_drop), fill=(182, 37, 43, 255), width=4)
    draw.line((x + 29, y + 13 + head_drop, x + 21, y + 19 + head_drop), fill=(182, 37, 43, 255), width=4)
    draw.polygon([(x + 10, y + 21 + head_drop), (x + 17, y + 23 + head_drop), (x + 11, y + 26 + head_drop)], fill=(7, 11, 17, 255))
    draw.polygon([(x + 27, y + 21 + head_drop), (x + 20, y + 23 + head_drop), (x + 26, y + 26 + head_drop)], fill=(7, 11, 17, 255))
    mouth_y = y + 32 + head_drop + int(slump * 3)
    draw.arc((x + 12, mouth_y - 1, x + 26, mouth_y + 9), start=200, end=340, fill=(11, 14, 19, 255), width=3)
    # Tiny question mark over the mask after denial.
    if frame >= 8:
        draw.arc((x + 36, y + 0, x + 47, y + 12), start=200, end=70, fill=(126, 216, 255, 235), width=2)
        draw.rectangle((x + 41, y + 14, x + 44, y + 17), fill=(126, 216, 255, 235))


def draw_tears(draw: ImageDraw.ImageDraw, x: int, y: int, frame: int) -> None:
    offset = (frame % 5) * 2
    draw.ellipse((x + 10, y + 28 + offset, x + 14, y + 34 + offset), fill=(126, 216, 255, 230))
    if frame >= 13:
        draw.ellipse((x + 25, y + 27 + (offset // 2), x + 29, y + 33 + (offset // 2)), fill=(126, 216, 255, 210))


if __name__ == "__main__":
    main()
