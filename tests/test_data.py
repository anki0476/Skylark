import io
import json
import zipfile

import pytest
from PIL import Image
from pydantic import ValidationError

from skylark.datasets import load_dataset
from skylark.exporting import export_reviewed
from skylark.imaging import inference_image, prepare_image, restore_boxes
from skylark.metrics import evaluate, match_boxes, timing_report
from skylark.schemas import Box, Dataset, Review


def test_exif_rotation_and_resizing():
    image = Image.new("RGB", (120, 60), "red")
    exif = Image.Exif()
    exif[274] = 6
    data = io.BytesIO()
    image.save(data, format="JPEG", exif=exif)
    upright = prepare_image(data.getvalue())
    assert (upright.width, upright.height) == (60, 120)
    sent = inference_image(upright, 60)
    assert (sent.width, sent.height) == (30, 60)
    boxes = restore_boxes([Box(label="apple", bbox=[0, 0, 30, 60])], sent, upright, ["apple"])
    assert boxes[0].bbox == (0, 0, 60, 120)
    assert prepare_image(upright.png).sha256 == upright.sha256


@pytest.mark.parametrize("bbox", [[0, 0, 0, 4], [-1, 0, 2, 2], [0, 0, float("nan"), 2],
                                  [0, 0, float("inf"), 2], [False, 0, 2, 2], ["0", 0, 2, 2]])
def test_invalid_coordinates_rejected(bbox):
    with pytest.raises(ValidationError):
        Box(label="apple", bbox=bbox)


def test_outside_or_unknown_class_rejected():
    with pytest.raises(ValueError, match="outside"):
        Box(label="apple", bbox=[0, 0, 50, 50]).validate_frame(49, 50, ["apple"])
    with pytest.raises(ValueError, match="Unknown"):
        Box(label="banana", bbox=[0, 0, 1, 1]).validate_frame(10, 10, ["apple"])


@pytest.mark.parametrize("data", [b"", b"not an image", b"a" * (20 * 1024 * 1024 + 1)],
                         ids=["empty", "invalid", "oversized"])
def test_bad_images_rejected(data):
    with pytest.raises(ValueError):
        prepare_image(data)


def test_gif_not_accepted():
    data = io.BytesIO()
    Image.new("RGB", (10, 10)).save(data, "GIF")
    with pytest.raises(ValueError, match="JPEG"):
        prepare_image(data.getvalue())


def change_manifest(manifest, mutate):
    data = json.loads(manifest.read_text())
    mutate(data)
    manifest.write_text(json.dumps(data))


def test_scene_split_leakage(manifest):
    change_manifest(manifest, lambda d: d["samples"][1].update(
        scene_id=d["samples"][0]["scene_id"], split="test"))
    with pytest.raises(ValueError, match="both development"):
        load_dataset(manifest)


def test_duplicate_content_not_counted_twice(manifest):
    (manifest.parent / "fixture-1.png").write_bytes((manifest.parent / "fixture-0.png").read_bytes())
    with pytest.raises(ValueError, match="Duplicate image"):
        load_dataset(manifest)


def test_path_escape_rejected(manifest):
    change_manifest(manifest, lambda d: d["samples"][0].update(image="../private.png"))
    with pytest.raises(ValueError, match="stay inside"):
        load_dataset(manifest)


def test_wrong_dimensions_rejected(manifest):
    change_manifest(manifest, lambda d: d["samples"][0].update(width=641))
    with pytest.raises(ValueError, match="dimensions"):
        load_dataset(manifest)


def test_unknown_and_duplicate_classes(manifest):
    data = json.loads(manifest.read_text())
    data["classes"].append("apple")
    with pytest.raises(ValueError, match="unique"):
        Dataset.model_validate(data)


def test_detection_matching_duplicates_and_wrong_labels():
    truth = [Box(label="apple", bbox=[0, 0, 10, 10])]
    pred = truth + [Box(label="cup", bbox=[0, 0, 10, 10])] + truth
    result = match_boxes(truth, pred)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 2, 0)


def test_matching_can_reassign_to_find_all_matches():
    truth = [Box(label="apple", bbox=[0, 0, 10, 10]), Box(label="apple", bbox=[5, 0, 15, 10])]
    pred = [Box(label="apple", bbox=[2, 0, 12, 10]), Box(label="apple", bbox=[0, 0, 7, 10])]
    result = match_boxes(truth, pred)
    assert (result["tp"], result["fn"]) == (2, 0)


def test_missing_predictions_count_as_missed_objects(manifest):
    dataset, _ = load_dataset(manifest)
    result = evaluate(dataset, {}, "development")
    assert result["missing_predictions"] == 4
    assert result["overall"]["fn"] == 12
    assert result["overall"]["recall"] == 0
    with pytest.raises(ValueError, match="outside"):
        evaluate(dataset, {"invented-sample": []}, "development")


def test_export_requires_explicit_review(manifest):
    with pytest.raises(ValueError, match="explicit"):
        export_reviewed(manifest, [])
    with pytest.raises(ValidationError):
        Review.model_validate({"sample_id": "fixture-0", "objects": [], "reviewed": True,
                               "reviewer": "test", "source": "manual", "elapsed_seconds": 10})


def test_export_yolo_geometry_and_provenance(manifest):
    dataset, _ = load_dataset(manifest)
    review = Review(sample_id="fixture-0", objects=dataset.samples[0].objects, reviewed=True,
                    all_objects_checked=True, reviewer="tester", source="manual", elapsed_seconds=22)
    archive = export_reviewed(manifest, [review])
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert "images/train/fixture-0.png" in z.namelist()
        assert not any("fixture-1" in name for name in z.namelist())
        width, height = Image.open(io.BytesIO(z.read("images/train/fixture-0.png"))).size
        labels = z.read("labels/train/fixture-0.txt").decode().splitlines()
        assert len(labels) == 3
        # Independently reconstruct standard YOLO xywh values against known pixel boxes.
        for line, original in zip(labels, review.objects):
            c, cx, cy, w, h = map(float, line.split())
            assert dataset.classes[int(c)] == original.label
            assert all(0 <= value <= 1 for value in (cx, cy, w, h))
            assert ((cx - w / 2) * width, (cy - h / 2) * height,
                    (cx + w / 2) * width, (cy + h / 2) * height) == pytest.approx(original.bbox, abs=1e-4)
        provenance = json.loads(z.read("manifest.json"))
        assert provenance["omitted_unreviewed_images"] == 3
        assert provenance["dataset_kind"] == "synthetic_fixture"


def test_reviewed_empty_image_exports_empty_label(manifest):
    review = Review(sample_id="fixture-0", objects=[], reviewed=True, all_objects_checked=True,
                    reviewer="tester", source="manual", elapsed_seconds=5)
    with zipfile.ZipFile(io.BytesIO(export_reviewed(manifest, [review]))) as archive:
        assert archive.read("labels/train/fixture-0.txt") == b""


def test_timing_includes_manual_and_assisted():
    manual = Review(sample_id="one", objects=[], reviewed=True, all_objects_checked=True,
                    reviewer="tester", source="manual", elapsed_seconds=100)
    assisted = Review(sample_id="two", objects=[], reviewed=True, all_objects_checked=True,
                      reviewer="tester", source="assisted", elapsed_seconds=60,
                      inference_model="fixture/test", prediction_run_id="test-run")
    assert timing_report([manual, assisted])["reduction_fraction"] == pytest.approx(.4)
    with pytest.raises(ValueError, match="different images"):
        timing_report([manual, manual])

