from dataclasses import replace
import numpy as np
import pytest
from rag.retrieve import rrf,fts_query,retrieve,document_scope_for_question

def test_filename_reference_scopes_selected_library():
    documents=[{'document_id':'a','display_name':'other-report.pdf'},
               {'document_id':'b','display_name':'24ALR001_ABISHEK M.pdf'}]
    assert document_scope_for_question(documents,'Tell me what 24alr001 pdf says',['a','b'])==['b']
    assert document_scope_for_question(documents,'Tell me what 24alr001 pdf says',[])==['b']
    assert document_scope_for_question(documents,'Summarize all documents',['a','b'])==['a','b']

def test_rank_agreement():
    assert rrf([['a','b'],['b','c']])[0]=='b'
    assert rrf([['z'],['a']])==['a','z']

def test_safe_query():
    assert fts_query('P-101 " OR *')=='"P" OR "101" OR "OR"'
    assert fts_query('***')==''

class FakeEmbedder:
    revision='emb1'
    def encode(self,texts,query=False):
        v=np.zeros((len(texts),384),dtype=np.float32); v[:,0]=1; return v

def test_empty_never_embeds(store):
    assert retrieve(store,None,'anything')==[]

def test_numeric_conflicts_are_preserved(store,one_chunk,one_vector):
    text='For pump P-101 the approved vibration alarm threshold during normal continuous operation is 7.1 mm/s.'
    first=replace(one_chunk,text=text,page=None,line_start=1,line_end=1)
    second=replace(first,chunk_id='conflict',text=text.replace('7.1','9.0'),line_start=101,line_end=101)
    store.publish('d1','a','a','v1',[first,second],np.vstack([one_vector,one_vector]),'emb1',[])
    assert len(retrieve(store,FakeEmbedder(),'P-101 threshold'))==2

def test_scope_paraphrase_and_identifiers(store,one_chunk,one_vector):
    store.publish('d1','a','a','v1',[one_chunk],one_vector,'emb1',[])
    other=replace(one_chunk,chunk_id='c2',document_id='d2',text='P-999 apples')
    other_vector=np.zeros((1,384),dtype=np.float32); other_vector[0,1]=1
    store.publish('d2','b','b','v1',[other],other_vector,'emb1',[])
    assert retrieve(store,FakeEmbedder(),'What shaking level requires attention?')[0].document_id=='d1'
    assert retrieve(store,FakeEmbedder(),'P-101')[0].document_id=='d1'
    assert all(c.document_id=='d2' for c in retrieve(store,FakeEmbedder(),'P-101',['d2']))


def test_named_pdf_reference_excludes_unrelated_selected_documents(store,one_chunk,one_vector):
    unrelated=replace(one_chunk,chunk_id='other',document_id='other',text='General engineering skills and assessments')
    requested=replace(one_chunk,chunk_id='requested',document_id='requested',text='The requested document discusses databases')
    store.publish('other','Maintenance Evidence Draft.docx','other','v1',[unrelated],one_vector,'emb1',[])
    store.publish('requested','24ALR001_ABISHEK M.pdf','requested','v1',[requested],one_vector,'emb1',[])
    passages=retrieve(store,FakeEmbedder(),'Tell me what the 24alr001 PDF says',['other','requested'])
    assert passages and {passage.document_id for passage in passages}=={'requested'}
