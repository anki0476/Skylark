"""Shared data contracts. Coordinates refer to EXIF-upright images, in pixels."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Box(Contract):
    label: str = Field(min_length=1, max_length=80)
    bbox: tuple[float, float, float, float]

    @field_validator("bbox", mode="before")
    @classmethod
    def numeric_coordinates(cls, value):
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            raise ValueError("bbox must contain four numeric pixel coordinates")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
            raise ValueError("bbox coordinates must be numbers, not strings or booleans")
        return value

    @model_validator(mode="after")
    def positive_area(self):
        x1, y1, x2, y2 = self.bbox
        if not all(math.isfinite(v) for v in self.bbox):
            raise ValueError("bbox coordinates must be finite")
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
            raise ValueError("bbox must have nonnegative origin and positive area")
        return self

    def validate_frame(self, width: int, height: int, classes: list[str]) -> None:
        if self.label not in classes:
            raise ValueError(f"Unknown class: {self.label}")
        if self.bbox[2] > width or self.bbox[3] > height:
            raise ValueError("Box is outside the image; it will not be silently clamped")


class Prediction(Contract):
    objects: list[Box] = Field(max_length=200)


class Sample(Contract):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    image: str = Field(min_length=1, max_length=300)
    scene_id: str = Field(min_length=1, max_length=100)
    split: Literal["development", "test"]
    condition: Literal["clean", "shadows", "clutter", "occlusion"]
    width: int = Field(gt=0, le=10000)
    height: int = Field(gt=0, le=10000)
    ground_truth_verified: Literal[True]
    objects: list[Box] = Field(max_length=200)


class Dataset(Contract):
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["real_photographs", "synthetic_fixture"]
    annotation_convention: Literal["upright_visible_extent_xyxy"] = "upright_visible_extent_xyxy"
    classes: list[str] = Field(min_length=1, max_length=20)
    samples: list[Sample] = Field(min_length=1, max_length=1000)

    @field_validator("classes")
    @classmethod
    def unique_classes(cls, value):
        if any(not c.strip() or c != c.strip() or len(c) > 80 for c in value):
            raise ValueError("Classes must be trimmed, nonempty strings of up to 80 characters")
        if len(set(value)) != len(value):
            raise ValueError("Classes must be unique")
        return value

    @model_validator(mode="after")
    def consistent_samples(self):
        ids: set[str] = set()
        scenes: dict[str, str] = {}
        for sample in self.samples:
            if sample.id in ids:
                raise ValueError("Sample IDs must be unique")
            ids.add(sample.id)
            if sample.scene_id in scenes and scenes[sample.scene_id] != sample.split:
                raise ValueError("A scene cannot appear in both development and test splits")
            scenes[sample.scene_id] = sample.split
            for box in sample.objects:
                box.validate_frame(sample.width, sample.height, self.classes)
        return self


class ModelSettings(Contract):
    model: str = Field(min_length=1, max_length=200)
    public_endpoint_confirmed: Literal[True]
    image_input_confirmed: Literal[True]
    input_usd_per_million: float = Field(gt=0, le=1000)
    output_usd_per_million: float = Field(gt=0, le=1000)
    pricing_source: str = Field(min_length=8, max_length=1000)
    response_format: Literal["json_schema", "json_object", "prompt_only"] = "json_object"
    max_output_tokens: int = Field(default=2048, ge=128, le=8192)
    estimated_input_tokens: int = Field(default=16000, ge=1024, le=1000000)
    image_long_edge: int = Field(default=1280, ge=256, le=2048)

    def estimated_attempt_usd(self) -> float:
        return (self.estimated_input_tokens * self.input_usd_per_million
                + self.max_output_tokens * self.output_usd_per_million) / 1_000_000


class ExperimentConfig(Contract):
    credits_and_expiry_checked: Literal[True]
    automatic_topups_disabled: Literal[True]
    confirmed_credit_balance_usd: float = Field(gt=0)
    experiment_limit_usd: float = Field(default=2.0, gt=0, le=2.0)
    models: list[ModelSettings] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def budget_and_candidates(self):
        if self.experiment_limit_usd > self.confirmed_credit_balance_usd:
            raise ValueError("Experiment allowance exceeds the confirmed credit balance")
        if len({m.model for m in self.models}) != len(self.models):
            raise ValueError("Choose distinct model candidates")
        return self


class Review(Contract):
    """An explicit whole-image review, including missing/empty object confirmation."""

    sample_id: str
    objects: list[Box]
    reviewed: Literal[True]
    all_objects_checked: Literal[True]
    reviewer: str = Field(min_length=1, max_length=100)
    source: Literal["manual", "assisted"]
    elapsed_seconds: float = Field(gt=0)
    inference_model: str | None = None
    prediction_run_id: str | None = None

    @model_validator(mode="after")
    def assisted_provenance(self):
        if self.source == "assisted" and (not self.inference_model or not self.prediction_run_id):
            raise ValueError("Assisted reviews must record the inference model and prediction run ID")
        return self

