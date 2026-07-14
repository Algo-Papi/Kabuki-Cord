from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "design_assets" / "dojo-sweep-v2-atlas-transparent.png"
BACKGROUND = ROOT / "design_assets" / "dojo-sweep-v2-background.png"
SOURCE_DIR = ROOT / "design_assets" / "dojo_sweep_v2_keyframes"
OUTPUT_DIR = ROOT / "src" / "nhi_zues" / "web" / "assets" / "monitor_dojo_sweep_v2_frames"
PREVIEW_DIR = ROOT / "design_assets" / "previews"
OLD_DIR = ROOT / "src" / "nhi_zues" / "web" / "assets" / "monitor_dojo_sweep_frames"

FRAME_SIZE = (640, 480)
FRAME_COUNT = 8
FRAME_MS = 300
ACTOR_SIZE = (576, 432)
ACTOR_X = 0
ACTOR_Y_OFFSETS = (0, 3, 50, 38, 102, 98, 98, 0)
SOURCE_CELL_SEQUENCE = (0, 1, 2, 3, 4, 5, 5, 0)
OLD_FRAME_COUNT = 48
OLD_FRAME_MS = 95


def main() -> None:
    background = Image.open(BACKGROUND).convert("RGB").resize(FRAME_SIZE, Image.Resampling.LANCZOS)
    source_cells = read_atlas_cells()
    source_cells[4] = clear_lower_bleed(source_cells[4])
    source_cells[5] = clear_lower_bleed(source_cells[5])

    actor_frames: list[Image.Image] = []
    final_frames: list[Image.Image] = []
    for index, source_index in enumerate(SOURCE_CELL_SEQUENCE):
        actor = source_cells[source_index].copy()
        if index == 6:
            paste_evidence_slip(actor, source_cells[6])
        actor_layer = place_actor(actor, y_offset=ACTOR_Y_OFFSETS[index])
        actor_frames.append(actor_layer)
        scene = background.convert("RGBA")
        scene.alpha_composite(actor_layer)
        final_frames.append(scene.convert("RGB"))

    write_source_frames(actor_frames)
    write_runtime_frames(final_frames)
    write_manifest()
    write_preview(final_frames)
    write_comparison(final_frames)
    print(f"wrote {FRAME_COUNT} Dojo Sweep V2 frames to {OUTPUT_DIR}")
    print(f"wrote {PREVIEW_DIR / 'dojo-sweep-v2.gif'}")
    print(f"wrote {PREVIEW_DIR / 'dojo-sweep-comparison.gif'}")


def read_atlas_cells() -> list[Image.Image]:
    atlas = Image.open(ATLAS).convert("RGBA")
    if atlas.size != (1024, 1536):
        raise ValueError(f"Expected a 1024x1536 Dojo Sweep atlas, got {atlas.size}.")
    return [
        atlas.crop((column * 512, row * 384, (column + 1) * 512, (row + 1) * 384))
        for row in range(4)
        for column in range(2)
    ]


def clear_lower_bleed(cell: Image.Image) -> Image.Image:
    cleaned = cell.copy()
    cleaned.paste((0, 0, 0, 0), (0, 330, cleaned.width, cleaned.height))
    return cleaned


def paste_evidence_slip(cell: Image.Image, source: Image.Image) -> None:
    evidence = source.crop((150, 230, 245, 305))
    cell.alpha_composite(evidence, (312, 225))


def place_actor(actor: Image.Image, *, y_offset: int) -> Image.Image:
    actor = actor.resize(ACTOR_SIZE, Image.Resampling.LANCZOS)
    actor.putalpha(actor.getchannel("A").point(lambda value: 0 if value < 14 else value))
    layer = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    layer.alpha_composite(actor, (ACTOR_X, y_offset))
    return layer


def write_source_frames(frames: list[Image.Image]) -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for old in SOURCE_DIR.glob("frame_*.png"):
        old.unlink()
    for index, frame in enumerate(frames):
        frame.save(SOURCE_DIR / f"frame_{index:03d}.png", optimize=True)


def write_runtime_frames(frames: list[Image.Image]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT_DIR.glob("frame_*.webp"):
        old.unlink()
    for index, frame in enumerate(frames):
        frame.save(OUTPUT_DIR / f"frame_{index:03d}.webp", "WEBP", quality=88, method=6)


def write_manifest() -> None:
    manifest = {
        "frame_count": FRAME_COUNT,
        "frame_ms": FRAME_MS,
        "width": FRAME_SIZE[0],
        "height": FRAME_SIZE[1],
        "extension": "webp",
        "timing": "looped-while-sweep-target-active",
        "animation": "eight-pose-fixed-camera-evidence-sweep",
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_preview(frames: list[Image.Image]) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    preview_frames = [frame.resize((480, 360), Image.Resampling.LANCZOS) for frame in frames]
    preview_frames[0].save(
        PREVIEW_DIR / "dojo-sweep-v2.gif",
        save_all=True,
        append_images=preview_frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )


def write_comparison(new_frames: list[Image.Image]) -> None:
    old_frames = [
        Image.open(OLD_DIR / f"frame_{index:03d}.webp").convert("RGB")
        for index in range(OLD_FRAME_COUNT)
    ]
    tick_ms = 100
    total_ms = 6_000
    comparison_frames: list[Image.Image] = []
    for timestamp in range(0, total_ms, tick_ms):
        old = old_frames[(timestamp // OLD_FRAME_MS) % OLD_FRAME_COUNT].resize(
            (320, 240), Image.Resampling.LANCZOS
        )
        new = new_frames[(timestamp // FRAME_MS) % FRAME_COUNT].resize(
            (320, 240), Image.Resampling.LANCZOS
        )
        canvas = Image.new("RGB", (676, 278), (9, 13, 18))
        canvas.paste(old, (12, 26))
        canvas.paste(new, (344, 26))
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 7), "CURRENT - 48 GHOSTED FRAMES", fill=(137, 151, 165))
        draw.text((344, 7), "V2 - 8 LOCKED FRAMES", fill=(69, 214, 202))
        comparison_frames.append(canvas)
    comparison_frames[0].save(
        PREVIEW_DIR / "dojo-sweep-comparison.gif",
        save_all=True,
        append_images=comparison_frames[1:],
        duration=tick_ms,
        loop=0,
        optimize=True,
        disposal=2,
    )


if __name__ == "__main__":
    main()
