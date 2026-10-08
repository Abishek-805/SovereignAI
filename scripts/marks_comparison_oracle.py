import json,urllib.request,io
from pathlib import Path
import openpyxl
out=Path('outputs/interaction-repair');answer=json.loads((out/'actual-marks-comparison.json').read_text(encoding='utf-8'))
with urllib.request.urlopen('http://127.0.0.1:8088/documents/e125b261fdd7a7efaa9aa45c8903611bb09481f4d1c2c24d58d2cb16a2616295/original') as r:raw=r.read()
book=openpyxl.load_workbook(io.BytesIO(raw),data_only=True);sheet=book['All'];rows=list(sheet.values)
header=next(row for row in rows if 'Member Id' in row);columns=list(header);records={}
for row in rows:
 if row[0] in {'24ALR001','24ALR051','24ALR063'}:records[row[0]]=dict(zip(columns,row))
fields=['WAT '+str(i) for i in range(1,7)]+['CAT 1'];checks=[];metrics={}
text=answer['body']['answer']
for identity,row in records.items():
 scores=[row[field] for field in fields];passed=sum(isinstance(x,(int,float)) and x>=25 for x in scores)
 metrics[identity]={'scores':scores,'passed':passed}
 checks.append(identity in text and f'{identity}: {passed} of 7 assessments passed.' in text)
 expected=identity+' | '+' | '.join(str(x) for x in scores)
 checks.append(expected in text)
for field in fields:
 numeric={identity:row[field] for identity,row in records.items() if isinstance(row[field],(int,float))}
 maximum=max(numeric.values());winners=[identity for identity,value in numeric.items() if value==maximum]
 checks.append(field+': '+', '.join(winners)+f' ({maximum}).' in text)
result={'status':'PASS' if answer['status']==200 and len(records)==3 and all(checks) else 'FAIL','source_rows':metrics,'checks':checks,'basis':'Independent original XLSX cells, not the model answer or retrieved excerpts'}
(out/'marks-independent.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result['status'],metrics)
