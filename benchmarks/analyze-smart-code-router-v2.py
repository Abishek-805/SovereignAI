"""Offline analysis of frozen V2 coding trials. Never loads models or executes code.

The report may be a checkpoint. Missing arms, reviews, and measurements remain
unknown. A paired latency difference is descriptive, never a causal switch gain.
"""

import argparse
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path


ARMS = ("A", "B", "C", "D", "E")
VERDICTS = ("PASS", "PARTIAL", "FAIL", "UNKNOWN")


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def _percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def _semantic_verdict(row, review):
    if not review or review.get("status", review.get("verdict")) not in VERDICTS:
        return "UNKNOWN"
    answer = (row.get("operational_result") or {}).get("answer")
    if not isinstance(answer, str) or not review.get("answer_sha256"):
        return "UNKNOWN"
    if hashlib.sha256(answer.encode("utf-8")).hexdigest() != review["answer_sha256"]:
        return "UNKNOWN"
    fixture = review.get("fixture_sha256")
    if fixture is not None and fixture != row.get("fixture_sha256"):
        return "UNKNOWN"
    return review.get("status", review.get("verdict"))


def _trusted_verdict(row):
    trajectory = row.get("validation_trajectory") or []
    checks = [event for event in trajectory if event.get("phase") == "trusted_tests" and event.get("container_executed") is True]
    if not checks:
        return "UNKNOWN"
    last = checks[-1]
    final = row.get("validation") or {}
    if (last.get("exit_code") == 0 and last.get("artifact_verified") is True and
            final.get("container_executed") is True and final.get("exit_code") == 0 and
            final.get("artifact_verified") is True and final.get("original_sources_preserved") is True and
            row.get("correctness") is True and row.get("stage") == "READY_FOR_REVIEW" and
            row.get("gate") == "EXECUTED"):
        return "PASS"
    if (final.get("container_executed") is True and
            (final.get("artifact_verified") is False or
             (isinstance(final.get("exit_code"), int) and final["exit_code"] != 0))):
        return "FAIL"
    if final.get("original_sources_preserved") is False:
        return "FAIL"
    if row.get("correctness") is False and final.get("container_executed") is True:
        return "FAIL"
    if isinstance(last.get("exit_code"), int) and last["exit_code"] != 0 and last.get("artifact_verified") is False:
        return "FAIL"
    return "UNKNOWN"


def _task_completion(row, trusted, semantic):
    if (row.get("gate") in {"FAIL", "STOP"} or row.get("stage") == "failed" or
            (row.get("operational_result") or {}).get("error") or
            (row.get("validation") or {}).get("original_sources_preserved") is False):
        return "FAIL" if row.get("gate") != "STOP" else "UNKNOWN"
    if trusted == "FAIL":
        return "FAIL"
    if trusted == "PASS":
        return "PASS"
    if row.get("stage") == "answered":
        return semantic
    return "UNKNOWN"


def _outcome(row, semantic):
    trusted = _trusted_verdict(row)
    return _task_completion(row, trusted, semantic)


def _routing_counts(rows):
    counts = {name: Counter() for name in ("task_type", "complexity", "worker_role")}
    for row in rows:
        expected = row.get("expected") or {}
        predicted = row.get("prediction") or {}
        for name in ("task_type", "complexity"):
            counts[name]["correct" if expected.get(name) and predicted.get(name) == expected[name] else
                         "incorrect" if expected.get(name) and predicted.get(name) else "unknown"] += 1
        suitable = set(expected.get("suitable_workers") or [])
        actual = predicted.get("worker_role")
        if "code" in suitable:
            suitable.add("coder")
        if "coder" in suitable:
            suitable.add("code")
        counts["worker_role"]["suitable" if suitable and actual in suitable else
                              "unsuitable" if suitable and actual else "unknown"] += 1
    return {key: {label: value[label] for label in ("correct", "incorrect", "suitable", "unsuitable", "unknown") if label in ("correct", "incorrect", "unknown") or key == "worker_role"}
            for key, value in counts.items()}


def _cluster_interval(outcomes, case_contracts, *, seed=1729, repetitions=1000):
    """Case-weighted bootstrap over independent development contract clusters."""
    groups = defaultdict(list)
    for case_id, verdict in outcomes.items():
        if verdict in ("PASS", "FAIL") and case_id in case_contracts:
            groups[case_contracts[case_id]].append(verdict == "PASS")
    ordered = [groups[key] for key in sorted(groups)]
    if len(ordered) < 2:
        return {"cluster_count": len(ordered), "interval": None, "reason": "fewer than two evaluated development contracts"}
    rng = random.Random(seed)
    samples = []
    for _ in range(repetitions):
        selected = [rng.choice(ordered) for _ in ordered]
        flattened = [value for group in selected for value in group]
        samples.append(sum(flattened) / len(flattened))
    return {"cluster_count": len(ordered), "method": "case-weighted contract cluster percentile bootstrap",
            "confidence": 0.95, "seed": seed, "repetitions": repetitions,
            "interval": [_percentile(samples, .025), _percentile(samples, .975)]}


def _failure_sequence(row):
    """Describe an observed mixed failure without inferring a repair invocation."""
    actual_failure = any(
        item.get("phase") == "trusted_tests" and item.get("container_executed") is True and
        isinstance(item.get("exit_code"), int) and item["exit_code"] != 0
        for item in row.get("validation_trajectory") or [])
    error = (row.get("operational_result") or {}).get("error") or {}
    proposal_failure = (row.get("gate") == "FAIL" and isinstance(error, dict) and
                        error.get("code") in {"semantic_uncertainty", "generation_format"})
    if not (actual_failure and proposal_failure):
        return False, False
    # Trajectory entries have no timestamp. Only an explicit telemetry validation
    # event can establish that a later generation call was a post-failure attempt.
    events = (row.get("telemetry") or {}).get("events") or []
    validation_times = [item.get("at") for item in events
                        if item.get("event") in {"VALIDATION_FAILED", "TRUSTED_TESTS_FAILED"}
                        and _number(item.get("at")) is not None]
    generation_times = [item.get("at") for item in events if item.get("event") == "GENERATION_STARTED"
                        and _number(item.get("at")) is not None]
    proven_generation = bool(validation_times and any(at > min(validation_times) for at in generation_times))
    return True, proven_generation


def analyze(report, semantic_reviews=None, *, case_contracts=None):
    reviews = semantic_reviews.get("reviews", []) if isinstance(semantic_reviews, dict) else semantic_reviews or []
    review_by_key = {(item["arm"], item["case_id"]): item for item in reviews}
    rows = report.get("rows") or []
    grouped = defaultdict(list)
    for row in rows:
        if row.get("arm") in ARMS and isinstance(row.get("case_id"), str):
            grouped[row["arm"]].append(row)
    result = {"scope": "offline observations; incomplete report rows and unreviewed answers remain UNKNOWN",
              "report_state": report.get("state"), "arms": {}, "paired": {}, "switch_effects": {}}
    outcomes_by_arm = {}
    for arm in ARMS:
        selected = grouped[arm]
        trusted, semantic, completion, outcomes, failure_layers = Counter(), Counter(), Counter(), {}, Counter()
        sequences = Counter()
        latencies, ram, vram = [], [], []
        calls = switches = repairs = recovered = 0
        calls_unknown = switches_unknown = 0
        for row in selected:
            key = row["case_id"]
            sem = _semantic_verdict(row, review_by_key.get((arm, key)))
            semantic[sem] += 1
            trust = _trusted_verdict(row)
            trusted[trust] += 1
            outcomes[key] = _outcome(row, sem)
            completion[outcomes[key]] += 1
            measures = row.get("measurements") or {}
            for keyname, accumulator in (("latency_seconds", latencies), ("peak_ram_mib", ram), ("peak_vram_mib", vram)):
                number = _number(measures.get(keyname))
                if number is not None:
                    accumulator.append(number)
            count = _number(measures.get("model_calls"))
            if count is None:
                calls_unknown += 1
            else:
                calls += count
            count = _number(measures.get("model_switches"))
            if count is None:
                switches_unknown += 1
            else:
                switches += count
            if row.get("repair_observed") is True:
                repairs += 1
                if row.get("repair_succeeded") is True and trust == "PASS" and len(row.get("validation_trajectory") or []) >= 2:
                    recovered += 1
            failure_layers[row.get("failure_layer") or "UNKNOWN"] += 1
            mixed, post_validation_generation = _failure_sequence(row)
            if mixed:
                sequences["validation_failure_then_terminal_proposal_failure"] += 1
                if post_validation_generation:
                    sequences["post_validation_generation_proven"] += 1
        outcomes_by_arm[arm] = outcomes
        result["arms"][arm] = {
            "n": len(selected), "trusted": {verdict: trusted[verdict] for verdict in ("PASS", "FAIL", "UNKNOWN")},
            "semantic": {verdict: semantic[verdict] for verdict in VERDICTS},
            "task_completion": {verdict: completion[verdict] for verdict in VERDICTS},
            "outcome": {verdict: list(outcomes.values()).count(verdict) for verdict in VERDICTS},
            "routing": _routing_counts(selected),
            "model_calls": calls, "model_calls_unknown_rows": calls_unknown,
            "model_switches": switches, "model_switches_unknown_rows": switches_unknown,
            "latency_p50_seconds": _percentile(latencies, .5), "latency_p95_seconds": _percentile(latencies, .95),
            "latency_observed_rows": len(latencies), "max_sampled_ram_mib": max(ram, default=None),
            "max_sampled_vram_mib": max(vram, default=None),
            "repair_observed": repairs, "repair_independent_recovery": recovered,
            "failure_layers": dict(sorted(failure_layers.items())),
            "failure_sequences": {
                "validation_failure_then_terminal_proposal_failure": sequences["validation_failure_then_terminal_proposal_failure"],
                "post_validation_generation_proven": sequences["post_validation_generation_proven"],
                "interpretation": "Actual failed trusted container check precedes terminal proposal error; this does not establish a repair call unless timestamped telemetry proves generation after validation."},
        }
        if case_contracts is not None:
            result["arms"][arm]["trusted_or_reviewed_contract_interval"] = _cluster_interval(outcomes, case_contracts)
    for baseline in ARMS[:-1]:
        common = sorted(outcomes_by_arm[baseline].keys() & outcomes_by_arm["E"].keys())
        transitions = Counter((outcomes_by_arm[baseline][case], outcomes_by_arm["E"][case]) for case in common)
        result["paired"][f"E_vs_{baseline}"] = {
            "cases": len(common), "transitions": {f"{left}->{right}": count for (left, right), count in sorted(transitions.items())},
            "both_decisive": sum(count for (left, right), count in transitions.items() if left in ("PASS", "FAIL") and right in ("PASS", "FAIL")),
        }
    # Sequential fixed-order runs cannot isolate a counterfactual switch decision
    # from warm state, model role, and prior case effects. Do not label a switch
    # NECESSARY/HELPFUL/HARMFUL from a cross-arm timing comparison.
    for arm in ARMS:
        observations = [switch for row in grouped[arm] for switch in row.get("switch_observations", [])]
        result["switch_effects"][arm] = {"observed": len(observations), "effect": "UNKNOWN",
                                         "reason": "No equivalent randomized same-state switch/no-switch counterfactual is recorded"}
    return result


def _development_contracts(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("metadata") or data.get("meta") or {}
    # Never allow the optional confidence calculation to expose heldout fixtures.
    if "heldout" in str(path).lower() or "heldout" in json.dumps(meta).lower():
        raise ValueError("Heldout datasets are excluded from contract confidence analysis")
    cases = data.get("cases") or []
    if len(cases) != 100 or not all(str(case.get("id", "")).startswith("v2-main-") for case in cases):
        raise ValueError("Contract confidence requires the explicit V2 development fixture")
    return {case["id"]: case["contract_id"] for case in cases if case.get("contract_id")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--semantic-review", type=Path)
    parser.add_argument("--development-dataset", type=Path, help="V2 development fixture only; heldout denied")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    contracts = _development_contracts(args.development_dataset) if args.development_dataset else None
    review = json.loads(args.semantic_review.read_text(encoding="utf-8")) if args.semantic_review else None
    report = json.loads(args.report.read_text(encoding="utf-8"))
    summary = analyze(report, review, case_contracts=contracts)
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
