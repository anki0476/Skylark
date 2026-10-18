from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from .datasets import load_dataset
from .schemas import Review


def export_reviewed(manifest: Path, reviews: list[Review]) -> bytes:
    dataset, images = load_dataset(manifest)
    if not reviews:
        raise ValueError("Export requires explicit whole-image reviews, including empty-image confirmation")
    samples = {s.id: s for s in dataset.samples}
    review_by_id = {r.sample_id: r for r in reviews}
    if len(review_by_id) != len(reviews) or review_by_id.keys() - samples.keys():
        raise ValueError("Reviews contain duplicate or unknown sample IDs")
    for review in reviews:
        sample = samples[review.sample_id]
        for box in review.objects:
            box.validate_frame(sample.width, sample.height, dataset.classes)
    buffer = io.BytesIO()
    provenance = []
    split_counts = {"train": 0, "val": 0}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in ("images/train/", "images/val/", "labels/train/", "labels/val/"):
            archive.writestr(folder, b"")
        for sample_id, review in sorted(review_by_id.items()):
            sample = samples[sample_id]
            split = "train" if sample.split == "development" else "val"
            split_counts[split] += 1
            lines = []
            for box in review.objects:
                x1, y1, x2, y2 = box.bbox
                lines.append(f"{dataset.classes.index(box.label)} "
                             f"{(x1 + x2) / (2 * sample.width):.8f} "
                             f"{(y1 + y2) / (2 * sample.height):.8f} "
                             f"{(x2 - x1) / sample.width:.8f} {(y2 - y1) / sample.height:.8f}")
            archive.writestr(f"images/{split}/{sample_id}.png", images[sample_id].png)
            archive.writestr(f"labels/{split}/{sample_id}.txt", "\n".join(lines) + ("\n" if lines else ""))
            provenance.append({"sample_id": sample_id, "scene_id": sample.scene_id,
                               "image_sha256": images[sample_id].sha256, "original_split": sample.split,
                               "review": review.model_dump()})
        # JSON-quoted values are valid YAML scalars and avoid YAML injection in class names.
        names = "\n".join(f"  {i}: {json.dumps(name)}" for i, name in enumerate(dataset.classes))
        # Omit path: '.' so a loader resolves paths from the YAML location, not its working directory.
        archive.writestr("data.yaml", "train: images/train\nval: images/val\nnames:\n" + names + "\n")
        archive.writestr("README.txt", "Skylark reviewed annotations\n\n"
                         "Load data.yaml by its absolute path after extracting this archive.\n"
                         "Only explicitly reviewed images are included. An empty split contains no\n"
                         "training/validation examples; review more images before using that split.\n"
                         "Development maps to train; the held-out test set maps to val for evaluation.\n"
                         "Do not train/tune against this val split and claim an unbiased held-out result.\n"
                         "See manifest.json for review provenance and original split identities.\n")
        archive.writestr("manifest.json", json.dumps({
            "version": 1, "dataset_kind": dataset.kind, "classes": dataset.classes,
            "convention": dataset.annotation_convention, "reviewed_images": len(reviews),
            "omitted_unreviewed_images": len(samples) - len(reviews), "samples": provenance,
            "exported_split_counts": split_counts,
            "notice": "Reviewed labels are human judgments, not guaranteed ground truth. "
                      "The original test split maps to val; do not tune on it and then call it held-out.",
        }, indent=2))
    return buffer.getvalue()
