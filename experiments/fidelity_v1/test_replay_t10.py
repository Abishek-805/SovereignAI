from experiments.fidelity_v1.replay_t10 import paired_payloads


def test_replay_changes_only_stream_and_preserves_original():
    original = {'stream': True, 'stream_options': {'include_usage': True}, 'tools': [{'x': 1}],
                'chat_template_kwargs': {'enable_thinking': False}, 'max_tokens': 4096}
    pairs = paired_payloads(original)
    assert pairs[0][1] == original
    assert pairs[1][1] == {**original, 'stream': False}
    pairs[1][1]['tools'][0]['x'] = 2
    assert original['tools'][0]['x'] == 1
