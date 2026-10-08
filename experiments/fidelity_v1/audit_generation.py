"""Read saved calls without executing models or rewriting outcomes."""
import json
from experiments.fidelity_v1.tasks import OUT
from experiments.fidelity_v1.run_status import write_atomic


def audit():
    rows = []
    for arm in ('native', 'nanobot', 'hermes'):
        for path in sorted((OUT / arm / 'T10').glob('attempt-*/call-*.json')):
            call = json.loads(path.read_text(encoding='utf-8'))
            choice = call.get('response', {}).get('choices', [{}])[0]
            message = choice.get('message', {})
            usage = call.get('response', {}).get('usage', {})
            payload = call['request']
            rows.append({'evidence': str(path.relative_to(OUT)), 'arm': arm, 'call': call['call'],
                         'finish_reason': choice.get('finish_reason'), 'completion_tokens': usage.get('completion_tokens'),
                         'reasoning_tokens': usage.get('completion_tokens_details', {}).get('reasoning_tokens'),
                         'reasoning_tokens_measured': 'reasoning_tokens' in usage.get('completion_tokens_details', {}),
                         'public_content_characters': len(message.get('content') or ''),
                         'tool_calls': len(message.get('tool_calls') or []),
                         'thinking_requested': payload.get('chat_template_kwargs', {}).get('enable_thinking'),
                         'tool_choice': payload.get('tool_choice'), 'output_limit': payload.get('max_tokens')})
    result = {'scope': 'saved T10 calls; no new inference or outcome mutation', 'calls': rows,
              'limitations': ['Reasoning-token split absent unless explicitly provided by runtime.',
                              'Request flags do not prove template/runtime enforcement.',
                              'Initial successful tool calls must not be conflated with later output-limit failure.']}
    write_atomic(OUT / 'reports' / 't10-generation-audit.json', result)
    return result


if __name__ == '__main__':
    result = audit()
    print(json.dumps({'saved_calls': len(result['calls']), 'length_finishes': sum(r['finish_reason'] == 'length' for r in result['calls'])}))
