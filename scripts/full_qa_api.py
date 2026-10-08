import json,re,time
from scripts.full_qa_inventory import http,save,OUT
routes=json.loads((OUT/'api-inventory.json').read_text(encoding='utf-8'))
results=[]
def test(id,path,method='GET',data=None,expected=None,headers=None,raw=None):
 r=http(path,method,data,headers,raw);r['id']=id;r['expected_status']=expected;r['verdict']='PASS' if r['status'] in expected else 'FAIL' if r['status'] is not None else 'BLOCKED';results.append(r);save('api/'+id+'.json',r);return r
for index,route in enumerate(routes):
 path=re.sub(r'\{[^}]+\}','qa_nonexistent_0000000000000000',route['path']);method=route['method']
 if path in ['/workbench/model/unload','/workbench/docker/start','/workbench/docker/verify','/workflows/csv-coding-demo']:continue
 if method=='GET':test('route-%02d-read'%index,path,expected=[200,400,404,422,503])
 else:
  test('route-%02d-missing'%index,path,method,{},expected=[400,404,409,422,503])
  test('route-%02d-malformed'%index,path,method,expected=[400,404,422],raw=b'{broken')
for path in ['/agent/jobs','/ask','/documents/jobs','/coding/workspaces']:
 for suffix,body in [('empty',{}),('wrong-type',{'goal':{},'question':[],'name':[],'kind':123}),('over-limit',{'goal':'x'*8001,'question':'x'*8001,'name':'x'*81,'kind':'ask'})]:test('boundary-'+path.replace('/','-')+'-'+suffix,path,'POST',body,expected=[400,422])
test('evil-origin','/calculate','POST',{'expression':'2+2'},[403],{'Origin':'https://evil.invalid'})
test('evil-host','/health',expected=[400],headers={'Host':'evil.invalid'})
test('calculate-valid','/calculate','POST',{'expression':'(6*7)+0'},[200])
test('calculate-forbidden','/calculate','POST',{'expression':'__import__("os").system("echo bad")'},[400,422])
r=test('workspace-create','/coding/workspaces','POST',{'name':'Full QA temporary '+str(time.time_ns())},[200]);wid=r['body']['workspace_id'];save('coding/fixture.json',{'workspace_id':wid})
test('file-write','/coding/workspaces/'+wid+'/files/notes.txt','PUT',{'content':'QA_PRESERVE_SENTINEL\n'},[200])
r=test('file-read','/coding/workspaces/'+wid+'/files/notes.txt',expected=[200]);sha=r['body']['sha256']
test('file-stale-revision','/coding/workspaces/'+wid+'/files/notes.txt','PUT',{'content':'bad','expected_sha256':'0'*64},[409])
for index,name in enumerate(['../outside.txt','C:/Windows/outside.txt','..%2Foutside.txt','folder\\outside.txt','CON.txt','x'*81+'.txt']):test('path-boundary-'+str(index),'/coding/workspaces/'+wid+'/files/'+name,'PUT',{'content':'UNAUTHORIZED'},[400,404,422])
test('file-special-valid','/coding/workspaces/'+wid+'/files/Unicode%20%E0%AE%A4%E0%AE%AE%E0%AE%BF%E0%AE%B4%E0%AF%8D.txt','PUT',{'content':'Safe unicode fixture'},[200])
test('file-copy','/coding/workspaces/'+wid+'/file-operation','POST',{'action':'copy','source':'notes.txt','destination':'copy.txt'},[200])
test('file-move','/coding/workspaces/'+wid+'/file-operation','POST',{'action':'move','source':'copy.txt','destination':'renamed.txt'},[200])
test('file-delete','/coding/workspaces/'+wid+'/file-operation','POST',{'action':'delete','source':'renamed.txt'},[200])
r=test('file-preserved','/coding/workspaces/'+wid+'/files/notes.txt',expected=[200]);assert r['body']['sha256']==sha
save('api/results.json',results)
print(json.dumps({'cases':len(results),'pass':sum(r['verdict']=='PASS' for r in results),'fail':sum(r['verdict']=='FAIL' for r in results)}))
