from __future__ import annotations

from itertools import accumulate
from pathlib import Path

from PIL import Image, ImageDraw


def equal_grid_frames(
    source: Path,
    *,
    columns: int,
    rows: int,
    frame_size: int = 256,
    trim_transparent: bool = False,
    trim_padding: int = 10,
    align_bottom: bool = False,
    cell_inset: int = 0,
    output_padding: int = 0,
) -> list[Image.Image]:
    atlas = Image.open(source).convert("RGBA")
    x_edges = [round(index * atlas.width / columns) for index in range(columns + 1)]
    y_edges = [round(index * atlas.height / rows) for index in range(rows + 1)]
    inset = max(0, int(cell_inset))
    cells = [
        atlas.crop(
            (
                x_edges[column] + inset,
                y_edges[row] + inset,
                x_edges[column + 1] - inset,
                y_edges[row + 1] - inset,
            )
        )
        for row in range(rows)
        for column in range(columns)
    ]
    if trim_transparent:
        cells = common_alpha_crop(cells, padding=trim_padding)
    padding = max(0, int(output_padding))
    inner_size = frame_size - padding * 2
    if inner_size <= 0:
        raise ValueError("Output padding must leave room for visible frame content.")
    frames = [fit_frame(cell, frame_size=inner_size) for cell in cells]
    if padding:
        padded_frames = []
        for frame in frames:
            canvas = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))
            canvas.alpha_composite(frame, (padding, padding))
            padded_frames.append(canvas)
        frames = padded_frames
    return align_frame_bottoms(frames) if align_bottom else frames


def align_frame_bottoms(images: list[Image.Image]) -> list[Image.Image]:
    boxes = [image.getchannel("A").getbbox() for image in images]
    target_bottom = max((box[3] for box in boxes if box is not None), default=0)
    aligned = []
    for image, box in zip(images, boxes, strict=True):
        if box is None or box[3] == target_bottom:
            aligned.append(image)
            continue
        canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
        canvas.alpha_composite(image, (0, target_bottom - box[3]))
        aligned.append(canvas)
    return aligned


def common_alpha_crop(images: list[Image.Image], *, padding: int = 10) -> list[Image.Image]:
    if not images:
        return []
    boxes = [image.getchannel("A").getbbox() for image in images]
    boxes = [box for box in boxes if box is not None]
    if not boxes:
        return images
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)
    width = right - left
    height = bottom - top
    side = max(width, height) + max(0, padding) * 2
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    square = (
        round(center_x - side / 2),
        round(center_y - side / 2),
        round(center_x + side / 2),
        round(center_y + side / 2),
    )
    return [_crop_with_transparent_padding(image, square) for image in images]


def _crop_with_transparent_padding(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> Image.Image:
    left, top, right, bottom = box
    output = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    source_box = (
        max(0, left),
        max(0, top),
        min(image.width, right),
        min(image.height, bottom),
    )
    if source_box[0] >= source_box[2] or source_box[1] >= source_box[3]:
        return output
    output.alpha_composite(
        image.crop(source_box),
        (source_box[0] - left, source_box[1] - top),
    )
    return output


def fit_frame(image: Image.Image, *, frame_size: int = 256) -> Image.Image:
    image = image.convert("RGBA")
    image.putalpha(image.getchannel("A").point(lambda value: 0 if value < 16 else value))
    image.thumbnail((frame_size, frame_size), Image.Resampling.LANCZOS)
    image.putalpha(image.getchannel("A").point(lambda value: 0 if value < 16 else value))
    canvas = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))
    canvas.alpha_composite(
        image,
        ((frame_size - image.width) // 2, (frame_size - image.height) // 2),
    )
    return canvas


def export_frames(frames: list[Image.Image], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, frame in enumerate(frames):
        frame.save(output_dir / f"frame_{index:03d}.png", optimize=True)


def write_sheet(frames: list[Image.Image], output: Path) -> None:
    if not frames:
        raise ValueError("Cannot build an empty sprite sheet.")
    frame_width, frame_height = frames[0].size
    sheet = Image.new("RGBA", (frame_width * len(frames), frame_height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * frame_width, 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, optimize=True)


def write_preview(
    frames: list[Image.Image],
    output: Path,
    *,
    durations_ms: tuple[int, ...],
    background: tuple[int, int, int, int] = (16, 22, 28, 255),
) -> None:
    if len(frames) != len(durations_ms):
        raise ValueError("Preview durations must match the number of frames.")
    output.parent.mkdir(parents=True, exist_ok=True)
    previews = []
    for frame in frames:
        canvas = Image.new("RGBA", frame.size, background)
        canvas.alpha_composite(frame)
        previews.append(canvas.convert("RGB"))
    previews[0].save(
        output,
        save_all=True,
        append_images=previews[1:],
        duration=list(durations_ms),
        loop=0,
        optimize=True,
        disposal=2,
    )


def write_comparison(
    *,
    old_sheet: Path,
    old_frame_count: int,
    old_frame_ms: int,
    new_frames: list[Image.Image],
    new_durations_ms: tuple[int, ...],
    output: Path,
    total_ms: int,
    tick_ms: int = 100,
) -> None:
    old = Image.open(old_sheet).convert("RGBA")
    old_frame_width = old.width // old_frame_count
    old_frames = [
        fit_frame(
            old.crop((index * old_frame_width, 0, (index + 1) * old_frame_width, old.height))
        )
        for index in range(old_frame_count)
    ]
    new_edges = list(accumulate(new_durations_ms))
    new_total_ms = sum(new_durations_ms)
    comparison_frames = []
    for timestamp in range(0, total_ms, tick_ms):
        old_index = (timestamp // old_frame_ms) % old_frame_count
        new_time = timestamp % new_total_ms
        new_index = next(index for index, edge in enumerate(new_edges) if new_time < edge)
        canvas = Image.new("RGBA", (552, 300), (11, 16, 21, 255))
        canvas.alpha_composite(old_frames[old_index], (12, 32))
        canvas.alpha_composite(new_frames[new_index], (284, 32))
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 10), "CURRENT", fill=(137, 151, 165, 255))
        draw.text((284, 10), "V2 TEST", fill=(69, 214, 202, 255))
        comparison_frames.append(canvas.convert("RGB"))
    output.parent.mkdir(parents=True, exist_ok=True)
    comparison_frames[0].save(
        output,
        save_all=True,
        append_images=comparison_frames[1:],
        duration=tick_ms,
        loop=0,
        optimize=True,
        disposal=2,
    )
