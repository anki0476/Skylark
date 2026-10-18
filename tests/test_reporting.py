import json

import pytest

from skylark.experiment import run_experiment
from skylark.fixture import FixtureProvider
from skylark.reporting import visual_report


def test_report_is_bound_to_exact_dataset_and_distinguishes_fixture(manifest, config, store):
    report = run_experiment(manifest, config, store, FixtureProvider())
    html = visual_report(manifest, report)
    assert "No model was called" in html
    assert "not passed" in html
    assert 'href="data:image/png;base64,' in html
    value = json.loads(manifest.read_text())
    value["name"] = "Changed dataset"
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="do not match"):
        visual_report(manifest, report)


def test_report_escapes_untrusted_model_error_and_names(manifest, config, store):
    value = json.loads(manifest.read_text())
    value["name"] = '<script>alert("untrusted")</script>'
    manifest.write_text(json.dumps(value))
    report = run_experiment(manifest, config, store, FixtureProvider())
    report["models"][0]["images"][0]["error"] = '<img src=x onerror="alert(1)">'
    report["models"][0]["model"] = '</option><script>alert("candidate")</script>'
    html = visual_report(manifest, report)
    assert '<script>alert(' not in html
    assert '<img src=x' not in html
    assert '&lt;img src=x' in html
    assert 'default-src &#x27;none&#x27;' not in html  # CSP is static, not derived from input.
