import threading
import numpy as np
import pytest
from tests.test_service import service
from backend.contracts import WorkbenchError
from rag.ingest import extract,chunk_pages
from rag.retrieve import retrieve
from tests.test_ingest import Characters

@pytest.mark.parametrize('suffix,text',[
    ('.csv','name,score\nAlice,73\nBob,91'),
    ('.tsv','name\tscore\nAlice\t73\nBob\t91'),
    ('.json','[{"name":"Alice","score":73},{"name":"Bob","score":91}]'),
    ('.jsonl','{"name":"Alice","score":73}\n{"name":"Bob","score":91}'),
    ('.yaml','- name: Alice\n  score: 73\n- name: Bob\n  score: 91'),
    ('.xml','<rows><row name="Alice"><score>73</score></row><row name="Bob"><score>91</score></row></rows>')])
def test_structured_formats_preserve_records_and_retrieve_exact_values(service,tmp_path,suffix,text):
    path=tmp_path/('scores'+suffix); path.write_text(text,encoding='utf-16')
    imported=service.import_file(path)
    chunks=service.store.active_chunks([imported['document_id']])
    assert sum(c.retrieval_kind=='schema' for c,_ in chunks)==1
    assert sum(c.retrieval_kind=='lexical' for c,_ in chunks)==2
    assert all(np.linalg.norm(v)==0 for c,v in chunks if c.retrieval_kind=='lexical')
    found=retrieve(service.store,service.embedder,'Bob',[imported['document_id']],limit=1)
    assert found and 'Bob' in found[0].text and '91' in found[0].text


def test_excel_embeds_sheets_not_thousands_of_numeric_rows(service,tmp_path):
    from openpyxl import Workbook
    book=Workbook(); sheet=book.active; sheet.title='Scores'
    sheet.append(['name','score'])
    for i in range(1000): sheet.append([f'Student-{i}',i])
    path=tmp_path/'scores.xlsx'; book.save(path)
    calls=[]; original=service.embedder.encode
    service.embedder.encode=lambda texts,query=False: calls.append(len(texts)) or original(texts,query)
    imported=service.import_file(path)
    assert sum(calls)==1
    found=retrieve(service.store,service.embedder,'Student-987',[imported['document_id']],limit=1)
    assert '987' in found[0].text and 'Student-987' in found[0].text
    from tests.test_api import client_for
    with client_for(service) as client:
        content=client.get('/documents/'+imported['document_id']+'/content').json()
        assert len(content['passages'])==100 and content['passage_total']>100
        linked=client.get('/documents/'+imported['document_id']+'/content',params={'chunk_id':found[0].chunk_id}).json()
        assert any(p['chunk_id']==found[0].chunk_id for p in linked['passages'])
        assert client.get('/documents/'+imported['document_id']+'/content?limit=999').status_code==400


def test_document_management_does_not_wait_for_indexing_and_stale_update_is_rejected(service,tmp_path):
    path=tmp_path/'notes.txt'; path.write_text('Original document')
    doc=service.import_file(path); path.write_text('Replacement text')
    entered=threading.Event(); release=threading.Event(); errors=[]
    original=service.embedder.encode
    def slow(*args,**kwargs):
        entered.set(); assert release.wait(3); return original(*args,**kwargs)
    service.embedder.encode=slow
    def run():
        try: service.import_file(path)
        except WorkbenchError as error: errors.append(error.code)
    thread=threading.Thread(target=run); thread.start()
    try:
        assert entered.wait(2)
        service.remove_document(doc['document_id'],doc['active_hash'])
    finally:
        release.set(); thread.join(3)
    assert errors==['document_conflict'] and not service.documents()


def test_structured_expansion_and_entities_are_bounded(tmp_path):
    for suffix,text in [('.yaml','a: &x [1]\nb: *x'),('.xml','<!DOCTYPE x [<!ENTITY y "secret">]><x>&y;</x>')]:
        path=tmp_path/('bad'+suffix); path.write_text(text)
        with pytest.raises(WorkbenchError): extract(path)


def test_rename_during_indexing_is_preserved_in_new_citations(service,tmp_path):
    path=tmp_path/'notes.txt'; path.write_text('Original text')
    doc=service.import_file(path); path.write_text('Replacement text')
    original=service.embedder.encode
    def rename(*args,**kwargs):
        service.rename_document(doc['document_id'],'renamed.txt',doc['active_hash'])
        return original(*args,**kwargs)
    service.embedder.encode=rename
    updated=service.import_file(path)
    assert updated['display_name']=='renamed.txt'
    assert all(chunk.display_name=='renamed.txt' for chunk,_ in service.store.active_chunks())


@pytest.mark.parametrize('suffix,text',[
    ('.toml','[reading]\nname="Pump"\nvalue=73\ndate=2026-09-30'),
    ('.ini','[reading]\nname=Pump\nvalue=73\npercent=100%'),
    ('.yaml','name: Pump\nvalue: 73\ndate: 2026-09-30')])
def test_structured_configs_and_dates(tmp_path,suffix,text):
    path=tmp_path/('reading'+suffix); path.write_text(text)
    result=extract(path)
    assert 'Pump' in result.pages[0].text and '73' in result.pages[0].text


def test_oversized_header_expansion_is_rejected(tmp_path):
    path=tmp_path/'expansion.csv'
    path.write_text('x'*100000+'\n'+'value\n'*30)
    with pytest.raises(WorkbenchError,match='two million'): extract(path)
