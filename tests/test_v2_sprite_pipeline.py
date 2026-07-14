from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from v2_sprite_pipeline import equal_grid_frames  # noqa: E402


class V2SpritePipelineTests(unittest.TestCase):
    def test_output_padding_keeps_content_inside_the_frame(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            atlas_path = Path(directory) / "atlas.png"
            Image.new("RGBA", (512, 512), (180, 40, 40, 255)).save(atlas_path)

            [frame] = equal_grid_frames(
                atlas_path,
                columns=1,
                rows=1,
                output_padding=6,
            )

            self.assertEqual((256, 256), frame.size)
            self.assertEqual((6, 6, 250, 250), frame.getchannel("A").getbbox())

    def test_common_crop_preserves_scale_and_bottom_alignment_across_grid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            atlas_path = Path(directory) / "atlas.png"
            atlas = Image.new("RGBA", (320, 160), (0, 0, 0, 0))
            draw = ImageDraw.Draw(atlas)
            for index in range(8):
                column = index % 4
                row = index // 4
                left = column * 80 + 12
                top = row * 80 + (30 if row == 0 else 8) + index % 3
                draw.rectangle((left, top, left + 54, top + 38), fill=(180, 40, 40, 255))
            atlas.save(atlas_path)

            frames = equal_grid_frames(
                atlas_path,
                columns=4,
                rows=2,
                trim_transparent=True,
                trim_padding=4,
                align_bottom=True,
            )

            self.assertEqual(8, len(frames))
            self.assertTrue(all(frame.size == (256, 256) for frame in frames))
            boxes = [frame.getchannel("A").getbbox() for frame in frames]
            self.assertTrue(all(box is not None for box in boxes))
            self.assertEqual(1, len({box[3] for box in boxes if box is not None}))


if __name__ == "__main__":
    unittest.main()
