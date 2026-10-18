"""Small geometric test fixture. It is never presented as photographs or model evidence."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from .provider import Completion
from .schemas import Dataset, ExperimentConfig


def create_fixture(directory: Path) -> Path:
    if directory.exists():
        raise ValueError("Choose a new fixture directory; existing data will not be overwritten")
    directory.mkdir(parents=True)
    samples = []
    for i, condition in enumerate(["clean", "shadows", "clutter", "occlusion"]):
        image = Image.new("RGB", (640, 400), (235 - i * 12, 235 - i * 8, 230))
        draw = ImageDraw.Draw(image)
        draw.text((16, 12), "SYNTHETIC SOFTWARE TEST FIXTURE - NOT MODEL EVIDENCE", fill="#333333")
        draw.ellipse((50, 170, 150, 270), fill="#cb4c3e")
        draw.rectangle((250, 140, 360, 270), fill="#4f8fbd")
        draw.rectangle((470, 100, 530, 290), fill="#45826c")
        image.save(directory / f"fixture-{i}.png")
        samples.append({"id": f"fixture-{i}", "image": f"fixture-{i}.png", "scene_id": f"fixture-scene-{i}",
                        "split": "development", "condition": condition, "width": 640, "height": 400,
                        "ground_truth_verified": True, "objects": [
                            {"label": "apple", "bbox": [50, 170, 150, 270]},
                            {"label": "cup", "bbox": [250, 140, 360, 270]},
                            {"label": "bottle", "bbox": [470, 100, 530, 290]},
                        ]})
    dataset = Dataset.model_validate({"version": 1, "name": "Illustrative software fixture",
                                      "kind": "synthetic_fixture", "classes": ["apple", "cup", "bottle"],
                                      "samples": samples})
    manifest = directory / "manifest.json"
    manifest.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def fixture_config() -> ExperimentConfig:
    return ExperimentConfig.model_validate({
        "credits_and_expiry_checked": True, "automatic_topups_disabled": True,
        "confirmed_credit_balance_usd": 2, "experiment_limit_usd": 2,
        "models": [{"model": "fixture/illustrative-proposals", "public_endpoint_confirmed": True,
                    "image_input_confirmed": True, "input_usd_per_million": .1,
                    "output_usd_per_million": .3, "pricing_source": "fixture-only, not a price quote"}]})


class FixtureProvider:
    def discover(self):
        return [{"id": "fixture/illustrative-proposals"}]

    def label(self, image, classes, task, settings):
        # Deliberately omit the cup. This fixture checks that recall isn't inflated.
        return Completion(json.dumps({"objects": [
            {"label": "apple", "bbox": [50, 170, 150, 270]},
            {"label": "bottle", "bbox": [470, 100, 530, 290]},
        ]}), 0, 0, 0.)

