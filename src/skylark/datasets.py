from __future__ import annotations

from pathlib import Path

from .imaging import PreparedImage, contained_image, prepare_image
from .schemas import Dataset


def load_dataset(manifest_path: Path) -> tuple[Dataset, dict[str, PreparedImage]]:
    dataset = Dataset.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    images: dict[str, PreparedImage] = {}
    hashes: dict[str, str] = {}
    for sample in dataset.samples:
        path = contained_image(manifest_path.parent, sample.image)
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError(f"Image too large: {sample.id}")
        image = prepare_image(path.read_bytes())
        if (image.width, image.height) != (sample.width, sample.height):
            raise ValueError(f"{sample.id}: dimensions must match the EXIF-upright image")
        if image.sha256 in hashes:
            raise ValueError(f"Duplicate image content: {sample.id} and {hashes[image.sha256]}")
        hashes[image.sha256] = sample.id
        images[sample.id] = image
    return dataset, images

