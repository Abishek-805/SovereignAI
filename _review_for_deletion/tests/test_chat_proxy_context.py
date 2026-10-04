"""The ordinary model proxy must not silently search private Knowledge."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from tests.test_service import service


@pytest.mark.parametrize('question', ['hi', 'What is your name?',
                                      'What is the capital of France?',
                                      'Explain how a database index works.'])
def test_plain_chat_never_initializes_embedder_or_reads_library(service, monkeypatch, question):
    forwarded = []

    def forbidden(*args, **kwargs):
        raise AssertionError('Plain Chat must not read or embed the Knowledge library')

    monkeypatch.setattr(type(service), 'embedder', property(forbidden))
    monkeypatch.setattr(service, 'documents', forbidden)
    monkeypatch.setattr(service.store, 'active_chunks', forbidden)
    monkeypatch.setattr(service.store, 'lexical', forbidden)

    class Upstream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            forwarded.append((method, url, kwargs['content']))
            return httpx.Response(200, json={'choices': [{'message': {'content': 'Model response'}}]})

    monkeypatch.setattr('backend.app.httpx.AsyncClient', lambda **kwargs: Upstream())
    body = json.dumps({'model': 'sovereign-text', 'messages': [
        {'role': 'system', 'content': 'Answer the question.'},
        {'role': 'user', 'content': question}], 'temperature': .2}).encode()
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        response = client.post('/v1/chat/completions', content=body,
                               headers={'content-type': 'application/json'})
    assert response.status_code == 200
    assert len(forwarded)==1
    assert forwarded[0][:2]==('POST','http://127.0.0.1:8087/v1/chat/completions')
    assert json.loads(forwarded[0][2])=={**json.loads(body),'chat_template_kwargs':{'enable_thinking':False}}
    assert not service.ask_lock.locked()


def test_multimodal_proxy_keeps_image_and_caller_messages_unchanged(service, monkeypatch):
    forwarded = []

    class Upstream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            forwarded.append(kwargs['content'])
            return httpx.Response(200, json={'choices': []})

    monkeypatch.setattr('backend.app.httpx.AsyncClient', lambda **kwargs: Upstream())
    body = json.dumps({'model': 'sovereign-vision', 'messages': [
        {'role': 'user', 'content': [
            {'type': 'text', 'text': 'Describe this attached image.'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AA=='}}]}]}).encode()
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        response = client.post('/v1/chat/completions', content=body,
                               headers={'content-type': 'application/json'})
    assert response.status_code == 200
    assert len(forwarded)==1
    assert json.loads(forwarded[0])=={**json.loads(body),'chat_template_kwargs':{'enable_thinking':False}}
    assert not service.ask_lock.locked()


@pytest.mark.parametrize('identity', ['conversation-1', 'conversation-1::sovereign-text'])
def test_completion_forwards_own_stream_identity(service, monkeypatch, identity):
    sent = []

    class Upstream:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def request(self, method, url, **kwargs):
            sent.append(kwargs['headers'])
            return httpx.Response(200, json={'choices': []})

    monkeypatch.setattr('backend.app.httpx.AsyncClient', lambda **kwargs: Upstream())
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        response = client.post('/v1/chat/completions', json={'messages': []},
                               headers={'X-Conversation-Id': identity})
    assert response.status_code == 200
    assert sent[0]['x-conversation-id'] == identity


def test_stop_forwards_only_selected_conversation_and_does_not_lease_model(service, monkeypatch):
    sent = []
    leases = []
    monkeypatch.setattr(service.registry, 'acquire_lease', lambda *args: leases.append(args))

    class Upstream:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def request(self, method, url, **kwargs):
            sent.append((method, url))
            return httpx.Response(204)

    monkeypatch.setattr('backend.app.httpx.AsyncClient', lambda **kwargs: Upstream())
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        response = client.delete('/v1/stream', params={'conv_id': 'conversation-1::sovereign-text'})
    assert response.status_code == 204
    assert sent == [('DELETE', 'http://127.0.0.1:8087/v1/stream?conv_id=conversation-1%3A%3Asovereign-text')]
    assert not leases


@pytest.mark.parametrize('query', [None, '', '../../slots', 'http://other.example',
                                  'name\nother', 'x' * 257, '*'])
def test_malformed_stop_identity_never_reaches_upstream(service, monkeypatch, query):
    def unexpected(**kwargs):
        raise AssertionError('Invalid identity must not make an upstream request')
    monkeypatch.setattr('backend.app.httpx.AsyncClient', unexpected)
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        response = client.delete('/v1/stream', params={} if query is None else {'conv_id': query})
    assert response.status_code == 400
    assert response.json()['code'] == 'invalid_stream'


def test_duplicate_stream_identity_and_invalid_offset_are_rejected(service, monkeypatch):
    def unexpected(**kwargs):
        raise AssertionError('Invalid request must not reach runtime')
    monkeypatch.setattr('backend.app.httpx.AsyncClient', unexpected)
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        assert client.delete('/v1/stream?conv_id=a&conv_id=b').status_code == 400
        for offset in ('-1', 'abc', '1' * 20):
            assert client.get('/v1/stream', params={'conv_id': 'a', 'from': offset}).status_code == 400


def test_replay_stream_forwards_offset_and_releases_upstream(service, monkeypatch):
    sent = []
    closed = []

    class EventBytes(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"content":"resumed"}\n\n'
            yield b'data: [DONE]\n\n'
        async def aclose(self):
            closed.append('response')

    class Upstream:
        def build_request(self, method, url, **kwargs):
            sent.append((method, url))
            return httpx.Request(method, url, **kwargs)
        async def send(self, request, stream=False):
            assert stream
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=EventBytes())
        async def aclose(self):
            closed.append('client')

    monkeypatch.setattr('backend.app.httpx.AsyncClient', lambda **kwargs: Upstream())
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        response = client.get('/v1/stream', params={'conv_id': 'conversation-1', 'from': 12})
    assert response.status_code == 200
    assert response.content.endswith(b'data: [DONE]\n\n')
    assert sent == [('GET', 'http://127.0.0.1:8087/v1/stream?conv_id=conversation-1&from=12')]
    assert closed == ['response', 'client']
    assert not service.ask_lock.locked()


@pytest.mark.parametrize('identity', ['', '../global', '*', 'x' * 257])
def test_malformed_completion_identity_never_leases_or_forwards(service, monkeypatch, identity):
    def unexpected(*args, **kwargs):
        raise AssertionError('Malformed completion identity must not allocate a model or proxy')
    monkeypatch.setattr(service.registry, 'acquire_lease', unexpected)
    monkeypatch.setattr('backend.app.httpx.AsyncClient', unexpected)
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        response = client.post('/v1/chat/completions', json={'messages': []},
                               headers={'X-Conversation-Id': identity})
    assert response.status_code == 400
    assert not service.ask_lock.locked()
