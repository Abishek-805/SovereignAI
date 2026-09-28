import pytest
from PIL import Image
import base64
from rag.vision import encode_image, ask_vision
from backend.contracts import WorkbenchError

def test_encode_image():
    img = Image.new('RGB', (100, 100), color='red')
    b64 = encode_image(img)
    
    # Verify it is base64
    decoded = base64.b64decode(b64)
    # JPEG magic number
    assert decoded.startswith(b'\xff\xd8\xff')
    
def test_encode_image_resize():
    # Should cap at 1024
    img = Image.new('RGB', (2048, 1000))
    b64 = encode_image(img)
    assert b64


def test_vision_endpoint_rejects_external_url():
    with pytest.raises(WorkbenchError,match='local HTTP'):
        ask_vision(Image.new('RGB',(10,10)), 'read',url='https://example.com')


def test_vision_returns_visible_complete_answer(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': '4'}}]}

    def post(url, *, json, **kwargs):
        assert url == 'http://127.0.0.1:8087/v1/chat/completions'
        assert json['chat_template_kwargs'] == {'enable_thinking': False}
        return Response()

    monkeypatch.setattr('rag.vision.httpx.post', post)
    assert ask_vision(Image.new('RGB', (10, 10)), 'What is 2 + 2?')['answer'] == '4'


def test_vision_rejects_empty_answer(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'finish_reason': 'length', 'message': {'content': ''}}]}

    monkeypatch.setattr('rag.vision.httpx.post', lambda *args, **kwargs: Response())
    with pytest.raises(WorkbenchError, match='empty or incomplete'):
        ask_vision(Image.new('RGB', (10, 10)), 'read')

def test_vision_uses_owned_model_client_and_preserves_cancellation():
    calls=[]
    def request(method,path,**kwargs):
        calls.append((method,path))
        raise WorkbenchError('cancelled','Task stopped')
    with pytest.raises(WorkbenchError) as error:
        ask_vision(Image.new('RGB',(10,10)),'read',request=request)
    assert error.value.code=='cancelled'
    assert calls==[('POST','/v1/chat/completions')]
