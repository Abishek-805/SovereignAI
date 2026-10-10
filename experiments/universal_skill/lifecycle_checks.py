"""Controlled staging acceptance receipts; never connects to production data."""
from pathlib import Path
import json,time,httpx,sys
ROOT=Path(__file__).resolve().parents[2]
OUT=Path((ROOT/'experiments/universal_skill/lifecycle-output.txt').read_text())
ids=json.loads((OUT/'document-ids.json').read_text())
cases=[('museum','Describe the Harbor Museum, its opening year, admission and website.',''),
       ('missing_reason','Why is the calibration interval 90 days in equipment-v1.txt?',''),
       ('invalid_id','Where is KPRIET located?','invalid_id'),
       ('missing_id','Where is KPRIET located?','missing_id'),
       ('quote_mismatch','Where is KPRIET located?','quote_mismatch'),
       ('unsupported','Where is KPRIET located?','unsupported')]
receipts=[]
if 'faults' in sys.argv:cases=cases[2:5]
output=OUT/('final-fault-acceptance.json' if 'faults' in sys.argv else 'final-api-acceptance.json')
with httpx.Client(base_url='http://127.0.0.1:8099',timeout=30) as client:
    try:
        for case,goal,mode in cases:
            (OUT/'fault-mode.txt').write_text(mode)
            start=time.perf_counter()
            response=client.post('/agent/jobs',json={'goal':goal,'document_ids':list(ids.values()),'history':[]});response.raise_for_status()
            job=response.json()['job_id'];snapshots=[]
            while True:
                response=client.get('/coding/jobs/'+job);response.raise_for_status();snapshot=response.json()
                snapshots.append(snapshot)
                if snapshot['state']!='running':break
                if time.perf_counter()-start>240:raise RuntimeError('Staging acceptance exceeded 240 seconds')
                time.sleep(.4)
            receipt={'case':case,'goal':goal,'fault':mode,'seconds':time.perf_counter()-start,'snapshots':snapshots}
            receipts.append(receipt)
            output.write_text(json.dumps(receipts,indent=2,ensure_ascii=False))
            print(case,snapshot['state'],snapshot.get('error_code'),flush=True)
    finally:(OUT/'fault-mode.txt').write_text('')
