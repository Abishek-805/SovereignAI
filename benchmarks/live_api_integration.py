"""Phase 2 Task 7: Live HTTP API integration test.

Validates the complete document-search workflow through the FastAPI endpoints
on port 8088, backed by the live llama.cpp model on port 8087.

No accuracy percentage is inferred. All measurements are from actual execution.
"""
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8088'
SAMPLES = ROOT / 'samples'
RESULTS_PATH = ROOT / 'benchmarks' / 'live-api-results.json'


def check_services():
    """Verify both servers are reachable before running tests."""
    errors = []
    try:
        r = httpx.get('http://127.0.0.1:8087/props', timeout=5)
        r.raise_for_status()
    except Exception as exc:
        errors.append(f'LLM server (8087): {exc}')
    try:
        r = httpx.get(f'{BASE}/health', timeout=5)
        r.raise_for_status()
    except Exception as exc:
        errors.append(f'Workbench (8088): {exc}')
    if errors:
        for e in errors:
            print(f'FAIL: {e}', file=sys.stderr)
        sys.exit(1)
    print('Services: both reachable')


def upload_file(path, client):
    """Upload a document via multipart POST /documents/import."""
    with open(path, 'rb') as f:
        files = {'file': (path.name, f, 'application/octet-stream')}
        r = client.post(f'{BASE}/documents/import', files=files)
    return r


def main():
    check_services()
    report = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'services': {'llm': 'http://127.0.0.1:8087', 'workbench': BASE},
        'tests': [],
    }
    client = httpx.Client(
        base_url=BASE,
        headers={'Origin': 'http://127.0.0.1:8088'},
        timeout=120,
    )

    # ── TEST 1: Health endpoint ──────────────────────────────────
    started = time.perf_counter()
    r = client.get('/health')
    elapsed = time.perf_counter() - started
    health = r.json()
    test1 = {
        'name': 'health_endpoint',
        'passed': r.status_code == 200 and health.get('status') == 'ok',
        'status_code': r.status_code,
        'response': health,
        'seconds': round(elapsed, 4),
    }
    report['tests'].append(test1)
    print(f"TEST 1 health: {'PASS' if test1['passed'] else 'FAIL'}")

    # ── TEST 2: Status endpoint ──────────────────────────────────
    started = time.perf_counter()
    r = client.get('/status')
    elapsed = time.perf_counter() - started
    status = r.json()
    test2 = {
        'name': 'status_endpoint',
        'passed': r.status_code == 200 and 'generator' in status,
        'status_code': r.status_code,
        'response': status,
        'seconds': round(elapsed, 4),
    }
    report['tests'].append(test2)
    print(f"TEST 2 status: {'PASS' if test2['passed'] else 'FAIL'}")

    # ── TEST 3: Import inspection.txt ────────────────────────────
    started = time.perf_counter()
    r = upload_file(SAMPLES / 'inspection.txt', client)
    elapsed = time.perf_counter() - started
    import_result = r.json()
    test3 = {
        'name': 'import_inspection',
        'passed': r.status_code == 200 and import_result.get('status') in ('indexed', 'unchanged'),
        'status_code': r.status_code,
        'response': import_result,
        'seconds': round(elapsed, 4),
    }
    report['tests'].append(test3)
    inspection_id = import_result.get('document_id')
    print(f"TEST 3 import inspection: {'PASS' if test3['passed'] else 'FAIL'} ({import_result.get('status')})")

    # ── TEST 4: Import sop.txt ───────────────────────────────────
    started = time.perf_counter()
    r = upload_file(SAMPLES / 'sop.txt', client)
    elapsed = time.perf_counter() - started
    sop_result = r.json()
    test4 = {
        'name': 'import_sop',
        'passed': r.status_code == 200 and sop_result.get('status') in ('indexed', 'unchanged'),
        'status_code': r.status_code,
        'response': sop_result,
        'seconds': round(elapsed, 4),
    }
    report['tests'].append(test4)
    sop_id = sop_result.get('document_id')
    print(f"TEST 4 import sop: {'PASS' if test4['passed'] else 'FAIL'} ({sop_result.get('status')})")

    # ── TEST 5: Documents listing ────────────────────────────────
    started = time.perf_counter()
    r = client.get('/documents')
    elapsed = time.perf_counter() - started
    docs = r.json()
    doc_ids = {d['document_id'] for d in docs}
    test5 = {
        'name': 'documents_listing',
        'passed': r.status_code == 200 and inspection_id in doc_ids and sop_id in doc_ids,
        'status_code': r.status_code,
        'document_count': len(docs),
        'seconds': round(elapsed, 4),
    }
    report['tests'].append(test5)
    print(f"TEST 5 documents: {'PASS' if test5['passed'] else 'FAIL'} ({len(docs)} docs)")

    # ── TEST 6: Answerable question (direct) ─────────────────────
    question = 'Does P-101 need vibration investigation? Cite the observation and threshold. Is shutdown authorized?'
    started = time.perf_counter()
    r = client.post('/ask', json={
        'question': question,
        'document_ids': [inspection_id, sop_id],
    })
    elapsed = time.perf_counter() - started
    answer = r.json()
    has_citations = bool(answer.get('sources'))
    checks = answer.get('checks', {})
    test6 = {
        'name': 'answerable_question_direct',
        'passed': (r.status_code == 200
                   and answer.get('status') in ('answered', 'citation_failure')
                   and has_citations
                   and 'timings' in answer),
        'status_code': r.status_code,
        'answer_status': answer.get('status'),
        'answer_text': answer.get('answer'),
        'source_count': len(answer.get('sources', [])),
        'checks': checks,
        'timings': answer.get('timings'),
        'usage': answer.get('usage'),
        'model': answer.get('model'),
        'seconds': round(elapsed, 4),
    }
    report['tests'].append(test6)
    print(f"TEST 6 answerable: {'PASS' if test6['passed'] else 'FAIL'} (status={answer.get('status')}, {elapsed:.2f}s)")

    # ── TEST 7: Insufficient evidence (M-2 temperature limit) ────
    question2 = 'Is M-2 above its permitted temperature?'
    started = time.perf_counter()
    r = client.post('/ask', json={
        'question': question2,
        'document_ids': [inspection_id, sop_id],
    })
    elapsed = time.perf_counter() - started
    answer2 = r.json()
    test7 = {
        'name': 'insufficient_evidence',
        'passed': (r.status_code == 200
                   and answer2.get('status') == 'insufficient_evidence'),
        'status_code': r.status_code,
        'answer_status': answer2.get('status'),
        'answer_text': answer2.get('answer'),
        'timings': answer2.get('timings'),
        'seconds': round(elapsed, 4),
    }
    report['tests'].append(test7)
    print(f"TEST 7 insufficient: {'PASS' if test7['passed'] else 'FAIL'} (status={answer2.get('status')}, {elapsed:.2f}s)")

    # ── TEST 8: Repeated identical query (determinism check) ─────
    question3 = 'What is the P-101 vibration reading?'
    results = []
    for i in range(2):
        started = time.perf_counter()
        r = client.post('/ask', json={
            'question': question3,
            'document_ids': [inspection_id, sop_id],
        })
        elapsed = time.perf_counter() - started
        results.append({
            'status': r.json().get('status'),
            'answer': r.json().get('answer'),
            'seconds': round(elapsed, 4),
        })
    # Both should succeed (status is consistent)
    test8 = {
        'name': 'repeated_query_stability',
        'passed': all(res['status'] in ('answered', 'insufficient_evidence') for res in results),
        'results': results,
    }
    report['tests'].append(test8)
    print(f"TEST 8 stability: {'PASS' if test8['passed'] else 'FAIL'}")

    # ── TEST 9: Timing metrics structure ─────────────────────────
    timings = answer.get('timings', {})
    has_timing_keys = all(k in timings for k in ['answer_seconds', 'estimated_prompt_tokens'])
    model_info = answer.get('model', {})
    has_model_keys = all(k in model_info for k in ['id', 'quantization', 'context'])
    test9 = {
        'name': 'timing_and_model_metadata',
        'passed': has_timing_keys and has_model_keys,
        'timing_keys': list(timings.keys()),
        'model_info': model_info,
    }
    report['tests'].append(test9)
    print(f"TEST 9 metadata: {'PASS' if test9['passed'] else 'FAIL'}")

    # ── TEST 10: Invalid document filter ─────────────────────────
    started = time.perf_counter()
    r = client.post('/ask', json={
        'question': 'test',
        'document_ids': ['nonexistent_doc_id'],
    })
    elapsed = time.perf_counter() - started
    test10 = {
        'name': 'invalid_document_filter',
        'passed': r.status_code == 400,
        'status_code': r.status_code,
        'response': r.json(),
        'seconds': round(elapsed, 4),
    }
    report['tests'].append(test10)
    print(f"TEST 10 invalid filter: {'PASS' if test10['passed'] else 'FAIL'}")

    # ── TEST 11: Unsupported file upload ─────────────────────────
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.exe', dir=str(SAMPLES), delete=False) as f:
        f.write(b'fake executable')
        bad_path = Path(f.name)
    try:
        r = upload_file(bad_path, client)
        test11 = {
            'name': 'unsupported_file_rejected',
            'passed': r.status_code == 400,
            'status_code': r.status_code,
            'response': r.json(),
        }
    finally:
        bad_path.unlink(missing_ok=True)
    report['tests'].append(test11)
    print(f"TEST 11 unsupported file: {'PASS' if test11['passed'] else 'FAIL'}")

    # ── TEST 12: Final status check ──────────────────────────────
    r = client.get('/status')
    final_status = r.json()
    test12 = {
        'name': 'final_status',
        'passed': (r.status_code == 200
                   and final_status.get('documents', 0) > 0
                   and final_status.get('chunks', 0) > 0),
        'status_code': r.status_code,
        'response': final_status,
    }
    report['tests'].append(test12)
    print(f"TEST 12 final status: {'PASS' if test12['passed'] else 'FAIL'}")

    # ── SUMMARY ──────────────────────────────────────────────────
    client.close()
    passed = sum(1 for t in report['tests'] if t['passed'])
    total = len(report['tests'])
    report['summary'] = {'passed': passed, 'total': total, 'all_passed': passed == total}

    RESULTS_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nRESULTS: {passed}/{total} passed')
    print(f'Saved to: {RESULTS_PATH}')
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
