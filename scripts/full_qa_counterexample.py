import json,urllib.request,time
from scripts.full_qa_inventory import http,save,OUT
text='Name,Group,Score,Result\nAlpha,ALR,30,FAIL\nBeta,ALR,26,FAIL\nGamma,ALR,10,PASS\nDelta,ALR,,ABSENT\n'
name='qa-score-label-counterexample.csv';(OUT/'documents/fixtures'/name).write_text(text,encoding='utf-8');save('rag/counterexample-oracle.json',{'question':'Count ALR students with Score at least 25. Include missing scores in the population denominator.','column':'Score','criterion':'>=25','passed':2,'total':4,'explicit_label_pass_count':1,'oracle_authored_before_request':True})
boundary='QAFieldBinding';raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: text/csv\r\n\r\n'+text+f'\r\n--{boundary}--\r\n').encode();req=urllib.request.Request('http://127.0.0.1:8088/documents/import',data=raw,headers={'Content-Type':'multipart/form-data; boundary='+boundary});admission=json.load(urllib.request.urlopen(req));save('documents/counterexample-import.json',admission)
if admission.get('job_id'):
 for _ in range(120):
  final=http('/coding/jobs/'+admission['job_id'])['body']
  if final['state']!='running':break
  time.sleep(1)
 save('documents/counterexample-job.json',final)
did=admission.get('document_id') or admission.get('document',{}).get('document_id');q='Count ALR students with Score at least 25. Include missing scores in the population denominator.';r=http('/ask','POST',{'question':q,'document_ids':[did],'history':[]});save('rag/counterexample-answer.json',r);print(str(r['body'].get('answer'))[:700])
