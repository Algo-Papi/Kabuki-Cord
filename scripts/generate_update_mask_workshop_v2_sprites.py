from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from v2_sprite_pipeline import equal_grid_frames, export_frames, write_preview, write_sheet


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "design_assets"
WEB_ASSETS = ROOT / "src" / "nhi_zues" / "web" / "assets"
PREVIEWS = ASSETS / "previews"


@dataclass(frozen=True)
class Animation:
    name: str
    frame_ms: int

    @property
    def source(self) -> Path:
        return ASSETS / f"update-mask-workshop-{self.name}-v2-atlas-transparent.png"

    @property
    def keyframes(self) -> Path:
        return ASSETS / f"update_mask_workshop_{self.name}_v2_keyframes"

    @property
    def sheet(self) -> Path:
        return WEB_ASSETS / f"update-mask-workshop-{self.name}-v2-sheet.png"

    @property
    def preview(self) -> Path:
        return PREVIEWS / f"update-mask-workshop-{self.name}-v2.gif"


ANIMATIONS = (
    Animation("checking", 400),
    Animation("updated", 244),
    Animation("current", 262),
)


def main() -> None:
    for animation in ANIMATIONS:
        frames = equal_grid_frames(
            animation.source,
            columns=4,
            rows=2,
            trim_transparent=True,
            trim_padding=12,
            align_bottom=True,
            output_padding=6,
        )
        export_frames(frames, animation.keyframes)
        write_sheet(frames, animation.sheet)
        write_preview(
            frames,
            animation.preview,
            durations_ms=(animation.frame_ms,) * len(frames),
        )
        print(f"wrote {animation.sheet} ({len(frames)} frames)")
        print(f"wrote {animation.preview}")


if __name__ == "__main__":
    main()
