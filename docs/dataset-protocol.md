# Photograph and annotation protocol

## What to collect

Collect 60 original tabletop photographs of apples, cups, and bottles:
20 development and 40 held out. Use 5 development and 10 held-out photographs
for each condition: clean, shadows, clutter, and occlusion. Balance the classes
across conditions. Include some images without target objects to expose false
positives. These proportions are a collection target, not a model performance claim.

Change physical scene arrangements across splits. All photographs of one arrangement,
including alternate lighting, frames, crops, and future augmentations, share one
`scene_id` and one split. The validator catches shared scene IDs and identical
decoded images; it cannot reliably detect all near duplicates. Human grouping matters.

Use photos you own or have permission to process and redistribute. Keep unrelated
people, personal documents, and sensitive information out of the demonstration.

## Coordinates and classes

Orient photographs upright according to EXIF first. Width, height, and boxes in the
manifest must refer to that upright image. All pipeline exports strip EXIF and save
the upright pixels, so consumers do not rotate them again.

- Classes are exactly `apple`, `cup`, and `bottle` for the initial gate.
- A box is `[x_min, y_min, x_max, y_max]` in pixels with positive area.
- Enclose the full visible extent of the object, including a visible cup handle.
- For occlusion, bound the visible portions; do not guess hidden geometry.
- Annotate every identifiable visible target instance. Do not annotate unidentifiable
  fragments or objects of unrelated classes. Record difficult cases for discussion.
- Set `ground_truth_verified` to true only after checking both existing boxes and
  missed objects. An empty `objects` list must be a deliberate absence confirmation.

Do not use the same model's proposals as independent benchmark ground truth.
Create manual truth before running the model. Lock the held-out labels and exclude
held-out images from prompt/model selection. The probe only sends development images.

Example entry after manually inspecting an upright image:

```json
{
  "id": "arrangement-01-clean",
  "image": "images/arrangement-01-clean.png",
  "scene_id": "arrangement-01",
  "split": "development",
  "condition": "clean",
  "width": 1280,
  "height": 960,
  "ground_truth_verified": true,
  "objects": [{"label": "apple", "bbox": [100, 200, 350, 440]}]
}
```

Coordinates above illustrate the format, not labels for your actual photograph.
Use a manual annotation tool and transcribe/import its pixel boxes using this
convention. The full interactive Skylark editor follows the feasibility gate.

## Evaluation interpretation

Matching is class-aware and one-to-one at IoU >= 0.5. A duplicate prediction is a
false positive. Missing or invalid model output counts as missed ground-truth
objects and is also recorded as an unavailable prediction. The metric is detection
precision/recall/F1 at a fixed overlap threshold, not COCO mAP.

Mean IoU describes matched objects only. Review it alongside recall: a model can
have high matched overlap while missing most objects. Global precision/recall use
micro-aggregated counts; condition results expose hard subsets.

## Timing study after the product UI exists

Use matched but different image sets for manual and assisted labeling. Alternate
session order and record object counts/conditions so easy scenes do not all enter
one arm. Include model wait, every correction, and final image review in elapsed
time; exclude breaks. Save `source`, `elapsed_seconds`, and the operator in review
records. The API accepts recorded times; it does not currently measure a UI timer.

Compare median time and final reviewed F1 on each arm. The target is at least
30% lower median time with assisted F1 no more than five percentage points below
manual. A small single-operator result is exploratory; report the sample size,
conditions, ordering, and limitations. Do not imply a controlled population study.

Do not relabel fixture outcomes as real results, select only favorable images,
or use held-out measurements to tune the model and still call them held out.
