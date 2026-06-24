from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "web" / "assets" / "source" / "latest_keyframes"
OUTPUT = ROOT / "web" / "assets" / "scanner-kabuki-latest-sheet.png"
FRAME = 256
FRAMES = 10


def main() -> None:
    frames = [
        Image.open(path).convert("RGBA").resize((FRAME, FRAME), Image.Resampling.LANCZOS)
        for path in sorted(SOURCE_DIR.glob("frame_*.png"))
    ]
    if not frames:
        raise SystemExit(f"No source frames found in {SOURCE_DIR}")
    if len(frames) != FRAMES:
        raise SystemExit(f"Expected {FRAMES} source frames in {SOURCE_DIR}, found {len(frames)}")

    sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * FRAME, 0))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUTPUT)
    print(f"wrote {OUTPUT} ({len(frames)} frames)")


if __name__ == "__main__":
    main()
