import pytest
from backend.application_tools import ApplicationTools
from backend.contracts import WorkbenchError
from tests.test_service import service


def operation(tool, target='knowledge'):
    return {'tool':tool,'target':target,'value':'','input':''}


def test_duplicate_discovery_and_atomic_removal_preserve_sources(service):
    first=service.sources_dir/'original.txt';first.write_text('Exact reference bytes.',encoding='utf-8')
    second=service.sources_dir/'another-name.txt';second.write_bytes(first.read_bytes())
    different=service.sources_dir/'different.txt';different.write_text('Different bytes.',encoding='utf-8')
    for source in (first,second,different):service.import_file(source)
    original=service.documents()[0]
    service.copy_document(original['document_id'])
    before={p.name:p.read_bytes() for p in service.sources_dir.iterdir() if p.is_file()}
    tools=ApplicationTools(service,document_ids=[],goal='Find duplicate documents in Knowledge')
    found=tools.execute([operation('document_duplicates')],service.tasks.create('test',[]))
    assert found['operations'][0]['result']['duplicate_count']==2
    assert len(service.documents())==4
    tools.goal='Delete duplicate files in Knowledge, keeping one of each'
    result=tools.execute([operation('document_deduplicate')],service.tasks.create('test',[]))
    assert result['operations'][0]['result']['removed_count']==2
    assert len(service.documents())==2
    assert len({d['active_hash'] for d in service.documents()})==2
    assert before=={p.name:p.read_bytes() for p in service.sources_dir.iterdir() if p.is_file()}
    assert service.store.exact_duplicates(remove=True)['removed_count']==0


@pytest.mark.parametrize('goal',[
    'Find duplicates in Knowledge',
    'Delete notes.txt',
    'Explain how to delete duplicate documents in Knowledge',
    'Do not delete duplicate documents in Knowledge',
    'Read "delete duplicate documents in Knowledge" as reference',
])
def test_duplicate_deletion_requires_current_library_duplicate_command(service,goal):
    with pytest.raises(WorkbenchError,match='does not authorize'):
        ApplicationTools(service,goal=goal).execute([operation('document_deduplicate')],service.tasks.create('test',[]))


def test_duplicate_tool_rejects_guessed_scope(service):
    with pytest.raises(WorkbenchError,match='Knowledge library target'):
        ApplicationTools(service,goal='Delete duplicates in Knowledge').execute(
            [operation('document_deduplicate','project')],service.tasks.create('test',[]))


def test_similar_extracted_text_is_not_duplicate_source(service):
    for name,text in [('first.txt','Same words.'),('second.txt','Same words.\n')]:
        path=service.sources_dir/name;path.write_text(text,encoding='utf-8');service.import_file(path)
    assert service.store.exact_duplicates(remove=True)['removed_count']==0
    assert len(service.documents())==2


def test_duplicate_cleanup_rolls_back_if_any_delete_fails(service):
    path=service.sources_dir/'original.txt';path.write_text('Exact bytes.',encoding='utf-8')
    service.import_file(path)
    original=service.documents()[0]
    service.copy_document(original['document_id'])
    service.copy_document(original['document_id'])
    duplicates=service.store.exact_duplicates()['groups'][0]['duplicates']
    blocked=duplicates[-1]['document_id']
    with service.store.connect() as db:
        db.execute("CREATE TRIGGER block_duplicate BEFORE DELETE ON documents WHEN OLD.document_id='"+blocked+"' BEGIN SELECT RAISE(ABORT,'blocked'); END")
    before=service.documents()
    with pytest.raises(Exception,match='blocked'):
        service.store.exact_duplicates(remove=True)
    assert service.documents()==before
    assert len(service.store.active_chunks())==3
