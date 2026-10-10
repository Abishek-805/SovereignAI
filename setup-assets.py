"""Install pinned inference assets before startup; never start or stop services."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def install_model(asset, root=ROOT):
    from huggingface_hub import hf_hub_download
    target = root / 'models' / asset['path']
    if target.is_file() and digest(target) == asset['sha256']:
        print('Verified ' + asset['path'], flush=True)
        return
    print('Downloading ' + asset['path'], flush=True)
    downloaded = Path(hf_hub_download(asset['repository'], asset['filename'], revision=asset['revision']))
    if digest(downloaded) != asset['sha256']:
        raise RuntimeError('Model checksum failed: ' + asset['path'])
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        pending = Path(handle.name)
    try:
        shutil.copyfile(downloaded, pending)
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


def install_runtime(spec, root=ROOT):
    target = root / spec['directory']
    if all((target / name).is_file() for name in spec['required_files']):
        print('Existing llama.cpp runtime present; reused.', flush=True)
        return
    with tempfile.TemporaryDirectory() as directory:
        stage = Path(directory)
        for index, asset in enumerate(spec['archives']):
            archive = stage / f'{index}.zip'
            print('Downloading ' + asset['url'].rsplit('/', 1)[-1], flush=True)
            urllib.request.urlretrieve(asset['url'], archive)
            if digest(archive) != asset['sha256']:
                raise RuntimeError('Runtime archive checksum failed')
            with zipfile.ZipFile(archive) as bundle:
                for entry in bundle.infolist():
                    if entry.is_dir():
                        continue
                    name = Path(entry.filename).name
                    if '\\' in entry.filename or '..' in Path(entry.filename).parts or Path(entry.filename).is_absolute():
                        raise RuntimeError('Unsafe runtime archive path')
                    destination = stage / 'files' / name
                    destination.parent.mkdir(exist_ok=True)
                    if destination.exists():
                        raise RuntimeError('Duplicate runtime archive filename: ' + name)
                    with bundle.open(entry) as source, destination.open('wb') as handle:
                        shutil.copyfileobj(source, handle)
        if not all((stage / 'files' / name).is_file() for name in spec['required_files']):
            raise RuntimeError('Runtime archive is missing required binaries')
        target.mkdir(parents=True, exist_ok=True)
        for source in (stage / 'files').iterdir():
            if not (target / source.name).exists():
                shutil.copyfile(source, target / source.name)


def main():
    manifest = json.loads((ROOT / 'model-assets.json').read_text(encoding='utf-8'))
    for asset in manifest['models']:
        install_model(asset)
    install_runtime(manifest['runtime'])
    module = importlib.util.spec_from_file_location('embedding_setup', ROOT / 'setup-embeddings.py')
    embeddings = importlib.util.module_from_spec(module)
    module.loader.exec_module(embeddings)
    embeddings.main()
    print('All inference assets ready. No service was restarted.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit(f'Asset setup failed: {error}. Check internet, disk space and model access; rerun to resume.') from error
