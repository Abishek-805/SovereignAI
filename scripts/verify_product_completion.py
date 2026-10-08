"""Sequential real-stack product verification; does not run historical benchmarks."""
import argparse
import os
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from io import BytesIO

BASE='http://127.0.0.1:8088'
OUT=Path(os.environ.get('SOVEREIGN_QA_OUTPUT','outputs/product-verification-20261004'))
OUT.mkdir(parents=True,exist_ok=True)

def save(name,result):
    if (OUT/(name+'.json')).exists():
        (OUT/(name+'-previous-'+str(time.time_ns())+'.json')).write_bytes((OUT/(name+'.json')).read_bytes())
    (OUT/(name+'.json')).write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')

def call(url,body=None,method=None):
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(BASE+url,data=data,method=method or ('POST' if data else 'GET'),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=300) as response:
        return json.load(response)

def job(name,url,body):
    started=time.monotonic()
    admitted=call(url,body);save(name+'-admission',admitted)
    for _ in range(360):
        result=call('/coding/jobs/'+admitted['job_id'])
        if result['state']!='running':
            save(name,{**result,'observed_latency':time.monotonic()-started})
            print(name,result['state'],flush=True)
            return result
        time.sleep(1)
    raise RuntimeError('Bounded product observation expired; backend job retained')

def workspace(name,files):
    result=call('/coding/workspaces',{'name':'Product verification '+name+' '+str(time.time_ns())})
    for name,content in files.items():
        call('/coding/workspaces/'+result['workspace_id']+'/files/'+name,{'content':content},'PUT')
    return result['workspace_id']

def languages():
    cases={'python':{'main.py':'from helpers import answer\nprint(answer())\n','helpers.py':'def answer():\n    return 42\n'},
           'node':{'package.json':'{"name":"verification","main":"main.js"}','main.js':"const {answer}=require('./helpers'); console.log(answer());",'helpers.js':'exports.answer=()=>42;'},
           'java':{'Main.java':'public class Main { public static void main(String[] args) { System.out.println(Helper.answer()); }}','Helper.java':'public class Helper { public static int answer(){return 42;} }'}}
    for label,files in cases.items():
        wid=workspace(label,files)
        result=job('language-'+label,'/coding/workspaces/'+wid+'/jobs',{'kind':'run','target':''})
        assert result['state']=='completed',result
        assert '42' in result['result']['stdout'],result
        assert result['result']['checks']['container_executed'],result
        assert result['result'].get('project_map'),result

def documents():
    token='verification-'+str(time.time_ns())
    text='Product verification source. Facility '+token+' has exactly 7 repair bays. Its supervisor is Mira.\n'
    boundary='SovereignProductVerification'
    payload=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{token}.txt"\r\nContent-Type: text/plain\r\n\r\n'+text+f'\r\n--{boundary}--\r\n').encode()
    request=urllib.request.Request(BASE+'/documents/import',data=payload,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    with urllib.request.urlopen(request,timeout=300) as response: imported=json.load(response)
    save('document-upload',imported)
    did=imported['document_id']
    result=job('document-rag','/documents/jobs',{'kind':'ask','question':'How many repair bays are in this facility and who supervises it? Cite the source.','document_ids':[did],'force_documents':True})
    assert result['state']=='completed' and '7' in result['result']['answer'] and 'Mira' in result['result']['answer']
    assert result['result']['sources']
    save('stored-document',{'document_id':did,'sha256':hashlib.sha256(text.encode()).hexdigest()})

def artifacts():
    for ext,request in [('md','Create a Knowledge Markdown document explaining what a Python function is, with a heading and an example.'),
                        ('docx','Create a Word DOCX document with title Product Verification, a section named Findings, and the sentence The prototype is under verification.'),
                        ('xlsx','Create an Excel XLSX workbook with one sheet named Checks. Row 1 headers are Item and Count. Row 2 values are Alpha and 7. Row 3 values are Beta and 3. No extra columns.')]:
        name='product_verification_'+str(time.time_ns())+'.'+ext
        result=job('artifact-'+ext,'/agent/jobs',{'goal':request+' Name the file '+name,'document_ids':[]})
        assert result['state']=='completed',result
        operations=result['result']['result']['operations']
        generated=next(item['result'] for item in operations if item['tool']=='document_create')
        did=generated['document_id']
        raw=urllib.request.urlopen(BASE+'/documents/'+did+'/original').read()
        (OUT/name).write_bytes(raw)
        if ext=='docx':
            from docx import Document
            contents='\n'.join(p.text for p in Document(BytesIO(raw)).paragraphs)
            assert 'Product Verification' in contents and 'Findings' in contents and 'prototype is under verification' in contents
        elif ext=='xlsx':
            from openpyxl import load_workbook
            book=load_workbook(BytesIO(raw),data_only=False)
            assert book.sheetnames==['Checks']
            assert list(book['Checks'].values)==[('Item','Count'),('Alpha',7),('Beta',3)]
        else:
            contents=raw.decode();assert '#' in contents and 'function' in contents.lower()
        save('artifact-'+ext+'-independent',{'document_id':did,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'validated':True})

def followups():
    did='e125b261fdd7a7efaa9aa45c8903611bb09481f4d1c2c24d58d2cb16a2616295'
    history=['User: Count ALR students passing each assessment. Passing is 25 and above.']
    for label,question in [('counts','Give me the assessment counts.'),('week1','Check Week 1.'),('bare','WAT 1.')]:
        result=job('followup-'+label,'/documents/jobs',{'kind':'ask','question':question,'document_ids':[did],'force_documents':True,'history':history})
        assert result['state']=='completed',result
        answer=result['result']['answer']
        assert '23' in answer and '64' in answer,answer
        assert result['result']['sources']
        history.extend(['User: '+question,'Assistant: '+answer[:500]])

def repair():
    wid=workspace('broken',{'main.py':'from helpers import answer\nprint(answer())\n',
        'helpers.py':'def answer():\n    return 42 / 0\n','README.md':'Run with python main.py. Expected output: 42.\n',
        'keep.txt':'unrelated sentinel\n'})
    failed=job('broken-run','/coding/workspaces/'+wid+'/jobs',{'kind':'run','target':'main.py'})
    assert failed['state']=='failed' and 'ZeroDivisionError' in failed['result']['stderr'],failed
    result=job('repair','/agent/jobs',{'goal':'Fix the division by zero in helpers.answer() so it returns integer 42. Preserve main.py and keep.txt, then run main.py to verify it prints 42.','workspace_id':wid,'document_ids':[], 'history':['User: Run main.py.', 'Assistant: '+failed['result']['stderr']]})
    assert result['state']=='completed',result
    operations=result['result']['result'].get('operations',[])
    draft=(next(item['result'] for item in operations if item['tool']=='file_edit') if operations else result['result']['result'])
    assert draft['state']=='completed',draft
    assert draft['checks']['container_executed'] and draft['validation_exit_code']==0,draft
    if draft['validation_kind']=='independent_build_contract':
        assert draft['checks']['build_contract_passed'],draft
        assert any(c.get('kind')=='cli' and c.get('passed') and c.get('stdout','').strip()=='42'
                   for c in draft['contract_results']),draft
    else:
        assert draft['validation_kind']=='syntax_and_runtime' and draft['checks']['runtime_passed'],draft
        assert '42' in draft['stdout'].splitlines(),draft
    call('/coding/workspaces/'+wid+'/tasks/'+draft['task_id']+'/accept',{})
    checked=job('repair-independent','/coding/workspaces/'+wid+'/jobs',{'kind':'terminal','command':"python -c 'from helpers import answer; assert answer() == 42; assert isinstance(answer(), int); print(answer())'"})
    assert checked['state']=='completed' and checked['result']['exit_code']==0,checked
    assert call('/coding/workspaces/'+wid+'/files/keep.txt')['content']=='unrelated sentinel\n'
    assert call('/coding/workspaces/'+wid+'/files/main.py')['content']=='from helpers import answer\nprint(answer())\n'
    save('repair-workspace',{'workspace_id':wid,'required_symbols_preserved':True,'unrelated_file_preserved':True})

def storage():
    assert not call('/status')['active_jobs'], 'Wait for active jobs before model reload'
    save('storage-unload',call('/workbench/model/unload',{}))
    save('storage-reload',call('/workbench/model/load',{'capability':'text'}))
    checks=[]
    for ext in ['md','docx','xlsx']:
        artifact=json.loads((OUT/('artifact-'+ext+'-independent.json')).read_text())
        raw=urllib.request.urlopen(BASE+'/documents/'+artifact['document_id']+'/original').read()
        assert hashlib.sha256(raw).hexdigest()==artifact['sha256']
        checks.append({'document_id':artifact['document_id'],'sha256':artifact['sha256'],'identical':True})
    save('storage-after-restart-and-reload',{'artifacts':checks,'passed':True})

def queue():
    wid=workspace('queue',{'main.py':'import time\ntime.sleep(8)\nprint("OWNER_DONE")\n'})
    owner=call('/coding/workspaces/'+wid+'/jobs',{'kind':'run','target':'main.py'})
    for _ in range(20):
        state=call('/coding/jobs/'+owner['job_id'])
        if 'Docker' in state['stage']:break
        time.sleep(.1)
    waiting=call('/documents/jobs',{'kind':'ask','question':'Explain what a variable is in one short sentence.','document_ids':[]})
    cancelled=call('/documents/jobs',{'kind':'ask','question':'Say one short greeting.','document_ids':[]})
    save('queue-admission',{'owner':owner,'waiting':waiting,'cancelled':cancelled,'status':call('/status')['active_jobs']})
    call('/coding/jobs/'+cancelled['job_id']+'/stop',{})
    completed={}
    for label,admission in [('owner',owner),('waiting',waiting),('cancelled',cancelled)]:
        for _ in range(180):
            result=call('/coding/jobs/'+admission['job_id'])
            if result['state']!='running':break
            time.sleep(1)
        completed[label]=result
    save('queue-final',completed)
    assert completed['owner']['state']=='completed' and 'OWNER_DONE' in completed['owner']['result']['stdout']
    assert completed['waiting']['state']=='completed' and completed['waiting']['result']['answer']
    assert completed['cancelled']['state']=='cancelled'

def multifile():
    wid=workspace('multifile',{'main.py':'from helpers import answer\nprint(answer())\n','helpers.py':'def answer():\n    return 42\n','keep.txt':'unrelated sentinel\n'})
    result=job('multifile','/agent/jobs',{'goal':'Rename answer() to value() in helpers.py and update its import and call in main.py. Keep keep.txt unchanged. The program must still print 42.','workspace_id':wid,'document_ids':[]})
    assert result['state']=='completed',result
    draft=result['result']['result']
    assert {c['path'] for c in draft['changes']}=={'main.py','helpers.py'},draft
    call('/coding/workspaces/'+wid+'/tasks/'+draft['task_id']+'/accept',{})
    checked=job('multifile-independent','/coding/workspaces/'+wid+'/jobs',{'kind':'terminal','command':'''python -c 'from helpers import value; import subprocess,sys; assert value()==42; output=subprocess.check_output([sys.executable,"main.py"],text=True); assert output.strip()=="42"; print(output,end="")' '''})
    assert checked['state']=='completed' and checked['result']['exit_code']==0,checked
    assert call('/coding/workspaces/'+wid+'/files/keep.txt')['content']=='unrelated sentinel\n'
    save('multifile-verdict',{'workspace_id':wid,'passed':True,'unrelated_file_preserved':True})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['languages','documents','artifacts','followups','repair','multifile','storage','queue']);args=parser.parse_args()
    try:globals()[args.stage]()
    except Exception as error:
        save(args.stage+'-error',{'error':str(error)});raise
