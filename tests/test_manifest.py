import hashlib
import json
from scripts.manifest_verifier import verify_manifest
from scripts.create_offline_manifest import included_files, ROOT


def test_offline_inventory_uses_built_ui_not_node_modules():
    paths={path.relative_to(ROOT).as_posix() for path in included_files()}
    assert 'frontend/llama-ui/LICENSE' in paths
    assert 'frontend/llama-ui/dist/index.html' in paths
    assert any(path.startswith('frontend/llama-ui/dist/_app/') for path in paths)
    assert 'benchmarks/run_heldout_eval.py' in paths
    assert 'benchmarks/heldout-fixtures/inspection.txt' in paths
    assert 'benchmarks/heldout-results.json' not in paths
    assert not any('/node_modules/' in path or '/.svelte-kit/' in path for path in paths)


def test_manifest_rejects_empty_and_path_escape(tmp_path):
    manifest=tmp_path/'manifest.json'
    manifest.write_text('{"files": []}')
    assert verify_manifest(manifest) is False
    manifest.write_text(json.dumps({'files':[{'path':'../outside.txt','sha256':'0'*64}]}))
    assert verify_manifest(manifest) is False


def test_manifest_validates_size_and_hash(tmp_path):
    target=tmp_path/'a.txt';target.write_bytes(b'ok')
    manifest=tmp_path/'manifest.json'
    entry={'path':'a.txt','sha256':hashlib.sha256(b'ok').hexdigest(),'size':2}
    manifest.write_text(json.dumps({'files':[entry]}))
    assert verify_manifest(manifest) is True
    entry['size']=3;manifest.write_text(json.dumps({'files':[entry]}))
    assert verify_manifest(manifest) is False
