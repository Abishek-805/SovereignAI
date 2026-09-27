from pathlib import Path
import numpy as np
import pytest
from backend.contracts import WorkbenchError
from backend.settings import Settings
from rag.embedding import Embedder, normalize_output

def test_missing_assets_fail_locally(tmp_path):
    with pytest.raises(WorkbenchError, match='Local embedding') as error:
        Embedder(tmp_path)
    assert error.value.code == 'embedding_unavailable'

def test_pooling_and_normalization():
    output = np.ones((2, 4, 384), dtype=np.float32)
    result = normalize_output(output)
    assert result.shape == (2, 384)
    assert np.allclose(np.linalg.norm(result, axis=1), 1)

@pytest.mark.parametrize('value', [np.zeros((1,384)), np.full((1,384), np.nan), np.ones((1,12))])
def test_invalid_vectors_rejected(value):
    with pytest.raises(WorkbenchError):
        normalize_output(value)

def test_paths_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert Settings().root == Path(__file__).resolve().parents[1]
