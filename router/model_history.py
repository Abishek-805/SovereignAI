"""Bounded metadata-only outcome aggregates; estimates do not grant authority.

Evidence is supplied by the application's real validation boundary, never inferred
from model text. Minimum samples are a configurable policy, not a calibrated claim.
Single application process writers share a lock; atomic replacement protects readers.
"""
from dataclasses import dataclass, asdict
import json
import math
import os
from pathlib import Path
import re
from threading import RLock
import time
from uuid import uuid4

_LOCK = RLock()
_MEASURES = {'latency_seconds', 'switches', 'load_seconds'}


def _nonnegative(value, *, integer=False):
    return (type(value) is int if integer else type(value) in (int, float)) and value >= 0 and math.isfinite(value)


def _metadata(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:/+@-]{1,192}', value):
        raise ValueError('History context must contain bounded metadata identifiers')
    return value


@dataclass(frozen=True)
class HistoryContext:
    task_type: str
    complexity: str
    language: str
    context_scope: str

    def key(self, model_id):
        return json.dumps([*[_metadata(v) for v in asdict(self).values()], _metadata(model_id)], separators=(',', ':'))


def wilson95(successes, total):
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z*z / total
    centre = (p + z*z / (2*total)) / denominator
    radius = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / denominator
    return [max(0, centre-radius), min(1, centre+radius)]


class ModelHistory:
    def __init__(self, data_dir, *, minimum_samples=20, max_entries=512):
        if type(minimum_samples) is not int or minimum_samples < 1 or type(max_entries) is not int or max_entries < 1:
            raise ValueError('History limits must be positive integers')
        self.path = Path(data_dir) / 'model_history.json'
        self.minimum_samples = minimum_samples
        self.max_entries = max_entries

    def _read(self):
        if not self.path.exists():
            return {'version': 1, 'entries': {}}
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or set(data) != {'version', 'entries'}
                or type(data.get('version')) is not int or data['version'] != 1
                or not isinstance(data.get('entries'), dict)
                or len(data['entries']) > self.max_entries):
            raise ValueError('Unsupported model history schema')
        for key, entry in data['entries'].items():
            try:
                parts = json.loads(key)
                if not isinstance(parts, list) or len(parts) != 5:
                    raise ValueError('Invalid history context key')
                for part in parts:
                    _metadata(part)
                if json.dumps(parts, separators=(',', ':')) != key:
                    raise ValueError('Noncanonical history context key')
                if (not isinstance(entry, dict)
                        or set(entry) != {'successes', 'failures', 'unknown', 'measurements', 'updated_at'}
                        or not all(_nonnegative(entry[name], integer=True) for name in ('successes', 'failures', 'unknown'))
                        or not _nonnegative(entry['updated_at'])
                        or not isinstance(entry['measurements'], dict)
                        or not set(entry['measurements']).issubset(_MEASURES)):
                    raise ValueError('Invalid history entry')
                for name, measure in entry['measurements'].items():
                    if (not isinstance(measure, dict) or set(measure) != {'sum', 'count'}
                            or not _nonnegative(measure['sum'], integer=name == 'switches')
                            or not _nonnegative(measure['count'], integer=True) or measure['count'] < 1):
                        raise ValueError('Invalid history measurement')
            except (TypeError, OverflowError) as error:
                raise ValueError('Invalid history metadata') from error
        return data

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.parent / (uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(data, allow_nan=False), encoding='utf-8')
            for attempt in range(5):
                try:
                    os.replace(temporary, self.path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(.02 * (attempt+1))
        finally:
            temporary.unlink(missing_ok=True)

    def record(self, context, model_id, *, status, container_verified=False,
               exit_code=None, goal_checks_passed=None, latency_seconds=None,
               switches=None, load_seconds=None):
        key = context.key(model_id)
        # Cancelled/blocked tasks cannot become wins, even with a successful
        # preliminary check. A zero exit alone cannot establish the task goal.
        terminal = status in ('completed', 'failed')
        verified = terminal and container_verified is True and type(exit_code) is int
        success = verified and exit_code == 0 and goal_checks_passed is True
        failure = verified and (exit_code != 0 or goal_checks_passed is False)
        with _LOCK:
            data = self._read()
            entry = data['entries'].setdefault(key, {'successes': 0, 'failures': 0, 'unknown': 0, 'measurements': {}})
            entry['successes' if success else 'failures' if failure else 'unknown'] += 1
            for name, value in [('latency_seconds', latency_seconds), ('switches', switches), ('load_seconds', load_seconds)]:
                valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
                if name == 'switches':
                    valid = valid and type(value) is int
                if valid:
                    measure = entry['measurements'].setdefault(name, {'sum': 0, 'count': 0})
                    measure['sum'] += value
                    measure['count'] += 1
            entry['updated_at'] = time.time()
            while len(data['entries']) > self.max_entries:
                oldest = min(data['entries'], key=lambda k: data['entries'][k]['updated_at'])
                del data['entries'][oldest]
            self._save(data)
        return self.lookup(context, model_id)

    def lookup(self, context, model_id):
        with _LOCK:
            entry = self._read()['entries'].get(context.key(model_id), {})
        successes, failures, unknown = [entry.get(k, 0) for k in ('successes', 'failures', 'unknown')]
        count = successes + failures
        total = count + unknown
        result = {'successes': successes, 'failures': failures, 'unknown': unknown,
                  'validated_samples': count, 'observations': total,
                  'success_rate': successes/count if count else None,
                  'coverage': count/total if total else None, 'wilson95': wilson95(successes, count),
                  'minimum_samples': self.minimum_samples}
        for name in ('latency_seconds', 'switches', 'load_seconds'):
            measurement = entry.get('measurements', {}).get(name, {})
            result[name] = measurement['sum']/measurement['count'] if measurement.get('count') else None
            result[name + '_samples'] = measurement.get('count', 0)
        return result

    def sufficient_evidence(self, context, preferred_model, other_model):
        preferred = self.lookup(context, preferred_model)
        other = self.lookup(context, other_model)
        return (preferred['validated_samples'] >= self.minimum_samples
                and other['validated_samples'] >= self.minimum_samples
                and preferred['wilson95'][0] > other['wilson95'][1])
