from __future__ import annotations

from pathlib import Path

from v2_sprite_pipeline import (
    equal_grid_frames,
    export_frames,
    write_comparison,
    write_preview,
    write_sheet,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design_assets" / "scanner-v2-atlas-transparent.png"
SOURCE_DIR = ROOT / "design_assets" / "scanner_v2_keyframes"
OUTPUT = ROOT / "src" / "nhi_zues" / "web" / "assets" / "scanner-kabuki-v2-sheet.png"
OLD_SHEET = ROOT / "src" / "nhi_zues" / "web" / "assets" / "scanner-kabuki-sheet.png"
PREVIEW_DIR = ROOT / "design_assets" / "previews"
PREVIEW = PREVIEW_DIR / "scanner-v2.gif"
COMPARISON = PREVIEW_DIR / "scanner-comparison.gif"
FRAME_DURATIONS_MS = (450, 350, 400, 350, 400, 350, 450, 450)


def main() -> None:
    frames = equal_grid_frames(SOURCE, columns=4, rows=2, align_bottom=True)
    export_frames(frames, SOURCE_DIR)
    write_sheet(frames, OUTPUT)
    write_preview(frames, PREVIEW, durations_ms=FRAME_DURATIONS_MS)
    write_comparison(
        old_sheet=OLD_SHEET,
        old_frame_count=16,
        old_frame_ms=320,
        new_frames=frames,
        new_durations_ms=FRAME_DURATIONS_MS,
        output=COMPARISON,
        total_ms=6_400,
    )
    print(f"wrote {OUTPUT} ({len(frames)} frames)")
    print(f"wrote {PREVIEW}")
    print(f"wrote {COMPARISON}")


if __name__ == "__main__":
    main()
