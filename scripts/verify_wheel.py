from __future__ import annotations

import sys
import zipfile
import argparse
from pathlib import Path


EXPECTED_SUFFIXES = {
    "nhi_zues/assets/app.ico",
    "nhi_zues/defaults/servers.example.json",
    "nhi_zues/defaults/character_cards/default.json",
    "nhi_zues/web/index.html",
    "nhi_zues/web/app.js",
    "nhi_zues/web/icons.css",
    "nhi_zues/web/monitor.html",
    "nhi_zues/web/assets/app-icon-32.png",
    "nhi_zues/web/assets/monitor_spy_frames/manifest.json",
    "nhi_zues/web/assets/monitor_spy_frames/frame_000.webp",
    "nhi_zues/web/assets/monitor_spy_v2_frames/frame_007.webp",
    "nhi_zues/web/assets/monitor_dojo_sweep_frames/frame_047.webp",
    "nhi_zues/web/assets/monitor_dojo_sweep_v2_frames/frame_007.webp",
    "nhi_zues/web/assets/mode-kabuki-dry-v2-sheet.png",
    "nhi_zues/web/assets/mode-kabuki-semi-auto-v2-sheet.png",
    "nhi_zues/web/assets/mode-kabuki-full-auto-v2-sheet.png",
    "nhi_zues/web/assets/mode-kabuki-live-fire-v2-sheet.png",
    "nhi_zues/web/assets/monitor-arigato-v2-sheet.png",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify packaged Kabuki-Cord runtime resources.")
    parser.add_argument("wheel", nargs="?", type=Path)
    args = parser.parse_args()
    wheels = [args.wheel] if args.wheel else sorted(Path("dist").glob("kabuki_cord-*.whl"))
    if not wheels:
        print("No Kabuki-Cord wheel found in dist/.", file=sys.stderr)
        return 1
    wheel = wheels[-1]
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    missing = sorted(EXPECTED_SUFFIXES - names)
    forbidden = sorted(name for name in names if "design_assets/" in name or "/source/" in name)
    if missing:
        print(f"Wheel is missing runtime resources: {missing}", file=sys.stderr)
        return 1
    if forbidden:
        print(f"Wheel contains source-only design assets: {forbidden[:5]}", file=sys.stderr)
        return 1
    print(f"Verified {wheel.name}: {len(names)} files, {wheel.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
