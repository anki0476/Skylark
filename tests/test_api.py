import io
import zipfile

from fastapi.testclient import TestClient

from skylark.api import create_app


def review_body(sample="fixture-0"):
    return {"sample_id": sample, "objects": [], "reviewed": True, "all_objects_checked": True,
            "reviewer": "test operator", "source": "manual", "elapsed_seconds": 20}


def test_review_persists_after_restart_and_exports(manifest, store):
    with TestClient(create_app(manifest, store)) as client:
        assert client.get("/api/health").json()["full_ui_ready"] is False
        assert client.get("/api/export").status_code == 409
        assert client.put("/api/reviews/fixture-0", json=review_body()).status_code == 200
        assert client.get("/api/images/fixture-0").headers["content-type"] == "image/png"
    with TestClient(create_app(manifest, store)) as client:
        assert len(client.get("/api/reviews").json()) == 1
        result = client.get("/api/export")
        assert result.status_code == 200
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            assert archive.read("labels/train/fixture-0.txt") == b""


def test_api_does_not_accept_unreviewed_or_bad_boxes(manifest, store):
    with TestClient(create_app(manifest, store)) as client:
        body = review_body()
        body["all_objects_checked"] = False
        assert client.put("/api/reviews/fixture-0", json=body).status_code == 422
        body["all_objects_checked"] = True
        body["objects"] = [{"label": "apple", "bbox": [0, 0, 1000, 400]}]
        assert client.put("/api/reviews/fixture-0", json=body).status_code == 422


def test_unknown_sample_and_assisted_provenance(manifest, store):
    with TestClient(create_app(manifest, store)) as client:
        assert client.get("/api/images/missing").status_code == 404
        body = review_body()
        body.update(source="assisted", prediction_run_id="missing", inference_model="nvidia/test")
        assert client.put("/api/reviews/fixture-0", json=body).status_code == 422


def test_cross_origin_writes_rejected(manifest, store):
    with TestClient(create_app(manifest, store)) as client:
        assert client.put("/api/reviews/fixture-0", json=review_body(),
                          headers={"Origin": "https://unrelated.example"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "unrelated.example"}).status_code == 403


def test_changed_images_invalidate_reviews(manifest, store):
    from PIL import Image
    with TestClient(create_app(manifest, store)) as client:
        assert client.put("/api/reviews/fixture-0", json=review_body()).status_code == 200
        Image.new("RGB", (640, 400), "white").save(manifest.parent / "fixture-0.png")
        assert client.get("/api/export").status_code == 409
    with TestClient(create_app(manifest, store)) as client:
        assert client.get("/api/reviews").json() == []
