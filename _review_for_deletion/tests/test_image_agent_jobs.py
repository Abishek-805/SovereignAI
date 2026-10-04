"""Image Agent tasks share jobs, cancellation and intent-first dispatch."""
from io import BytesIO
from pathlib import Path
import threading
import time
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.contracts import WorkbenchError
from backend.jobs import Job
from tests.test_service import service


def image_bytes():
    data=BytesIO();Image.new('RGB',(12,12),'white').save(data,format='PNG');return data.getvalue()


def plan(action, response='Model answer'):
    return {'action':action,'target':'','expression':'','response':response}


def wait_job(client, job_id):
    for _ in range(150):
        state=client.get('/coding/jobs/'+job_id).json()
        if state['state']!='running':return state
        time.sleep(.01)
    raise AssertionError('Job did not finish')


def test_image_job_retains_upload_until_callback_and_cleans_afterwards(service,monkeypatch):
    entered=threading.Event();release=threading.Event();paths=[]
    def execute(goal,path,job=None):
        paths.append(Path(path));assert Path(path).read_bytes()==image_bytes();entered.set()
        assert release.wait(3)
        assert Path(path).is_file()
        return {'status':'completed','answer':'Observed image','plan':{'action':'analyze_image'}}
    monkeypatch.setattr(service,'run_image_agent',execute)
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:
        response=client.post('/agent/vision/jobs',data={'question':'Describe this image'},files={'file':('test.png',image_bytes(),'image/png')})
        assert response.status_code==200,response.text
        assert entered.wait(1);assert paths[0].is_file()
        release.set();assert wait_job(client,response.json()['job_id'])['state']=='completed'
    assert not paths[0].exists()


def test_rejected_busy_image_job_cleans_only_its_own_upload(service,monkeypatch):
    entered=threading.Event();release=threading.Event();paths=[]
    def execute(goal,path,job=None):
        paths.append(Path(path));entered.set();assert release.wait(3)
        return {'status':'completed','answer':'done'}
    monkeypatch.setattr(service,'run_image_agent',execute)
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:
        first=client.post('/agent/vision/jobs',data={'question':'Describe'},files={'file':('one.png',image_bytes(),'image/png')})
        assert entered.wait(1)
        try:
            second=client.post('/agent/vision/jobs',data={'question':'Describe'},files={'file':('two.png',image_bytes(),'image/png')})
            assert second.status_code==409
            assert list((service.settings.data_dir/'uploads').glob('*'))==paths
        finally:release.set()
        wait_job(client,first.json()['job_id'])
    assert not paths[0].exists()


def test_stopped_image_job_cleans_upload_and_has_cancelled_terminal_state(service,monkeypatch):
    paths=[]
    def execute(goal,path,job=None):
        paths.append(Path(path));assert job.cancel.wait(3)
        raise WorkbenchError('cancelled','Image task stopped')
    monkeypatch.setattr(service,'run_image_agent',execute)
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:
        start=client.post('/agent/vision/jobs',data={'question':'Describe'},files={'file':('one.png',image_bytes(),'image/png')}).json()
        assert client.post('/coding/jobs/'+start['job_id']+'/stop').status_code==200
        assert wait_job(client,start['job_id'])['state']=='cancelled'
    assert paths and not paths[0].exists()


def test_image_job_body_limit_rejects_upload_before_creating_tempfile(service):
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:
        response=client.post('/agent/vision/jobs',data={'question':'Describe'},files={'file':('huge.png',b'x'*(5*1024*1024+65537),'image/png')})
    assert response.status_code==413
    assert not list((service.settings.data_dir/'uploads').glob('*'))


def test_attached_image_does_not_force_vision_for_unrelated_question(service,monkeypatch):
    leases=[];service.registry.acquire_lease=lambda value:leases.append(value)
    def understand(goal,documents,files,history,images=None):
        assert images==[{'name':'Attached image'}]
        return plan('answer','Paris is the capital of France.')
    service.model.plan_task=understand
    def unexpected(*args,**kwargs):raise AssertionError('Unrelated question must not read the image')
    monkeypatch.setattr(service,'ask_vision',unexpected)
    result=service.run_image_agent('What is the capital of France?',Path('not-opened.png'))
    assert result['answer']=='Paris is the capital of France.'
    assert leases==['text']
    assert [step['name'] for step in result['steps']]==['plan']


def test_image_intent_delegates_after_releasing_planning_lock(service,monkeypatch):
    service.model.plan_task=lambda *args,**kwargs:plan('analyze_image')
    calls=[]
    def analyze(path,goal,job=None):
        assert not service.ask_lock.locked()
        calls.append((path,goal,job))
        return {'status':'answered','answer':'Image observation',
                'routing':{'capability':'vision','model':'sovereign-vision'}}
    monkeypatch.setattr(service,'ask_vision',analyze)
    job=Job('agent');path=Path('image.png')
    result=service.run_image_agent('Describe this picture',path,job)
    assert calls==[(path,'Describe this picture',job)]
    assert result['plan']['action']=='analyze_image'
    assert result['routing']['capability']=='vision'


def test_stop_during_image_planning_never_runs_visual_inference(service,monkeypatch):
    job=Job('agent')
    def understand(*args,**kwargs):job.cancel.set();return plan('analyze_image')
    service.model.plan_task=understand
    monkeypatch.setattr(service,'ask_vision',lambda *_args,**_kwargs:pytest.fail('Stopped planner must not dispatch vision'))
    with pytest.raises(WorkbenchError) as error:service.run_image_agent('Describe',Path('image.png'),job)
    assert error.value.code=='cancelled'
    assert not service.ask_lock.locked()


def test_visual_action_without_image_requests_input(service):
    service.model.plan_task=lambda *args,**kwargs:plan('analyze_image')
    with pytest.raises(WorkbenchError) as error:service.run_auto_agent('Describe this picture')
    assert error.value.code=='needs_input'
    assert 'Attach an image' in str(error.value)


def test_vision_stop_after_inference_does_not_publish_answer(service,tmp_path,monkeypatch):
    path=tmp_path/'image.png';path.write_bytes(image_bytes());job=Job('agent')
    def analyze(image,question):job.cancel.set();return {'status':'answered','answer':'Late answer'}
    monkeypatch.setattr('backend.service.ask_vision',analyze)
    with pytest.raises(WorkbenchError) as error:service.ask_vision(path,'Describe',job)
    assert error.value.code=='cancelled'
    assert not service.ask_lock.locked()


def test_image_callback_failure_still_cleans_upload(service,monkeypatch):
    paths=[]
    def execute(goal,path,job=None):
        paths.append(Path(path));raise WorkbenchError('generation_format','Controlled failed inference')
    monkeypatch.setattr(service,'run_image_agent',execute)
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:
        start=client.post('/agent/vision/jobs',data={'question':'Describe'},files={'file':('one.png',image_bytes(),'image/png')}).json()
        result=wait_job(client,start['job_id'])
        assert result['state']=='failed'
        assert 'Controlled failed inference' in result['error']
    assert paths and not paths[0].exists()


def test_precancelled_image_agent_does_not_load_model(service):
    job=Job('agent');job.cancel.set()
    service.registry.acquire_lease=lambda *_args:pytest.fail('Stopped image task must not load any model')
    with pytest.raises(WorkbenchError) as error:service.run_image_agent('Describe',Path('unused.png'),job)
    assert error.value.code=='cancelled'
