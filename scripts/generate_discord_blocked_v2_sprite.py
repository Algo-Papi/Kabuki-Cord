from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design_assets" / "discord-blocked-v2-atlas-transparent.png"
SOURCE_DIR = ROOT / "design_assets" / "discord_blocked_v2_keyframes"
OUTPUT = (
    ROOT
    / "src"
    / "nhi_zues"
    / "web"
    / "assets"
    / "scanner-kabuki-discord-blocked-v2-sheet.png"
)
OLD_SHEET = (
    ROOT
    / "src"
    / "nhi_zues"
    / "web"
    / "assets"
    / "scanner-kabuki-discord-blocked-sheet.png"
)
PREVIEW_DIR = ROOT / "design_assets" / "previews"
PREVIEW = PREVIEW_DIR / "discord-blocked-v2.gif"
COMPARISON = PREVIEW_DIR / "discord-blocked-comparison.gif"
FRAME = 256

# The generated atlas is a 4x2 layout with narrow white separator lines. These
# rectangles intentionally exclude those separators before alpha-frame export.
CELL_RECTS = (
    (0, 0, 442, 442),
    (445, 0, 885, 442),
    (889, 0, 1328, 442),
    (1332, 0, 1774, 442),
    (0, 445, 442, 887),
    (445, 445, 885, 887),
    (889, 445, 1328, 887),
    (1332, 445, 1774, 887),
)
FRAME_DURATIONS_MS = (550, 450, 450, 350, 250, 400, 650, 500)


def _fit_frame(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    alpha = image.getchannel("A").point(lambda value: 0 if value < 16 else value)
    image.putalpha(alpha)
    image.thumbnail((FRAME, FRAME), Image.Resampling.LANCZOS)
    alpha = image.getchannel("A").point(lambda value: 0 if value < 16 else value)
    image.putalpha(alpha)
    canvas = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((FRAME - image.width) // 2, (FRAME - image.height) // 2))
    return canvas


def _export_frames() -> list[Image.Image]:
    atlas = Image.open(SOURCE).convert("RGBA")
    if atlas.size != (1774, 887):
        raise SystemExit(f"Expected a 1774x887 V2 atlas, found {atlas.size}")
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    frames = [_fit_frame(atlas.crop(rect)) for rect in CELL_RECTS]
    for index, frame in enumerate(frames):
        frame.save(SOURCE_DIR / f"frame_{index:03d}.png", optimize=True)
    return frames


def _write_sheet(frames: list[Image.Image]) -> None:
    sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * FRAME, 0))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUTPUT, optimize=True)


def _preview_frame(frame: Image.Image, *, size: int = 256) -> Image.Image:
    backdrop = Image.new("RGBA", (size, size), (16, 22, 28, 255))
    actor = frame.resize((size, size), Image.Resampling.LANCZOS)
    backdrop.alpha_composite(actor)
    return backdrop.convert("RGB")


def _write_preview(frames: list[Image.Image]) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    preview_frames = [_preview_frame(frame) for frame in frames]
    preview_frames[0].save(
        PREVIEW,
        save_all=True,
        append_images=preview_frames[1:],
        duration=list(FRAME_DURATIONS_MS),
        loop=0,
        optimize=True,
        disposal=2,
    )


def _write_comparison(frames: list[Image.Image]) -> None:
    if not OLD_SHEET.exists():
        return
    old_sheet = Image.open(OLD_SHEET).convert("RGBA")
    old_frames = [old_sheet.crop((index * FRAME, 0, (index + 1) * FRAME, FRAME)) for index in range(10)]
    total_ms = 7_200
    tick_ms = 100
    v2_total = sum(FRAME_DURATIONS_MS)
    v2_edges: list[int] = []
    elapsed = 0
    for duration in FRAME_DURATIONS_MS:
        elapsed += duration
        v2_edges.append(elapsed)

    comparison_frames: list[Image.Image] = []
    for timestamp in range(0, total_ms, tick_ms):
        old_index = min(timestamp // 720, len(old_frames) - 1)
        v2_time = timestamp % v2_total
        v2_index = next(index for index, edge in enumerate(v2_edges) if v2_time < edge)
        canvas = Image.new("RGBA", (552, 300), (11, 16, 21, 255))
        canvas.alpha_composite(old_frames[old_index], (12, 32))
        canvas.alpha_composite(frames[v2_index], (284, 32))
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 10), "CURRENT", fill=(137, 151, 165, 255))
        draw.text((284, 10), "V2 TEST", fill=(69, 214, 202, 255))
        comparison_frames.append(canvas.convert("RGB"))
    comparison_frames[0].save(
        COMPARISON,
        save_all=True,
        append_images=comparison_frames[1:],
        duration=tick_ms,
        loop=0,
        optimize=True,
        disposal=2,
    )


def main() -> None:
    frames = _export_frames()
    _write_sheet(frames)
    _write_preview(frames)
    _write_comparison(frames)
    print(f"wrote {OUTPUT} ({len(frames)} frames)")
    print(f"wrote {PREVIEW}")
    print(f"wrote {COMPARISON}")


if __name__ == "__main__":
    main()
