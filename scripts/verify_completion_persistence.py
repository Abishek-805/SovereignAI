"""Final selected-source abstention and content persistence checks."""
import hashlib
import json
import urllib.request
from scripts.verify_product_completion import OUT,call,job,save

def snapshot():
    artifact_checks=[]
    for ext in ['md','docx','xlsx']:
        artifact=json.loads((OUT/('artifact-'+ext+'-independent.json')).read_text())
        raw=urllib.request.urlopen('http://127.0.0.1:8088/documents/'+artifact['document_id']+'/original').read()
        assert hashlib.sha256(raw).hexdigest()==artifact['sha256']
        artifact_checks.append({'format':ext,'sha256':artifact['sha256'],'identical':True})
    verdict=json.loads((OUT/'multifile-fixed/multifile-verdict.json').read_text())
    assert call('/coding/workspaces/'+verdict['workspace_id']+'/files/keep.txt')['content']=='unrelated sentinel\n'
    return {'artifacts':artifact_checks,'workspace_preserved':True}

if __name__=='__main__':
    source=json.loads((OUT/'browser-rag.json').read_text())['request']['document_ids']
    result=job('insufficient-evidence','/documents/jobs',{'kind':'ask','question':'What is the facility annual budget? Use only the selected source.','document_ids':source,'force_documents':True})
    assert result['state']=='completed',result
    response=result['result']
    save('insufficient-evidence-verdict',{'answer':response.get('answer'),'status':response.get('status'),'result':response})
    assert response.get('status')=='insufficient_evidence',response
    save('persistence-before-model-reload',snapshot())
    assert not call('/status').get('active_jobs'), 'Do not unload an active worker'
    save('model-unload',call('/workbench/model/unload',{}))
    save('model-reload',call('/workbench/model/load',{'capability':'text'}))
    save('persistence-after-model-reload',snapshot())
    print('Insufficient evidence and persisted artifact/workspace bytes verified.')
