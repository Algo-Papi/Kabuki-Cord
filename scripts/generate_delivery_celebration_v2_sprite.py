from __future__ import annotations

from pathlib import Path

from PIL import Image

from v2_sprite_pipeline import (
    align_frame_bottoms,
    common_alpha_crop,
    export_frames,
    fit_frame,
    write_comparison,
    write_preview,
    write_sheet,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design_assets" / "delivery-celebration-v2-atlas-transparent.png"
SOURCE_DIR = ROOT / "design_assets" / "delivery_celebration_v2_keyframes"
OUTPUT = ROOT / "src" / "nhi_zues" / "web" / "assets" / "monitor-arigato-v2-sheet.png"
OLD_SPRITE = ROOT / "src" / "nhi_zues" / "web" / "assets" / "monitor-arigato-sprite.png"
PREVIEW_DIR = ROOT / "design_assets" / "previews"
PREVIEW = PREVIEW_DIR / "delivery-celebration-v2.gif"
COMPARISON = PREVIEW_DIR / "delivery-celebration-comparison.gif"
FRAME_DURATIONS_MS = (260, 260, 300, 300, 300, 280, 320, 380)


def main() -> None:
    frames = build_frames()
    export_frames(frames, SOURCE_DIR)
    write_sheet(frames, OUTPUT)
    write_preview(frames, PREVIEW, durations_ms=FRAME_DURATIONS_MS)
    write_comparison(
        old_sheet=OLD_SPRITE,
        old_frame_count=1,
        old_frame_ms=sum(FRAME_DURATIONS_MS),
        new_frames=frames,
        new_durations_ms=FRAME_DURATIONS_MS,
        output=COMPARISON,
        total_ms=7_200,
    )
    print(f"wrote {OUTPUT} ({len(frames)} frames)")
    print(f"wrote {PREVIEW}")
    print(f"wrote {COMPARISON}")


def build_frames() -> list[Image.Image]:
    atlas = Image.open(SOURCE).convert("RGBA")
    if atlas.size != (1536, 1024):
        raise ValueError(f"Expected a 1536x1024 Delivery Celebration atlas, got {atlas.size}.")
    cells = [
        atlas.crop((column * 384, row * 512, (column + 1) * 384, (row + 1) * 512))
        for row in range(2)
        for column in range(4)
    ]
    # The chroma matte leaves a transparent-looking border trace below cell 3.
    # Clearing only that empty region prevents one bad alpha pixel from shrinking all frames.
    cells[2].paste((0, 0, 0, 0), (0, 420, 384, 512))
    cells = common_alpha_crop(cells, padding=12)
    frames = []
    for cell in cells:
        fitted = fit_frame(cell, frame_size=248)
        frame = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        frame.alpha_composite(fitted, (4, 4))
        frames.append(frame)
    return align_frame_bottoms(frames)


if __name__ == "__main__":
    main()
