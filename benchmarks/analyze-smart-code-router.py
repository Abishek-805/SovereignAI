"""Offline endpoint analysis; never executes candidates or models."""
import argparse
import hashlib
import json
import random
from pathlib import Path


def clustered_pass_interval(observations, seed=1729, repetitions=1000):
    """Resample reused trusted contracts, preserving all outcomes per cluster."""
    clusters = {}
    for contract, passed in observations:
        clusters.setdefault(contract, []).append(passed)
    groups = [clusters[key] for key in sorted(clusters)]
    count = len(observations)
    interval = None
    if len(groups) >= 2:
        rng = random.Random(seed)
        samples = []
        for _ in range(repetitions):
            sampled = [value for _ in groups for value in rng.choice(groups)]
            samples.append(sum(sampled) / len(sampled))
        samples.sort()
        def percentile(fraction):
            position = (len(samples) - 1) * fraction
            lower = int(position)
            upper = min(lower + 1, len(samples) - 1)
            return samples[lower] + (samples[upper] - samples[lower]) * (position - lower)
        interval = [percentile(.025), percentile(.975)]
    return {'method': 'percentile bootstrap of trusted contract clusters with replacement',
            'cluster_key': 'SHA256 canonical JSON of trusted_files and command',
            'seed': seed, 'repetitions': repetitions, 'confidence': .95,
            'clusters': len(groups), 'evaluated_cases': count,
            'pass_fraction': sum(value for _, value in observations) / count if count else None,
            'interval': interval, 'interval_unknown_reason': 'fewer than two evaluated clusters' if interval is None else None}


def worker_suitability_correction(results):
    """Offline terminology correction; observed rows and policies stay immutable."""
    def canonical(role):
        return 'code' if role == 'coder' else role
    profiles = results.get('provenance', {}).get('profiles', [])
    model_roles = {profile['model_id']: {canonical(role) for role in profile.get('worker_roles', [])}
                   for profile in profiles if isinstance(profile, dict) and profile.get('model_id')}
    arms = {}
    for row in results.get('rows', []):
        arm = arms.setdefault(row['arm'], {name: {'suitable': 0, 'unsuitable': 0, 'unknown': 0}
            for name in ('advisory_policy_role', 'reported_worker_role', 'actual_active_model_roles')})
        expected = {canonical(role) for role in row.get('expected', {}).get('suitable_workers', [])}
        prediction = row.get('prediction') or {}
        classified = next((event.get('details', {}).get('worker_role')
            for event in row.get('telemetry', {}).get('events', [])
            if event.get('event') == 'CODING_REQUEST_CLASSIFIED'), None)
        observed = {'advisory_policy_role': {canonical(classified)} if classified else set(),
                    'reported_worker_role': {canonical(prediction['worker_role'])} if prediction.get('worker_role') else set(),
                    'actual_active_model_roles': model_roles.get(prediction.get('active_worker'), set())}
        for name, roles in observed.items():
            endpoint = 'unknown' if not expected or not roles else 'suitable' if expected & roles else 'unsuitable'
            arm[name][endpoint] += 1
    for arm in arms.values():
        for metric in arm.values():
            metric['evaluated'] = metric['suitable'] + metric['unsuitable']
            metric['accuracy'] = metric['suitable'] / metric['evaluated'] if metric['evaluated'] else None
    return {'alias_map': {'coder': 'code'}, 'arms': arms,
            'scope': 'Fixture suitable-worker labels; advisory event, reported role and concrete active model assignment scored separately. Actual roles come only from frozen result profile provenance.',
            'limitation': 'Suitability against authored fixture policy does not prove measured model superiority or successful task execution.'}


def analyze(results, dataset, semantic_reviews=None):
    cases = {case['id']: case for case in dataset['cases']}
    review_records = semantic_reviews.get('reviews', []) if isinstance(semantic_reviews, dict) else semantic_reviews or []
    reviews = {(r['arm'], r['case_id']): r for r in review_records}
    rows = results.get('rows', [])

    def group(selected):
        endpoints = {'passed': 0, 'partial': 0, 'failed': 0, 'unknown': 0}
        trusted = {'passed': 0, 'partial': 0, 'failed': 0, 'unknown': 0}
        artifacts = {'passed': 0, 'failed': 0, 'unknown': 0}
        executable = 0
        trusted_observations = []
        blocked_cases = 0
        unknown_reasons = {}
        semantic_verified = 0
        semantic_verdicts = {verdict: 0 for verdict in ('PASS', 'PARTIAL', 'FAIL', 'UNKNOWN')}
        for row in selected:
            case = cases[row['case_id']]
            is_trusted = case.get('oracle', {}).get('kind') == 'trusted_tests'
            supported = case.get('execution_supported', True) and row.get('gate') != 'NOT_VERIFIED'
            executable += supported
            artifact = 'passed' if row.get('correctness') is True else 'failed' if row.get('correctness') is False else 'unknown'
            artifacts[artifact] += 1
            endpoint = 'unknown'
            if row.get('gate') == 'STOP':
                blocked_cases += 1
                reason = 'environment_or_execution_stopped'
                unknown_reasons[reason] = unknown_reasons.get(reason, 0) + 1
            elif supported:
                if (row.get('gate') == 'FAIL' or row.get('operational_result', {}).get('error') or
                        row.get('stage') == 'failed' or row.get('correctness') is False):
                    endpoint = 'failed'
                elif row.get('stage') == 'READY_FOR_REVIEW' and row.get('correctness') is True and is_trusted and not case.get('oracle', {}).get('semantic_review_required'):
                    endpoint = 'passed'
                else:
                    review = reviews.get((row.get('arm'), row['case_id']))
                    # Reviewer must bind both the frozen fixture and actual candidate.
                    hashes = row.get('validation', {}).get('candidate_hashes')
                    if hashes is None:
                        changes = row.get('operational_result', {}).get('changes')
                        initial = case.get('context', {}).get('initial_files')
                        if isinstance(changes, list) and isinstance(initial, dict):
                            candidate = dict(initial)
                            valid = True
                            for change in changes:
                                name = change.get('path')
                                if name not in case.get('allowed_change_paths', []) or change.get('before') != candidate.get(name):
                                    valid = False
                                    break
                                if change.get('after') is None:
                                    candidate.pop(name, None)
                                else:
                                    candidate[name] = change['after']
                            if valid:
                                hashes = {name: hashlib.sha256(content.encode()).hexdigest() for name, content in candidate.items()}
                    answer = row.get('operational_result', {}).get('answer')
                    fixture_matches = (review and row.get('fixture_sha256') is not None and
                                       review.get('fixture_sha256') == row['fixture_sha256'])
                    answer_matches = (isinstance(answer, str) and review and
                                      review.get('answer_sha256') == hashlib.sha256(answer.encode()).hexdigest())
                    verdict = review.get('verdict') if review else None
                    if (not is_trusted and fixture_matches and answer_matches and
                            row.get('stage') in {'answered', 'READY_FOR_REVIEW'} and verdict in semantic_verdicts):
                        semantic_verified += 1
                        semantic_verdicts[verdict] += 1
                        endpoint = {'PASS': 'passed', 'PARTIAL': 'partial', 'FAIL': 'failed', 'UNKNOWN': 'unknown'}[verdict]
                    elif (is_trusted and fixture_matches and answer_matches and
                            row.get('stage') == 'answered' and row.get('correctness') is None and
                            not hashes and verdict == 'FAIL' and review.get('goal_satisfied') is False):
                        # A reviewed refusal/no-patch answer can fail the requested goal
                        # without inventing a failed code artifact or test execution.
                        semantic_verified += 1
                        semantic_verdicts['FAIL'] += 1
                        endpoint = 'failed'
                    elif (review and row.get('stage') == 'READY_FOR_REVIEW' and
                            review.get('fixture_sha256') == row.get('fixture_sha256') and
                            row.get('fixture_sha256') is not None and hashes and
                            review.get('candidate_hashes') == hashes and
                            isinstance(review.get('goal_satisfied'), bool)):
                        semantic_verified += 1
                        endpoint = 'passed' if review['goal_satisfied'] else 'failed'
            if endpoint == 'unknown' and row.get('gate') != 'STOP':
                reason = 'unsupported_or_unverified' if not supported else 'outcome_not_verified'
                unknown_reasons[reason] = unknown_reasons.get(reason, 0) + 1
            endpoints[endpoint] += 1
            if is_trusted:
                trusted[endpoint] += 1
                if supported and endpoint in {'passed', 'failed'}:
                    oracle = case['oracle']
                    contract = hashlib.sha256(json.dumps({'trusted_files': oracle.get('trusted_files'),
                                                          'command': oracle.get('command')}, sort_keys=True,
                                                         separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
                    trusted_observations.append((contract, endpoint == 'passed'))

        def rates(counts, denominator):
            evaluated = counts['passed'] + counts['failed'] + counts.get('partial', 0)
            return {**counts, 'cases': denominator, 'evaluated': evaluated,
                    'failure_rate_all_cases': counts['failed'] / denominator if denominator else None,
                    'failure_rate_evaluated': counts['failed'] / evaluated if evaluated else None,
                    'exact_goal_unmet_rate_evaluated': (counts['failed'] + counts.get('partial', 0)) / evaluated if evaluated else None}

        measurements = {}
        for name in ('model_calls', 'model_switches', 'tool_calls', 'latency_seconds'):
            observed = [r.get('measurements', {}).get(name) for r in selected]
            known = [v for v in observed if isinstance(v, (int, float)) and not isinstance(v, bool)]
            measurements[name] = {'observed': len(known), 'unknown': len(selected) - len(known),
                                  'total': sum(known) if known else None, 'mean': sum(known) / len(known) if known else None}
        resource_names = sorted({name for row in selected for name in row.get('measurements', {})
                                 if any(token in name for token in ('rss', 'vram', 'memory', 'peak'))})
        resources = {}
        for name in resource_names:
            values = [r.get('measurements', {}).get(name) for r in selected]
            known = [v for v in values if isinstance(v, (float, int)) and not isinstance(v, bool)]
            resources[name] = {'peak': max(known) if known else None, 'observed': len(known), 'unknown': len(selected) - len(known)}
        repairs = [r for r in selected if r.get('repair_observed') is True]
        return {'task_endpoints': rates(endpoints, len(selected)),
                'trusted_task_endpoints': rates(trusted, sum(trusted.values())),
                'trusted_task_pass_clustered_uncertainty': clustered_pass_interval(trusted_observations),
                'executable_cases': executable, 'blocked_cases': blocked_cases, 'unknown_reasons': unknown_reasons,
                'task_failure_rate_executable': endpoints['failed'] / executable if executable else None,
                'conditional_artifact_tests': rates(artifacts, len(selected)),
                'semantic_reviews_verified': semantic_verified, 'semantic_verdicts': semantic_verdicts, 'measurements': measurements,
                'resource_peaks': resources, 'resource_scopes': sorted({r['resource_scope'] for r in selected if r.get('resource_scope')}),
                'repairs': {'observed': len(repairs), 'observation_unknown': sum(r.get('repair_observed') is None for r in selected),
                            'independently_passed': sum(r.get('repair_succeeded') is True for r in repairs),
                            'success_unknown': sum(r.get('repair_succeeded') is None for r in repairs)}}

    arms = {}
    for arm in sorted({r['arm'] for r in rows}):
        selected = [r for r in rows if r['arm'] == arm]
        arms[arm] = group(selected)
        arms[arm]['categories'] = {category: group([r for r in selected if cases[r['case_id']]['category'] == category])
                                  for category in sorted({cases[r['case_id']]['category'] for r in selected})}
    return {'arms': arms, 'worker_suitability_correction': worker_suitability_correction(results),
            'limitations': ['Task pass means trusted artifact validation unless separately bound semantic review is supplied.',
            'Unknown endpoints remain in all-case denominators; evaluated failure rates are conditional.',
            'Resource peaks retain recorded scope and do not imply exclusive device ownership.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('--dataset', type=Path, default=Path(__file__).parent / 'smart-code-router/main.json')
    parser.add_argument('--semantic-reviews', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = analyze(json.loads(args.results.read_text(encoding='utf-8')), json.loads(args.dataset.read_text(encoding='utf-8')),
                     json.loads(args.semantic_reviews.read_text(encoding='utf-8')) if args.semantic_reviews else None)
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    else:
        print(text)


if __name__ == '__main__':
    main()
