from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from backend.contracts import Chunk

@pytest.fixture
def one_chunk():
    return Chunk('c1','d1','v1','a.txt','P-101 vibration threshold 7.1 mm/s.',None,1,1)

@pytest.fixture
def one_vector():
    vector=np.zeros((1,384),dtype=np.float32); vector[0,0]=1
    return vector

@pytest.fixture
def store(tmp_path):
    from rag.store import Store
    return Store(tmp_path/'index.sqlite')
