from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from backend.contracts import WorkbenchError
from backend.contracts import Page, Extraction
from backend.settings import Settings
from backend.service import Workbench
from tests.test_answer import FakeModel

class TestEmbedder:
    __test__=False
    revision='emb1'
    def __init__(self):
        self.tokenizer=SimpleNamespace(encode=lambda text,add_special_tokens=False:SimpleNamespace(offsets=[(i,i+1) for i in range(len(text))]))
        self.calls=0
    def encode(self,texts,query=False):
        self.calls+=1
        vectors=np.zeros((len(texts),384),dtype=np.float32); vectors[:,0]=1; return vectors

@pytest.fixture
def service(tmp_path,store):
    model=FakeModel(); model.status=lambda:{'available':True,'is_sleeping':True}
    registry = SimpleNamespace(acquire_lease=lambda model_type: None)
    return Workbench(Settings(data_dir=tmp_path/'data'),store,TestEmbedder(),model,registry)

def test_import_unchanged_and_replace(service,tmp_path):
    path=tmp_path/'a.txt';path.write_text('P-101 limit is 7.1 mm/s.')
    first=service.import_file(path)
    assert first['status']=='indexed'
    assert service.import_file(path)['status']=='unchanged'
    assert service.embedder.calls==1
    path.write_text('P-101 revised limit is 8.0 mm/s.')
    assert service.import_file(path)['status']=='replaced'
    assert service.documents()[0]['document_id']==first['document_id']

def test_busy_and_empty(service):
    assert service.ask('limit?')['status']=='insufficient_evidence'
    assert service.ask('limit?')['routing']=={'capability':'text','model':'sovereign-text'}
    service.ask_lock.acquire()
    try:
        with pytest.raises(WorkbenchError) as error: service.ask('limit?')
        assert error.value.code=='busy'
    finally: service.ask_lock.release()


def test_text_and_vision_use_distinct_capability_routes(service,tmp_path,monkeypatch):
    from PIL import Image
    leases=[]
    service.registry.acquire_lease=lambda capability: leases.append(capability)
    service.ask('What is the limit?')
    image=tmp_path/'label.png';Image.new('RGB',(20,20),'white').save(image)
    monkeypatch.setattr('backend.service.ask_vision',lambda img,question:{'status':'answered','answer':'P-101'})
    result=service.ask_vision(image,'What is printed?')
    assert leases==['text','vision']
    assert result['routing']=={'capability':'vision','model':'sovereign-vision'}


def test_coding_workflow_requires_verified_sandbox(service):
    with pytest.raises(WorkbenchError) as error:
        service.create_csv_coding_demo()
    assert error.value.code=='sandbox_unavailable'
    record=service.settings.data_dir/'sandbox-validation.json'
    record.parent.mkdir(parents=True,exist_ok=True)
    record.write_text('{"image_id":"sha256:fake","checks":{"normal_execution":true}}')
    with pytest.raises(WorkbenchError) as error:
        service.create_csv_coding_demo()
    assert error.value.code=='sandbox_unavailable'

def test_failure_keeps_old(service,tmp_path):
    path=tmp_path/'a.txt';path.write_text('limit 7.1')


def test_ocr_observations_saved_with_source_version(service,tmp_path,monkeypatch):
    import hashlib
    path=tmp_path/'scan.pdf';path.write_bytes(b'%PDF synthetic stub')
    def fake_extract(path,*args):
        return Extraction([Page('P-101 8.2 mm/s',2,method='ocr',confidence=92.0,image_hash='imagehash',
                                observations=({'text':'P-101','confidence':92.0,'box':(1,2,3,4),'engine':'rapidocr-onnx'},))],[], hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr('backend.service.extract',fake_extract)
    result=service.import_file(path)
    metadata=service.settings.data_dir/'ocr'/(result['active_hash']+'.json')
    assert metadata.is_file()
    assert 'rapidocr-onnx' in metadata.read_text()
    assert service.store.active_chunks()[0][0].extraction_method=='ocr'
    service.import_file(path); old=service.documents()[0]['active_hash']
    path.write_text('limit 8.2')
    def fail(*args,**kwargs): raise WorkbenchError('embedding_unavailable','failed')
    service.embedder.encode=fail
    with pytest.raises(WorkbenchError): service.import_file(path)
    assert service.documents()[0]['active_hash']==old

def test_unknown_selection_and_empty_question(service):
    with pytest.raises(WorkbenchError): service.ask('limit?',['missing'])
    with pytest.raises(WorkbenchError): service.ask('   ')
    assert service.status()['generator']['is_sleeping'] is True
