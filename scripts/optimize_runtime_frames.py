from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "src" / "nhi_zues" / "web" / "assets"
GROUPS = {
    "monitor_spy_frames": ((800, 600), 84),
    "monitor_dojo_sweep_frames": ((640, 480), 80),
}


def main() -> None:
    for directory, (size, quality) in GROUPS.items():
        for source in sorted((ASSET_ROOT / directory).glob("frame_*.png")):
            optimize(source, source.with_suffix(".webp"), size=size, quality=quality)
    paused = ASSET_ROOT / "monitor-paused-lounge.png"
    if paused.exists():
        optimize(
            paused,
            ASSET_ROOT / "monitor-paused-lounge.webp",
            size=(800, 600),
            quality=84,
        )


def optimize(source: Path, target: Path, *, size: tuple[int, int], quality: int) -> None:
    with Image.open(source) as image:
        converted = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        converted.save(target, "WEBP", quality=quality, method=6)
    print(f"{source.name} -> {target.name} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
