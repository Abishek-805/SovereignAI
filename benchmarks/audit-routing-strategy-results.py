"""Post-run validator audit. Never rewrites frozen samples or their timings.

Default: read-only inspection of suite-owned results/fixtures, write a separate
audited-results.json. Optional --execute-code-checks runs additional multiplication
inputs in the verified Docker sandbox ONLY after the suite reports complete.
No model inference, Workbench creation, or user project access is performed.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARTIFACT_ROOT = ROOT / 'benchmarks/routing-strategy-artifacts'
STRATEGIES = {'always_text', 'current_mapping', 'proposed'}
ANSWER_ACTIONS = {'answer', 'search_documents', 'create_report', 'read_files', 'inspect_code', 'clarify'}


def bounded_path(path, root, must_exist=True):
    path, root = Path(path).absolute(), Path(root).resolve()
    if not path.resolve().is_relative_to(root):
        raise ValueError('Path leaves the suite-owned folder: ' + str(path))
    current = path
    while current != root:
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('Linked suite paths are not permitted: ' + str(current))
        if current == current.parent:
            raise ValueError('Invalid suite path')
        current = current.parent
    if must_exist and not path.exists():
        raise ValueError('Missing suite path: ' + str(path))
    return path


def expected_documents(strategy_root):
    database = bounded_path(strategy_root / 'data/index.sqlite', strategy_root)
    uri = 'file:' + quote(database.as_posix(), safe='/:') + '?mode=ro'
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute('PRAGMA query_only=ON')
        documents = connection.execute('SELECT document_id,display_name,active_hash FROM documents').fetchall()
    finally:
        connection.close()
    return {row[0]: {'display_name': row[1], 'version_hash': row[2]} for row in documents if row[1] == 'fixture.txt'}


def docx_check(strategy_root, result, question):
    nested = result.get('result') or {}
    task_id = nested.get('task_id') or result.get('task_id')
    if not isinstance(task_id, str) or not re.fullmatch('[a-f0-9]{32}', task_id):
        return {'docx_readback': False, 'reason': 'Missing valid artifact task ID'}
    directory = bounded_path(strategy_root / 'outputs' / task_id, strategy_root)
    documents = list(directory.glob('*.docx'))
    if not documents:
        return {'docx_readback': False, 'reason': 'No DOCX artifact'}
    bodies = []
    for path in documents:
        bounded_path(path, strategy_root)
        with zipfile.ZipFile(path) as archive:
            entry = archive.getinfo('word/document.xml')
            if entry.file_size > 10_000_000:
                raise ValueError('DOCX XML exceeds audit bound')
            tree = ET.fromstring(archive.read(entry))
        paragraphs = [''.join(p.itertext()).strip() for p in tree.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')]
        # Exclude question/title and the Sources appendix, which cannot establish
        # that the generated report body actually addresses the requested facts.
        body = []
        for paragraph in paragraphs:
            if paragraph == 'Sources': break
            if paragraph in ('Document report', question) or paragraph.startswith('AI-assisted draft.'):
                continue
            if paragraph: body.append(paragraph)
        bodies.append('\n'.join(body))
    substantive = all(len(body.split()) >= 8 for body in bodies)
    facts = ['3.6', '4.0'] if 'approval note' in question.lower() else ['3.6'] if 'inspection' in question.lower() else []
    return {'docx_readback': True, 'substantive_report_body': substantive,
            'requested_numeric_facts_in_body': all(all(fact in body for fact in facts) for body in bodies),
            'fact_check_scope': facts, 'human_semantic_support': None}


def citation_check(result, expected):
    nested = result.get('result') or {}
    sources = nested.get('sources') or []
    answer = nested.get('answer') or result.get('answer') or ''
    labels = {source.get('label') for source in sources if isinstance(source, dict)}
    references = set()
    for bracket in re.findall(r'\[([^\]]+)\]', answer):
        references.update(re.findall(r'\bS\d+\b', bracket))
    identities = bool(expected) and bool(sources) and all(isinstance(source, dict) and source.get('document_id') in expected
        and source.get('version_hash') == expected[source['document_id']]['version_hash'] for source in sources)
    return {'source_identity_and_version_valid': identities,
            'answer_cites_returned_labels': bool(references) and references.issubset(labels),
            'referenced_labels': sorted(references), 'expected_document_ids': sorted(expected),
            'semantic_support_human_review': None}


def code_check(strategy_root):
    """Copy bounded, suite-owned JS bytes into existing pinned isolated Docker."""
    config_path = bounded_path(strategy_root / 'data/sandbox-validation.json', strategy_root)
    config = json.loads(config_path.read_text(encoding='utf-8'))
    required = {'normal_execution', 'network_blocked', 'root_read_only', 'input_read_only', 'non_root'}
    if not all(config.get('checks', {}).get(key) is True for key in required):
        raise ValueError('Pinned sandbox isolation record did not pass')
    projects = bounded_path(strategy_root / 'projects', strategy_root)
    targets = list(projects.glob('*/multiply.js'))
    if len(targets) != 1:
        raise ValueError('Expected exactly one suite-owned multiply.js')
    target = bounded_path(targets[0], strategy_root)
    payload = target.read_bytes()
    if len(payload) > 128_000:
        raise ValueError('Suite multiply.js exceeds bounded size')
    from router.sandbox import CodeSandbox
    sandbox = CodeSandbox('docker', image_id=config.get('image_id'), task_root=strategy_root / 'audit-code-tasks')
    inputs = [[6, 7, 42], [0, 9, 0], [-3, 5, -15], [2.5, 4, 10], [7, 1, 7]]
    command = "const m=require('/input/multiply.js');const cases=" + json.dumps(inputs) + ";if(typeof m!=='function')throw Error('not function');for(const [a,b,want]of cases){const got=m(a,b);if(typeof got!=='number'||Math.abs(got-want)>1e-9)throw Error(JSON.stringify({a,b,want,got}));}console.log('AUDIT_MULTIPLY_PASS');"
    script = "import subprocess,sys\nsys.exit(subprocess.call(['node','-e'," + repr(command) + "]))\n"
    started = time.perf_counter()
    result = sandbox.execute(script, timeout=30, input_files={'multiply.js': payload})
    return {'executed': result.executed, 'passed': result.executed and result.exit_code == 0 and 'AUDIT_MULTIPLY_PASS' in result.stdout,
            'inputs': inputs, 'source_sha256': hashlib.sha256(payload).hexdigest(), 'exit_code': result.exit_code,
            'stdout': result.stdout, 'stderr': result.stderr, 'audit_validation_seconds': time.perf_counter() - started,
            'scope': 'Additional post-run tests; not part of original workflow timing'}


def failure_category(row, checks):
    job = row.get('job') or {}
    result = job.get('result') or {}
    decision = (result.get('routing') or {}).get('decision') or (job.get('routing') or {}).get('decision') or {}
    error = str(job.get('error') or '')
    serialized = json.dumps(decision)
    intent = row.get('actual_action') or decision.get('intent')
    if job.get('state')=='completed' and intent is not None and intent!=row.get('expected_action'):
        return 'router_failure','Recorded completed action differs from the expected task action',intent
    if any(value is False for value in checks.values()) and job.get('state') == 'completed':
        if checks.get('source_identity_and_version_valid') is False or checks.get('answer_cites_returned_labels') is False:
            return 'evidence_failure', 'Completed output failed stronger citation identity/reference checks', intent
        return 'validation_failure', 'Completed output failed post-run content validator', intent
    if job.get('state') != 'completed':
        if 'unsupported_modality' in error or (decision.get('selected_model') is None and 'unsupported_modality' in serialized):
            return 'modality_failure', 'Explicit unsupported-modality rejection in frozen decision/error', intent
        if 'sandbox_unavailable' in serialized or 'isolation verifier' in error:
            return 'validation_setup_failure', 'Suite did not provide verified sandbox record', intent
        if 'artifact_publish' in serialized or '[WinError 5]' in error:
            return 'artifact_publication_failure', 'Recorded Windows artifact publication failure; no completed report was published', intent
        if 'grounded report' in error:
            return 'evidence_failure', 'Frozen report error explains missing grounded evidence', intent
        if 'No model satisfies' in error or 'cannot satisfy' in error:
            return 'model_admission_failure', 'Recorded selection/admission refusal; not conflated with semantic routing', intent
        if intent is not None and intent != row.get('expected_action'):
            return 'router_failure', 'Recorded intent differs from expected action', intent
        return 'model_or_execution_failure', 'No demonstrated intent mismatch; raw error retained for review', intent
    if intent != row.get('expected_action'):
        return 'router_failure', 'Completed recorded intent differs from expected action', intent
    if not row.get('success'):
        return row.get('failure_category') or 'model_failure', 'Original validation failure retained', intent
    return None, 'Original pass also satisfies applicable post-run checks; human review unresolved', intent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True, type=Path)
    parser.add_argument('--execute-code-checks', action='store_true')
    args = parser.parse_args()
    folder = bounded_path(args.folder, ARTIFACT_ROOT)
    if folder.parent.resolve() != ARTIFACT_ROOT.resolve() or not re.fullmatch('[a-f0-9]{32}', folder.name):
        parser.error('folder must be a direct suite-owned UUID directory')
    source = bounded_path(folder / 'results.json', folder)
    frozen_bytes = source.read_bytes()
    original = json.loads(frozen_bytes)
    if args.execute_code_checks and original.get('metadata', {}).get('complete') is not True:
        parser.error('Additional Docker tests require a completed benchmark and an exclusive post-run window')
    rows, document_maps, code_results = [], {}, {}
    for row in original.get('rows', []):
        strategy = row.get('strategy')
        if strategy not in STRATEGIES:
            raise ValueError('Unknown strategy: ' + str(strategy))
        strategy_root = bounded_path(folder / strategy, folder)
        result = (row.get('job') or {}).get('result') or {}
        nested = result.get('result') or {}
        checks = {}
        errors = []
        if result and row.get('expected_action') in ANSWER_ACTIONS:
            checks['nonempty_answer'] = bool(str(nested.get('answer') or result.get('answer') or '').strip())
        if result and row.get('expected_action') in {'search_documents', 'create_report'}:
            try:
                if strategy not in document_maps: document_maps[strategy] = expected_documents(strategy_root)
                checks.update(citation_check(result, document_maps[strategy]))
            except Exception as exc:
                checks['citation_audit_completed'] = False; errors.append(str(exc))
        if result and row.get('expected_action') == 'create_report':
            try: checks.update(docx_check(strategy_root, result, row.get('task', '')))
            except Exception as exc:
                checks['docx_audit_completed'] = False; errors.append(str(exc))
        if row.get('task_id') == 'e30':
            if args.execute_code_checks:
                if strategy not in code_results:
                    try: code_results[strategy] = code_check(strategy_root)
                    except Exception as exc: code_results[strategy] = {'executed': False, 'passed': False, 'error': str(exc)}
                checks['additional_multiplication_tests_passed'] = code_results[strategy]['passed']
            else:
                checks['additional_multiplication_tests_passed'] = None
        category, reason, intent = failure_category(row, checks)
        derived = copy.deepcopy(row)
        derived['audit'] = {'checks': checks, 'errors': errors, 'recorded_intent': intent,
                            'success': bool(row.get('success')) and not any(value is False for value in checks.values()),
                            'failure_category': category, 'classification_provenance': reason, 'human_review': None}
        rows.append(derived)
    output = {'raw_results_sha256': hashlib.sha256(frozen_bytes).hexdigest(), 'raw_metadata': original.get('metadata'),
              'audited_at_unix': time.time(), 'rows': rows, 'additional_code_validation': code_results,
              'validator_limits': ['No semantic support, general-answer quality, report approval safety, or vision human review is inferred',
                                   'Nonempty text and requested numeric presence are necessary checks, not semantic quality proof',
                                   'Original execution samples and timings are unchanged; additional code-check timing is separate',
                                   'Errors without a recorded intent are unresolved model/execution failures, not proven routing failures',
                                   'Repeated latency, production-context peaks, competing eligible alternatives and oracle remain unavailable'],
              'human_review_complete': False}
    bounded_path(folder / 'audited-results.json', folder, must_exist=False).write_text(json.dumps(output, indent=2), encoding='utf-8')
    print('Wrote separate audit: ' + str(folder / 'audited-results.json'))


if __name__ == '__main__':
    main()
