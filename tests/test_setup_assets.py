import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest
import huggingface_hub

spec = importlib.util.spec_from_file_location('setup_assets', Path(__file__).parents[1] / 'setup-assets.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_model_download_is_pinned_atomic_and_reused(tmp_path, monkeypatch):
    cached = tmp_path / 'cache.gguf'
    cached.write_bytes(b'verified model')
    calls = []
    def download(repo, filename, **kwargs):
        calls.append((repo, filename, kwargs))
        return str(cached)
    monkeypatch.setattr(huggingface_hub, 'hf_hub_download', download)
    asset = {'repository':'vendor/model','filename':'model.gguf','path':'vision/model.gguf',
             'revision':'pinned','sha256':setup.digest(cached)}
    setup.install_model(asset, tmp_path)
    setup.install_model(asset, tmp_path)
    assert calls == [('vendor/model', 'model.gguf', {'revision':'pinned'})]
    target = tmp_path / 'models' / asset['path']
    assert target.read_bytes() == cached.read_bytes()
    cached.write_bytes(b'wrong download')
    target.write_bytes(b'keep existing file')
    with pytest.raises(RuntimeError, match='checksum'):
        setup.install_model(asset, tmp_path)
    assert target.read_bytes() == b'keep existing file'


@pytest.mark.parametrize('filename', ['bundle/llama-server.exe', '../llama-server.exe'])
def test_runtime_extraction_is_verified_and_cannot_escape(tmp_path, monkeypatch, filename):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(filename, b'runtime')
    data = buffer.getvalue()
    def retrieve(url, destination):
        destination.write_bytes(data)
    monkeypatch.setattr(setup.urllib.request, 'urlretrieve', retrieve)
    runtime = {'directory':'runtime/pinned','required_files':['llama-server.exe'],
               'archives':[{'url':'https://official.example/runtime.zip','sha256':hashlib.sha256(data).hexdigest()}]}
    if filename.startswith('..'):
        with pytest.raises(RuntimeError, match='Unsafe'):
            setup.install_runtime(runtime, tmp_path)
        assert not (tmp_path / 'runtime').exists()
    else:
        setup.install_runtime(runtime, tmp_path)
        assert (tmp_path / 'runtime/pinned/llama-server.exe').read_bytes() == b'runtime'
        monkeypatch.setattr(setup.urllib.request, 'urlretrieve', lambda *args: pytest.fail('Redownloaded installed runtime'))
        setup.install_runtime(runtime, tmp_path)


def test_runtime_checksum_failure_does_not_publish_files(tmp_path, monkeypatch):
    monkeypatch.setattr(setup.urllib.request, 'urlretrieve', lambda url, path: path.write_bytes(b'bad archive'))
    runtime = {'directory':'runtime/pinned','required_files':['llama-server.exe'],
               'archives':[{'url':'https://official.example/runtime.zip','sha256':'0'*64}]}
    with pytest.raises(RuntimeError, match='checksum'):
        setup.install_runtime(runtime, tmp_path)
    assert not (tmp_path / 'runtime').exists()
