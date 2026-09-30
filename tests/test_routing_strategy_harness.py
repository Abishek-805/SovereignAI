"""Fixture-only verification: this suite must never invoke a model or Docker."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def harness():
    path=Path(__file__).resolve().parents[1]/'benchmarks/routing-strategy-comparison.py'
    spec=importlib.util.spec_from_file_location('strategy_harness',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_manifest_is_representative_and_honestly_disabled():
    module=harness()
    cases,fixture,digest=module.manifest()
    description=module.describe(cases,list(enumerate(cases)),digest)
    assert len(cases)>=30 and fixture
    assert description['inference_performed'] is False
    assert description['classifier']['production_enabled'] is False
    assert description['oracle']['latency_seconds'] is None
    assert description['oracle']['status']=='unavailable'
    assert {'edit_code','search_documents','answer','analyze_image'} <= description['expected_action_counts'].keys()
    assert len({row['case_id'] for row in description['tasks']})==len(cases)


def test_dry_manifest_cannot_call_runtime(monkeypatch):
    module=harness()
    monkeypatch.setattr(module,'check_idle',lambda:pytest.fail('Dry run touched runtime'))
    monkeypatch.setattr(module.sys,'argv',['routing-strategy-comparison.py'])
    module.main()


def test_raw_snapshot_detects_binary_changes():
    module=harness()
    files={'assets/photo.png':b'\x89PNG\0original','notes.md':b'notes'}
    service=SimpleNamespace(coding=SimpleNamespace(raw_files=lambda _:dict(files)))
    before=module.file_snapshot(service,'fixture')
    files['assets/photo.png']=b'\x89PNG\0modified'
    after=module.file_snapshot(service,'fixture')
    assert before['assets/photo.png']!=after['assets/photo.png']
    assert before['notes.md']==after['notes.md']

def test_code_benchmark_explicitly_accepts_validated_staged_changes(tmp_path):
    from workflows.coding_workspace import CodingWorkspace
    from router.task_ledger import TaskLedger
    from tests.test_coding_project import ProjectModel, Sandbox
    work=CodingWorkspace(tmp_path); wid=work.create('Fixture')['workspace_id']
    work.write(wid,'notes.md','# Working notes\nOld item.\n')
    module=harness(); service=SimpleNamespace(coding=work,accept_coding_task=work.accept)
    before=module.file_snapshot(service,wid)
    task=work.run_project(wid,'notes.md','Replace Old item. with Verified item.',
        ProjectModel({'scope':'existing_files','operations':[{'action':'edit','path':'notes.md','reason':'Requested change'}]},
            '# Working notes\nVerified item.\n'),Sandbox(),TaskLedger(tmp_path))
    assert module.file_snapshot(service,wid)==before
    _,checks=module.validate(service,wid,{'action':'edit_code','question':'Edit notes.md','needle':None},
        {'plan':{'action':'edit_code'},'result':task},before)
    assert checks['canonical_unchanged_before_accept'] and checks['explicit_accept'] and checks['code_valid']
    assert work.read(wid,'notes.md')['content']=='# Working notes\nVerified item.\n'


@pytest.mark.parametrize('answer,valid',[
    ('The valve is red [S1].',True),
    ('The valve is red [S1, S2].',True),
    ('The valve is red [S9].',False),
    ('The valve is red.',False),
])
def test_retrieval_validates_citations_not_just_any_source(answer,valid):
    module=harness()
    service=SimpleNamespace(documents=lambda:[{'document_id':'fixture-doc','active_hash':'version'}],
        coding=SimpleNamespace(raw_files=lambda _:{}))
    result={'plan':{'action':'search_documents'},'answer':answer,'result':{'sources':[
        {'label':label,'document_id':'fixture-doc','version_hash':'version'} for label in ('S1','S2')]}}
    _,checks=module.validate(service,'fixture',{'action':'search_documents','question':'Find valve','needle':None},result,{})
    assert checks['source_identity_valid'] is True
    assert checks['answer_cites_returned_labels'] is valid
    assert checks['semantic_support_human_review'] is None


def test_small_manifest_cannot_be_passed_off_as_full_evaluation():
    module=harness()
    with pytest.raises(ValueError,match='thirty'):
        module.describe([{'question':'hi','action':'answer','category':'greeting'}],[], 'hash')


@pytest.mark.parametrize('strategy',['always_text','current_mapping'])
@pytest.mark.parametrize('unsafe',['license','pressure','image'])
def test_fixed_comparators_keep_production_hard_admission(strategy,unsafe):
    from router.model_registry import ModelSpec
    spec=ModelSpec('text','fixture','fixture.gguf',license_id='fixture-license',
        license_reviewed=unsafe!='license',license_reference='fixture-reviewed')
    registry=SimpleNamespace(specs={'text':spec},installed=lambda _:True,runtime_available=lambda _:True)
    router=harness().fixed_router(registry,strategy)
    from router.resource_admission import ResourceSnapshot
    snapshot=ResourceSnapshot(1,1 if unsafe=='pressure' else 10000,5000,6000,'0','fixture')
    decision=router.select_model('vision' if unsafe=='image' else 'text',
        modality='image' if unsafe=='image' else 'text',resource_snapshot=snapshot)
    assert decision.selected_model is None
    assert decision.selection_policy=='fixed_mapping_with_production_hard_admission'
