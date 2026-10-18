import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from skylark.experiment import cache_key, gate_for, run_experiment
from skylark.fixture import FixtureProvider
from skylark.provider import Completion, ProviderError
from skylark.store import BudgetExceeded, Store


class ControlledProvider(FixtureProvider):
    def __init__(self, outcomes=None):
        self.calls = 0
        self.outcomes = outcomes or []

    def label(self, image, classes, task, settings):
        self.calls += 1
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        response = super().label(image, classes, task, settings)
        response.input_tokens, response.output_tokens = 100, 30
        return response


def test_offline_cannot_pass_real_gate(manifest, config, store):
    report = run_experiment(manifest, config, store, ControlledProvider())
    assert report["state"] == "completed"
    assert report["gate"]["status"] == "not_passed"
    assert report["gate"]["selected_model"] is None
    assert report["models"][0]["metrics"]["overall"]["recall"] == pytest.approx(2 / 3)
    assert store.get_run(report["run_id"])["payload"]["gate"] == report["gate"]


def test_cache_resumes_without_extra_calls(manifest, config, store):
    provider = ControlledProvider()
    first = run_experiment(manifest, config, store, provider)
    initial_cost = store.budget()["accounted_usd"]
    second = run_experiment(manifest, config, Store(store.directory), provider)
    assert provider.calls == 4
    assert second["models"][0]["cached_images"] == 4
    assert second["models"][0]["comparison_cost_usd"] == first["models"][0]["comparison_cost_usd"]
    assert store.budget()["accounted_usd"] == initial_cost


def test_cache_invalidated_by_prompt_model_settings_or_evidence(config):
    settings = config.models[0]
    original = cache_key("hash", ["apple"], "task", settings, "synthetic_fixture")
    assert original != cache_key("hash", ["apple"], "new task", settings, "synthetic_fixture")
    assert original != cache_key("hash", ["apple"], "task", settings, "live_nebius")
    changed = settings.model_copy(update={"image_long_edge": 640})
    assert original != cache_key("hash", ["apple"], "task", changed, "synthetic_fixture")


def test_invalid_output_retried_once_and_charged(manifest, config, store):
    invalid = Completion("not JSON", 100, 50, .01)
    provider = ControlledProvider([invalid, invalid])
    report = run_experiment(manifest, config, store, provider)
    assert provider.calls == 5  # two failed attempts for image 1, then one for each remaining image
    assert report["state"] == "partial_failure"
    assert report["models"][0]["images"][0]["attempts"] == 2
    assert len(store.attempts(report["run_id"])) == 5
    assert store.attempts(report["run_id"])[0]["cost_basis"] == "reported_tokens"
    assert store.attempts(report["run_id"])[0]["accounted_usd"] > 0


def test_unknown_billing_retains_estimate(manifest, config, store):
    provider = ControlledProvider([ProviderError("timeout", retryable=True)])
    report = run_experiment(manifest, config, store, provider)
    assert provider.calls == 5
    assert report["budget"]["uncertain_or_reserved_usd"] > 0


def test_auth_or_credit_failure_stops_all_requests(manifest, config, store):
    provider = ControlledProvider([ProviderError("access denied", retryable=False)])
    report = run_experiment(manifest, config, store, provider)
    assert provider.calls == 1
    assert report["state"] == "failed"


def test_preflight_budget_rejects_before_api_request(manifest, config, store):
    config.experiment_limit_usd = .001
    provider = ControlledProvider()
    with pytest.raises(BudgetExceeded, match="Projected"):
        run_experiment(manifest, config, store, provider)
    assert provider.calls == 0


def test_actual_spend_above_estimate_stops_next_attempt(manifest, config, store):
    provider = ControlledProvider([Completion('{"objects": []}', 30_000_000, 0, .01)])
    report = run_experiment(manifest, config, store, provider)
    assert provider.calls == 1
    assert report["budget"]["accounted_usd"] == 3.
    assert report["gate"]["status"] == "not_passed"


def test_cancelled_run_checkpoints_prior_images(manifest, config, store):
    provider = ControlledProvider([Completion('{"objects": []}', 100, 0, .01), KeyboardInterrupt()])
    report = run_experiment(manifest, config, store, provider)
    assert report["state"] == "cancelled"
    assert report["models"][0]["completed_images"] == 1
    assert store.attempts(report["run_id"])[-1]["status"] == "interrupted"
    assert report["models"][0]["accounted_usd"] == report["budget"]["accounted_usd"]


def test_reconciliation_updates_cached_comparison_cost_without_erasing_estimate(manifest, config, store):
    provider = ControlledProvider([ProviderError("timeout", retryable=True)])
    first = run_experiment(manifest, config, store, provider)
    attempt = store.attempts(first["run_id"])[0]
    initial_cost = first["models"][0]["comparison_cost_usd"]
    audit = store.reconcile(attempt["id"], 0, "Test provider usage reference verified 2026-10-17")
    assert audit["previous_usd"] == attempt["estimated_usd"]
    assert store.budget()["uncertain_or_reserved_usd"] == 0
    assert store.attempts(first["run_id"])[0]["estimated_usd"] == attempt["estimated_usd"]
    second = run_experiment(manifest, config, store, provider)
    assert provider.calls == 5
    assert second["models"][0]["comparison_cost_usd"] == pytest.approx(initial_cost - attempt["estimated_usd"])


def test_reconciliation_cannot_remove_reported_usage_or_reconcile_active_requests(store):
    attempt = store.reserve("run", "image", "model", .1, 2.)
    with pytest.raises(ValueError, match="active"):
        store.reconcile(attempt, 0, "Verified test reference")
    store.finish_attempt(attempt, status="completed", latency=.1, cost=.08)
    with pytest.raises(ValueError, match="reported token"):
        store.reconcile(attempt, 0, "Verified test reference")
    with pytest.raises(ValueError, match="finite"):
        store.reconcile(attempt, float("nan"), "Verified test reference")


def test_budget_reservations_are_atomic_across_connections(store):
    def reserve(index):
        try:
            Store(store.directory).reserve("run", str(index), "test", .6, 1.)
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, range(2)))
    assert sum(results) == 1
    assert store.budget()["accounted_usd"] == .6


def test_gate_requires_all_evidence_and_selects_f1_then_cost():
    def candidate(name, f1, cost):
        return {"model": name, "completed_images": 20, "comparison_cost_usd": cost,
                "metrics": {"overall": {"precision": .8, "recall": .8, "f1": f1}}}
    report = {"evidence_kind": "live_nebius", "dataset_kind": "real_photographs",
              "development_images": 20, "conditions": ["clean", "shadows", "clutter", "occlusion"],
              "classes_present": ["apple", "cup", "bottle"], "experiment_limit_usd": 2.,
              "budget": {"accounted_usd": .2, "uncertain_or_reserved_usd": 0},
              "models": [candidate("nvidia/a", .8, .2), candidate("nvidia/b", .8, .1)]}
    assert gate_for(report)["selected_model"] == "nvidia/b"
    report["budget"]["uncertain_or_reserved_usd"] = .01
    assert gate_for(report)["status"] == "not_passed"

