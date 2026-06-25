from __future__ import annotations

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
KEYFRAME_DIR = ROOT / "web" / "assets" / "source" / "dojo_sweep_keyframes"
OUTPUT_DIR = ROOT / "web" / "assets" / "monitor_dojo_sweep_frames"
FRAME_W = 960
FRAME_H = 720
FRAMES = 48
FRAME_MS = 150
KEYFRAME_NAMES = (
    "key_000.png",
    "key_001.png",
    "key_002.png",
    "key_003.png",
    "key_004.png",
)
POSE_SEQUENCE = (0, 1, 2, 3, 4, 3, 2, 1)
EYE_POINTS = (
    ((411, 234), (461, 232)),
    ((414, 287), (469, 287)),
    ((404, 243), (461, 243)),
    ((391, 244), (447, 237)),
    ((291, 219), (348, 217)),
)


def main() -> None:
    keyframes = load_keyframes()
    clear_output_dir()
    for index in range(FRAMES):
        frame = render_frame(keyframes, index)
        save_pixel_png(frame, OUTPUT_DIR / f"frame_{index:03d}.png")
    manifest = {
        "frame_count": FRAMES,
        "frame_ms": FRAME_MS,
        "width": FRAME_W,
        "height": FRAME_H,
        "source": "../source/dojo_sweep_keyframes/key_000.png",
        "keyframes": list(KEYFRAME_NAMES),
        "timing": "scanner-dwell-synced",
        "animation": "five-pose-sweep-cycle-with-dust-vortex",
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {FRAMES} animated Dojo Sweep frames to {OUTPUT_DIR}")


def clear_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.glob("frame_*.png"):
        path.unlink()
    manifest = OUTPUT_DIR / "manifest.json"
    if manifest.exists():
        manifest.unlink()


def load_keyframes() -> list[Image.Image]:
    keyframes: list[Image.Image] = []
    for name in KEYFRAME_NAMES:
        path = KEYFRAME_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"Missing Dojo Sweep keyframe: {path}")
        keyframes.append(framed_source(path))
    return keyframes


def framed_source(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    width, height = image.size
    target_ratio = FRAME_W / FRAME_H
    if width / height > target_ratio:
        crop_w = int(height * target_ratio)
        left = max(0, (width - crop_w) // 2)
        image = image.crop((left, 0, left + crop_w, height))
    else:
        crop_h = int(width / target_ratio)
        top = max(0, (height - crop_h) // 2)
        image = image.crop((0, top, width, top + crop_h))
    return image.resize((FRAME_W, FRAME_H), Image.Resampling.LANCZOS)


def render_frame(keyframes: list[Image.Image], index: int) -> Image.Image:
    pose = pose_frame(keyframes, index)
    pose = pulse_contrast(pose, index)
    overlay = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    draw_whirlwind(draw, index)
    draw_sweep_particles(draw, index)
    draw_leaf_flecks(draw, index)
    draw_broom_impact_flash(draw, index)
    draw_red_vignette(draw, index)
    overlay = overlay.filter(ImageFilter.GaussianBlur(0.22))
    frame = Image.alpha_composite(pose, overlay)
    frame = Image.alpha_composite(frame, red_eye_glow(index))
    return frame.convert("RGB")


def pose_frame(keyframes: list[Image.Image], index: int) -> Image.Image:
    # Sweep forward across the first five poses, then recoil through the middle
    # poses so the loop reads as continuous motion instead of a static shake.
    start, end, t, dx, dy = pose_state(index)
    frame = Image.blend(keyframes[start], keyframes[end], t)
    # Tiny camera emphasis only, not the fake animation source.
    if dx or dy:
        shifted = Image.new("RGBA", (FRAME_W, FRAME_H), (6, 8, 13, 255))
        shifted.alpha_composite(frame, (dx, dy))
        frame = shifted.crop((0, 0, FRAME_W, FRAME_H))
    return frame


def pose_state(index: int) -> tuple[int, int, float, int, int]:
    segment_count = len(POSE_SEQUENCE)
    position = (index / FRAMES) * segment_count
    segment = int(position) % segment_count
    local = position - math.floor(position)
    start = POSE_SEQUENCE[segment]
    end = POSE_SEQUENCE[(segment + 1) % segment_count]
    t = smoothstep(local)
    beat = math.sin((index / FRAMES) * math.tau * 2)
    dx = int(round(2.0 * beat))
    dy = int(round(1.5 * math.sin((index / FRAMES) * math.tau * 4)))
    return start, end, t, dx, dy


def pulse_contrast(image: Image.Image, index: int) -> Image.Image:
    pulse = 1.0 + 0.035 * abs(math.sin(index * math.tau / 12))
    contrasted = ImageEnhance.Contrast(image).enhance(pulse)
    return ImageEnhance.Color(contrasted).enhance(1.0 + 0.02 * math.sin(index * math.tau / 16))


def draw_whirlwind(draw: ImageDraw.ImageDraw, index: int) -> None:
    cycle = index / FRAMES
    sweep = 0.5 - 0.5 * math.cos(cycle * math.tau)
    wind = math.sin(cycle * math.tau * 2)
    base_alpha = 95 + int(55 * abs(wind))
    for layer in range(5):
        inset = layer * 25
        y_lift = int(layer * 12 + abs(wind) * 18)
        bbox = (
            45 + inset,
            508 - y_lift,
            FRAME_W - 42 - inset,
            760 - layer * 10,
        )
        start = 188 + int(sweep * 48) - layer * 8
        end = 350 + int(sweep * 38) - layer * 5
        alpha = max(22, base_alpha - layer * 18)
        width = max(2, 8 - layer)
        color = (231, 184, 107, alpha)
        draw.arc(bbox, start, end, fill=color, width=width)
        draw.arc(
            (bbox[0] + 18, bbox[1] + 12, bbox[2] - 22, bbox[3] - 8),
            start + 15,
            end + 21,
            fill=(255, 219, 143, max(15, alpha - 42)),
            width=max(1, width - 3),
        )


def draw_sweep_particles(draw: ImageDraw.ImageDraw, index: int) -> None:
    rng = random.Random(9200 + index)
    cycle = index / FRAMES
    sweep_x = 120 + int((0.5 - 0.5 * math.cos(cycle * math.tau)) * 720)
    gust = abs(math.sin(cycle * math.tau * 2))
    for particle in range(78):
        orbit = (particle / 78) * math.tau + cycle * math.tau * (1.4 + (particle % 4) * 0.18)
        radius = 70 + (particle % 17) * 8 + gust * 42
        x = int(sweep_x + math.cos(orbit) * radius + rng.randint(-12, 12))
        y = int(625 + math.sin(orbit * 0.72) * (28 + gust * 34) + rng.randint(-18, 20))
        if x < -12 or x > FRAME_W + 12 or y < 430 or y > FRAME_H + 16:
            continue
        size = rng.choice((2, 2, 3, 3, 4, 5, 6))
        alpha = rng.randint(58, 150)
        color = rng.choice(
            (
                (218, 166, 86, alpha),
                (245, 207, 128, max(24, alpha - 18)),
                (154, 101, 66, max(20, alpha - 28)),
                (107, 70, 64, max(16, alpha - 42)),
            )
        )
        draw.ellipse((x, y, x + size, y + size), fill=color)
    for streak in range(14):
        x = sweep_x - 270 + streak * 42 + rng.randint(-18, 18)
        y = 645 + rng.randint(-38, 10)
        draw.line(
            (x, y, x + rng.randint(35, 88), y - rng.randint(5, 29)),
            fill=(236, 185, 98, 80 + int(gust * 56)),
            width=rng.choice((1, 2, 2, 3)),
        )


def draw_leaf_flecks(draw: ImageDraw.ImageDraw, index: int) -> None:
    rng = random.Random(12100)
    cycle = index / FRAMES
    for leaf in range(30):
        start_x = rng.randint(20, FRAME_W - 20)
        speed = rng.uniform(120, 330)
        drift = (cycle * speed + leaf * 23) % (FRAME_W + 120)
        x = int((start_x + drift) % (FRAME_W + 80)) - 40
        y = int(470 + rng.randint(-58, 210) + math.sin(cycle * math.tau * 2 + leaf) * 22)
        angle = cycle * math.tau * 3 + leaf
        length = rng.randint(5, 11)
        dx = int(math.cos(angle) * length)
        dy = int(math.sin(angle) * max(2, length // 2))
        color = rng.choice(((151, 73, 46, 120), (202, 126, 54, 128), (114, 76, 42, 105)))
        draw.line((x - dx, y - dy, x + dx, y + dy), fill=color, width=2)


def draw_broom_impact_flash(draw: ImageDraw.ImageDraw, index: int) -> None:
    cycle = index / FRAMES
    sweep_x = 120 + int((0.5 - 0.5 * math.cos(cycle * math.tau)) * 720)
    pulse = abs(math.sin(cycle * math.tau * 4))
    if pulse < 0.28:
        return
    alpha = int(95 * pulse)
    draw.polygon(
        (
            (sweep_x - 95, 646),
            (sweep_x + 34, 594),
            (sweep_x + 132, 621),
            (sweep_x - 34, 679),
        ),
        fill=(255, 213, 129, alpha),
    )
    draw.arc(
        (sweep_x - 180, 548, sweep_x + 190, 722),
        202,
        333,
        fill=(255, 230, 159, min(170, alpha + 40)),
        width=4,
    )


def red_eye_glow(index: int) -> Image.Image:
    glow = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow, "RGBA")
    pulse = 0.62 + 0.38 * abs(math.sin(index * math.tau / 10))
    start, end, t, dx, dy = pose_state(index)
    points = []
    for eye_index in range(2):
        sx, sy = EYE_POINTS[start][eye_index]
        ex, ey = EYE_POINTS[end][eye_index]
        points.append((int(round(sx + (ex - sx) * t + dx)), int(round(sy + (ey - sy) * t + dy))))
    # Keyframes already contain eyes; this makes sweep mode read from a distance
    # in the monitor window while tracking the actor's changing pose.
    for x, y in points:
        for radius, alpha in ((34, 52), (20, 96), (8, 210)):
            adjusted = int(alpha * pulse)
            draw.ellipse(
                (x - radius, y - radius // 2, x + radius, y + radius // 2),
                fill=(255, 26, 26, adjusted),
            )
    blurred = glow.filter(ImageFilter.GaussianBlur(1.7))
    sharp = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    sharp_draw = ImageDraw.Draw(sharp, "RGBA")
    for x, y in points:
        sharp_draw.ellipse((x - 9, y - 4, x + 9, y + 4), fill=(255, 0, 0, 235))
        sharp_draw.rectangle((x - 3, y - 1, x + 3, y), fill=(255, 235, 220, int(80 * pulse)))
        sharp_draw.line((x - 10, y + 1, x + 10, y + 1), fill=(255, 0, 0, 255), width=4)
    return Image.alpha_composite(blurred, sharp)


def draw_red_vignette(draw: ImageDraw.ImageDraw, index: int) -> None:
    pulse = 0.42 + 0.30 * abs(math.sin(index * math.tau / 14))
    alpha = int(70 * pulse)
    draw.rectangle((0, 0, FRAME_W, 22), fill=(178, 43, 58, alpha))
    draw.rectangle((0, FRAME_H - 30, FRAME_W, FRAME_H), fill=(178, 43, 58, alpha))
    draw.rectangle((0, 0, 25, FRAME_H), fill=(178, 43, 58, alpha))
    draw.rectangle((FRAME_W - 25, 0, FRAME_W, FRAME_H), fill=(178, 43, 58, alpha))


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def save_pixel_png(image: Image.Image, path: Path) -> None:
    # Keep RGB output so tiny saturated details, especially the red eye slits,
    # are not collapsed into nearby browns by an adaptive palette.
    image.save(path, optimize=True, compress_level=6)


if __name__ == "__main__":
    main()
