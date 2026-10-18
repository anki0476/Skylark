"""Detection matching never treats duplicate predictions as extra true positives."""

from __future__ import annotations

from statistics import median

from .schemas import Box, Dataset, Review


def iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a.bbox
    bx1, by1, bx2, by2 = b.bbox
    intersection = max(0., min(ax2, bx2) - max(ax1, bx1)) * max(0., min(ay2, by2) - max(ay1, by1))
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection
    return intersection / union if union else 0.


def match_boxes(truth: list[Box], predictions: list[Box], threshold: float = .5) -> dict:
    """Maximum-cardinality, class-aware bipartite matching; IoU orders ties.

    No model confidence is invented. This is fixed-threshold detection F1, not AP.
    """
    adjacency = []
    for predicted in predictions:
        candidates = [(iou(predicted, gt), i) for i, gt in enumerate(truth)
                      if gt.label == predicted.label and iou(predicted, gt) >= threshold]
        adjacency.append([i for _, i in sorted(candidates, reverse=True)])
    matched: dict[int, int] = {}

    def assign(prediction_index: int, seen: set[int]) -> bool:
        for truth_index in adjacency[prediction_index]:
            if truth_index in seen:
                continue
            seen.add(truth_index)
            if truth_index not in matched or assign(matched[truth_index], seen):
                matched[truth_index] = prediction_index
                return True
        return False

    for index in range(len(predictions)):
        assign(index, set())
    return {"tp": len(matched), "fp": len(predictions) - len(matched),
            "fn": len(truth) - len(matched),
            "matched_ious": [iou(truth[t], predictions[p]) for t, p in matched.items()]}


def summarize(counts: list[dict]) -> dict:
    tp = sum(c["tp"] for c in counts)
    fp = sum(c["fp"] for c in counts)
    fn = sum(c["fn"] for c in counts)
    overlaps = [v for c in counts for v in c["matched_ious"]]
    precision = tp / (tp + fp) if tp + fp else 0.
    recall = tp / (tp + fn) if tp + fn else 0.
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.,
            "mean_matched_iou": sum(overlaps) / len(overlaps) if overlaps else None}


def evaluate(dataset: Dataset, predictions: dict[str, list[Box]], split: str) -> dict:
    samples = [s for s in dataset.samples if s.split == split]
    rows, conditions = [], {}
    sample_ids = {s.id for s in samples}
    unknown = predictions.keys() - sample_ids
    if unknown:
        raise ValueError(f"Predictions contain IDs outside the {split} split: {sorted(unknown)}")
    for sample in samples:
        boxes = predictions.get(sample.id, [])
        for box in boxes:
            box.validate_frame(sample.width, sample.height, dataset.classes)
        counts = match_boxes(sample.objects, boxes)
        row = {"sample_id": sample.id, "condition": sample.condition,
               "prediction_available": sample.id in predictions, **counts}
        rows.append(row)
        conditions.setdefault(sample.condition, []).append(counts)
    return {"split": split, "image_count": len(samples),
            "missing_predictions": sum(not r["prediction_available"] for r in rows),
            "overall": summarize(rows),
            "by_condition": {key: summarize(value) for key, value in sorted(conditions.items())},
            "per_image": rows}


def timing_report(reviews: list[Review]) -> dict:
    seen = set()
    times: dict[str, list[float]] = {"manual": [], "assisted": []}
    for review in reviews:
        if review.sample_id in seen:
            raise ValueError("Timed sessions must use different images to avoid repeated-image learning")
        seen.add(review.sample_id)
        times[review.source].append(review.elapsed_seconds)
    medians = {k: median(v) if v else None for k, v in times.items()}
    manual, assisted = medians["manual"], medians["assisted"]
    return {"sample_counts": {k: len(v) for k, v in times.items()}, "median_seconds": medians,
            "reduction_fraction": 1 - assisted / manual if manual and assisted else None,
            "limitation": "Small single-operator study; match difficulty and alternate session order."}
