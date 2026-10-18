"""Decode once, normalize orientation, and keep an explicit coordinate transform."""

from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .schemas import Box

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000


@dataclass(frozen=True)
class PreparedImage:
    png: bytes
    width: int
    height: int
    sha256: str


def prepare_image(content: bytes) -> PreparedImage:
    if not content or len(content) > MAX_BYTES:
        raise ValueError("Image must be nonempty and no larger than 20 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise ValueError("Only JPEG and PNG images are supported")
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("Image exceeds the 40-megapixel limit")
                image.load()
                upright = ImageOps.exif_transpose(image).convert("RGB")
                output = io.BytesIO()
                # A fresh RGB image has no EXIF or source metadata in the saved PNG.
                clean = Image.new("RGB", upright.size)
                clean.paste(upright)
                clean.save(output, format="PNG")
                png = output.getvalue()
                return PreparedImage(png, clean.width, clean.height, hashlib.sha256(png).hexdigest())
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("Invalid, truncated, or excessively large image") from exc


def inference_image(image: PreparedImage, long_edge: int) -> PreparedImage:
    with Image.open(io.BytesIO(image.png)) as original:
        original.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        original.save(output, format="PNG")
        content = output.getvalue()
        return PreparedImage(content, original.width, original.height, hashlib.sha256(content).hexdigest())


def restore_boxes(boxes: list[Box], sent: PreparedImage, original: PreparedImage,
                  classes: list[str]) -> list[Box]:
    restored = []
    for box in boxes:
        box.validate_frame(sent.width, sent.height, classes)
        x1, y1, x2, y2 = box.bbox
        restored.append(Box(label=box.label, bbox=(
            x1 / sent.width * original.width, y1 / sent.height * original.height,
            x2 / sent.width * original.width, y2 / sent.height * original.height,
        )))
    return restored


def contained_image(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if Path(relative).is_absolute() or not candidate.is_relative_to(root.resolve()):
        raise ValueError("Dataset image paths must stay inside the dataset directory")
    if not candidate.is_file():
        raise ValueError(f"Missing dataset image: {relative}")
    return candidate

