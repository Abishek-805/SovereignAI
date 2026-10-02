import pytest
from router.coding_router import classify_coding_request
from router.request_normalization import normalize_request

@pytest.mark.parametrize('prompt,task',[
    ('Write a Python script','CODE_GENERATION'),('Rename this variable','EDIT'),
    ('refactor thi function','REFACTOR'),('debug thsi','DEBUG'),
    ('Implement pagination','IMPLEMENT'),('Review this code','REVIEW'),
    ('Add tests for this function','TEST'),('Complete the next line','AUTOCOMPLETE')])
def test_clear_coding_families(prompt,task):
    result=classify_coding_request(prompt,{'active_file':'main.py','workspace_available':True})
    assert result.task_type==task
    assert result.steps==('code',)
    assert not result.mutation_authorized

def test_simple_explanation_and_complex_repository_change():
    assert classify_coding_request('Explain this function',{'active_file':'main.py'}).steps==('lightweight',)
    result=classify_coding_request('Refactor authentication across the project',{'workspace_available':True})
    assert result.task_type=='MULTI_FILE_CHANGE'
    assert result.complexity=='complex' and result.steps==('reasoning','code')

def test_visual_input_is_metadata_and_protected_mentions_are_not_intent():
    assert classify_coding_request('Fix the UI',{'visual_input_present':True}).steps==('vision','code')
    assert classify_coding_request('Explain the word "refactor"').steps==('lightweight',)
    assert classify_coding_request('Use this screenshot').steps!=('vision','code')

def test_followup_uses_operational_state_or_abstains():
    assert classify_coding_request('fix that').needs_clarification
    result=classify_coding_request('fix that',{'previous_task_type':'DEBUG','previous_validation_failed':True})
    assert result.task_type=='REPAIR' and result.steps==('code',)
    assert classify_coding_request('continue',{'previous_task_type':'EDIT'}).task_type=='EDIT'

@pytest.mark.parametrize('literal',[
    '`creat`','"teh"','creat.py','C:/creat/teh.py','https://teh.test/creat',
    'teh@example.com','creat_value','creatValue','```python\ncreat = "teh"\n```',
    '\ncreat = 1\nprint(creat)', '\ndef creat(teh):\n    return teh'])
def test_normalization_preserves_literals_and_source(literal):
    result=normalize_request('fix teh error '+literal)
    assert result.normalized=='fix the error '+literal
    assert result.original=='fix teh error '+literal

def test_noisy_prose_and_negative_command():
    assert normalize_request('creat py file; fix teh error; refactor thi function; debug thsi').normalized==(
        'create py file; fix the error; refactor this function; debug this')
    result=classify_coding_request('Do not edit this code; explain it',{'active_file':'main.py'})
    assert result.task_type=='EXPLAIN' and not result.mutation_authorized

def test_explicit_following_edit_takes_precedence_over_explanation():
    result=classify_coding_request('Explain app.py and then fix the bug',{'active_file':'app.py'})
    assert result.task_type=='DEBUG' and result.steps==('code',)
    assert not result.mutation_authorized
    assert classify_coding_request('Explain how to fix this function',{'active_file':'app.py'}).task_type=='EXPLAIN'


def test_visual_multifile_change_keeps_required_modality():
    result=classify_coding_request('Fix app.py and styles.css using this screenshot',{'visual_input_present':True,'requested_files':['app.py','styles.css'],'workspace_available':True})
    assert result.task_type=='VISION_ASSISTED_CODE'
    assert result.steps==('vision','code')
    assert result.features['modality']=='image'
def test_visual_restore_uses_same_explicit_edit_guard():
    from router.coding_router import classify_coding_request
    context={'visual_input_present':True,'active_file':'index.html'}
    assert classify_coding_request('Restore the layout in index.html',context).steps==('vision','code')
    assert classify_coding_request('Explain how to restore the layout in index.html',context).steps==('vision',)
    assert classify_coding_request('Do not restore the layout in index.html',context).steps==('vision',)
