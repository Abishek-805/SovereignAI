"""Synthetic, offline metrics checks; no model, Docker, or heldout data."""

import hashlib
import importlib.util
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "benchmarks" / "analyze-smart-code-router-v2.py"
spec = importlib.util.spec_from_file_location("smart_code_v2_analysis", SOURCE)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def row(arm, case, *, trusted=None, answer="answer", repair=False, succeeded=False, latency=5, switches=0):
    trajectory = []
    if trusted is not None:
        trajectory = [{"phase": "trusted_tests", "container_executed": True,
                       "exit_code": 0 if trusted else 1, "artifact_verified": trusted}]
        if repair:
            trajectory.insert(0, {"phase": "trusted_tests", "container_executed": True,
                                  "exit_code": 1, "artifact_verified": False})
    return {"arm": arm, "case_id": case, "fixture_sha256": "fixture", "gate": "EXECUTED",
            "stage": "READY_FOR_REVIEW" if trusted else "failed" if trusted is False else "answered",
            "correctness": trusted,
            "validation": {"artifact_verified": trusted, "container_executed": trusted is not None,
                           "exit_code": 0 if trusted else 1 if trusted is False else None,
                           "original_sources_preserved": True},
            "expected": {"task_type": "DEBUG", "complexity": "simple", "suitable_workers": ["code"]},
            "prediction": {"task_type": "DEBUG", "complexity": "simple", "worker_role": "coder"},
            "operational_result": {"answer": answer}, "validation_trajectory": trajectory,
            "repair_observed": repair, "repair_succeeded": succeeded,
            "measurements": {"latency_seconds": latency, "model_calls": 2 if repair else 1,
                             "model_switches": switches, "peak_ram_mib": 100, "peak_vram_mib": 70},
            "switch_observations": [{"previous_model": "M1", "next_model": "M2"}] if switches else [],
            "failure_layer": None if trusted else "VALIDATION_FAILURE"}


def test_trusted_semantic_and_paired_outcomes_remain_distinct():
    answer = "carefully reviewed"
    review = {"reviews": [{"arm": "E", "case_id": "c3", "status": "PARTIAL",
                           "answer_sha256": hashlib.sha256(answer.encode()).hexdigest()}]}
    rows = [row("A", "c1", trusted=False), row("E", "c1", trusted=True, repair=True, succeeded=True, switches=1),
            row("E", "c2", trusted=False), row("E", "c3", answer=answer)]
    result = analysis.analyze({"state": "running", "rows": rows}, review)
    e = result["arms"]["E"]
    assert e["n"] == 3
    assert e["trusted"] == {"PASS": 1, "FAIL": 1, "UNKNOWN": 1}
    assert e["semantic"] == {"PASS": 0, "PARTIAL": 1, "FAIL": 0, "UNKNOWN": 2}
    assert e["repair_independent_recovery"] == 1
    assert e["routing"]["worker_role"]["suitable"] == 3
    assert result["paired"]["E_vs_A"]["transitions"] == {"FAIL->PASS": 1}
    assert result["switch_effects"]["E"]["effect"] == "UNKNOWN"


def test_unbound_review_and_nonexecuted_validation_do_not_create_success():
    candidate = row("E", "c1", answer="new")
    candidate["validation_trajectory"] = [{"phase": "trusted_tests", "container_executed": False,
                                           "exit_code": 0, "artifact_verified": True}]
    result = analysis.analyze({"rows": [candidate]}, {"reviews": [{"arm": "E", "case_id": "c1", "status": "PASS",
        "answer_sha256": hashlib.sha256(b"old").hexdigest()}]})
    assert result["arms"]["E"]["trusted"]["UNKNOWN"] == 1
    assert result["arms"]["E"]["outcome"]["UNKNOWN"] == 1
    assert result["arms"]["E"]["latency_p95_seconds"] == 5
    assert result["arms"]["E"]["max_sampled_vram_mib"] == 70


def test_cluster_interval_is_development_only_and_missing_stays_unknown(tmp_path):
    report = {"rows": [row("E", "c1", trusted=True), row("E", "c2", trusted=False), row("E", "c3")]}
    result = analysis.analyze(report, case_contracts={"c1": "contract_a", "c2": "contract_b", "c3": "contract_b"})
    interval = result["arms"]["E"]["trusted_or_reviewed_contract_interval"]
    assert interval["cluster_count"] == 2
    assert 0 <= interval["interval"][0] <= interval["interval"][1] <= 1
    assert analysis.analyze(report)["arms"]["E"].get("trusted_or_reviewed_contract_interval") is None
    heldout = tmp_path / "v2-heldout.json"
    heldout.write_text('{"cases": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="Heldout"):
        analysis._development_contracts(heldout)


@pytest.mark.parametrize("alter", [
    lambda candidate: candidate.update(correctness=False, stage="failed"),
    lambda candidate: candidate["validation"].update(artifact_verified=False, exit_code=1),
    lambda candidate: candidate["validation"].update(original_sources_preserved=False),
    lambda candidate: candidate.update(stage="answered"),
])
def test_intermediate_pass_cannot_override_final_state(alter):
    candidate = row("E", "c1", trusted=True)
    alter(candidate)
    result = analysis.analyze({"rows": [candidate]})
    assert result["arms"]["E"]["trusted"]["PASS"] == 0
    assert result["arms"]["E"]["task_completion"]["PASS"] == 0


def test_generation_failure_is_task_failure_without_claiming_trusted_test_failure():
    candidate = row("E", "c1")
    candidate.update(stage=None, gate="FAIL", operational_result={"error": {"code": "generation_format"}},
                     failure_layer="MODEL_FAILURE")
    result = analysis.analyze({"rows": [candidate]})["arms"]["E"]
    assert result["trusted"] == {"PASS": 0, "FAIL": 0, "UNKNOWN": 1}
    assert result["task_completion"]["FAIL"] == 1
    assert result["outcome"]["FAIL"] == 1


def test_actual_failed_validation_then_terminal_proposal_error_is_separate_sequence():
    candidate = row("A", "c1", trusted=False)
    candidate.update(gate="FAIL", stage=None, correctness=None, repair_observed=False,
                     validation={"artifact_verified": None, "original_sources_preserved": True},
                     operational_result={"error": {"code": "semantic_uncertainty"}},
                     failure_layer="MODEL_FAILURE", telemetry={"events": [
                         {"event": "GENERATION_STARTED", "at": 1},
                         {"event": "GENERATION_COMPLETED", "at": 2},
                         {"event": "REQUEST_FAILED", "at": 3}]})
    metrics = analysis.analyze({"rows": [candidate]})["arms"]["A"]
    assert metrics["repair_observed"] == 0
    assert metrics["failure_sequences"]["validation_failure_then_terminal_proposal_failure"] == 1
    assert metrics["failure_sequences"]["post_validation_generation_proven"] == 0
    assert metrics["failure_layers"]["MODEL_FAILURE"] == 1


def test_nonexecuted_check_or_unrelated_error_does_not_infer_sequence():
    candidate = row("A", "c1", trusted=False)
    candidate.update(gate="FAIL", stage=None,
                     operational_result={"error": {"code": "generation_format"}})
    candidate["validation_trajectory"][0]["container_executed"] = False
    metrics = analysis.analyze({"rows": [candidate]})["arms"]["A"]
    assert metrics["failure_sequences"]["validation_failure_then_terminal_proposal_failure"] == 0
