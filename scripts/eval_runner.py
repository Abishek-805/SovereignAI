"""Run a declared local answer set and retain raw results for inspection."""
import json
import logging
import sys
import time
from pathlib import Path

from backend.service import Workbench

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def run_evaluation(workbench: Workbench, eval_file: Path, output_file: Path) -> bool:
    tasks = json.loads(eval_file.read_text(encoding='utf-8'))
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('Evaluation file must contain a nonempty task list')
    if len({task['id'] for task in tasks}) != len(tasks):
        raise ValueError('Evaluation task IDs must be unique')
    results = []
    for task in tasks:
        started = time.perf_counter()
        try:
            result = workbench.ask(task['question'], task.get('document_ids'))
            answer = result.get('answer', '')
            status_ok = result.get('status') == task['expected_status']
            terms_ok = all(term.casefold() in answer.casefold() for term in task.get('required_terms', []))
            forbidden_ok = all(term.casefold() not in answer.casefold() for term in task.get('forbidden_terms', []))
            citation_ok = result.get('checks', {}).get('citation_ids_valid') is True
            success = status_ok and terms_ok and forbidden_ok and citation_ok
            results.append({'id': task['id'], 'success': success, 'status_ok': status_ok,
                            'terms_ok': terms_ok, 'forbidden_ok': forbidden_ok,
                            'citation_ids_valid': citation_ok, 'result': result,
                            'latency_seconds': time.perf_counter() - started})
        except Exception as exc:
            logger.exception('Evaluation task %s failed', task['id'])
            results.append({'id': task['id'], 'success': False, 'error': str(exc),
                            'latency_seconds': time.perf_counter() - started})
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps({'task_count': len(tasks),
                                       'passed': sum(item['success'] for item in results),
                                       'results': results}, indent=2), encoding='utf-8')
    return all(item['success'] for item in results)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python -m scripts.eval_runner TASKS.json RESULTS.json')
    raise SystemExit(0 if run_evaluation(Workbench(), Path(sys.argv[1]), Path(sys.argv[2])) else 1)
