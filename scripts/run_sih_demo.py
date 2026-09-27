"""Run the SIH26117 scanned-report-to-briefing demonstration on local services.

Only fictional P-101 data is generated. Start SovereignAI before running this.
"""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from time import perf_counter

import httpx
from PIL import Image, ImageDraw, ImageFont

from backend.service import Workbench


ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8088'


def scanned_report():
    image=Image.new('RGB',(1800,1000),'white')
    draw=ImageDraw.Draw(image)
    font_path=Path('C:/Windows/Fonts/arial.ttf')
    font=ImageFont.truetype(str(font_path),52) if font_path.is_file() else ImageFont.load_default()
    lines=['SYNTHETIC DEMO DATA - NOT AN INDUSTRIAL REPORT',
           'Inspection report: Pump P-101',
           'P-101 vibration measured 8.2 mm/s.',
           'Inspector note: review against current SOP.']
    for index,line in enumerate(lines):
        draw.text((100,110+index*130),line,fill='black',font=font)
    stream=BytesIO()
    image.save(stream,format='PDF',resolution=180)
    return stream.getvalue()


def main():
    started=perf_counter()
    report=scanned_report()
    sop=(b'SYNTHETIC DEMO DATA - NOT AN OPERATIONAL INSTRUCTION.\n'
         b'SOP-A: Investigate Pump P-101 vibration above 7.1 mm/s.\n'
         b'This excerpt does not authorize shutdown.\n')
    with httpx.Client(base_url=BASE,timeout=120,trust_env=False) as client:
        health=client.get('/health');health.raise_for_status()
        imports=[]
        for name,data,mime in [('sih-scanned-inspection.pdf',report,'application/pdf'),
                               ('sih-demo-sop.txt',sop,'text/plain')]:
            response=client.post('/documents/import',files={'file':(name,data,mime)})
            response.raise_for_status()
            imports.append(response.json())
        ids=[item['document_id'] for item in imports]
        workbench=Workbench()
        chunks=[chunk for chunk,_ in workbench.store.active_chunks([ids[0]])]
        if not chunks or not all(chunk.extraction_method=='ocr' for chunk in chunks):
            raise RuntimeError('The scanned report was not processed through OCR')
        response=client.post('/agent/tasks',json={
            'goal':'Compare the selected scanned inspection report with its SOP and draft a maintenance approval note',
            'document_ids':ids})
        response.raise_for_status()
        task=response.json()
        if task['status']!='completed' or task['workflow']!='maintenance_draft':
            raise RuntimeError('Agent did not complete the maintenance task')
        outputs={}
        for kind,url in task['result']['downloads'].items():
            artifact=client.get(url);artifact.raise_for_status()
            if not artifact.content.startswith(b'PK'):
                raise RuntimeError(f'{kind} was not an Office package')
            outputs[kind]={'bytes':len(artifact.content),'sha256':hashlib.sha256(artifact.content).hexdigest()}
        parent=client.get('/tasks/'+task['task_id']);parent.raise_for_status()
        child=client.get('/tasks/'+task['child_task_id']);child.raise_for_status()
        if parent.json()['state']!='completed' or child.json()['state']!='completed':
            raise RuntimeError('Task trace did not finish')
    record={'synthetic':True,'status':'passed','seconds':round(perf_counter()-started,3),
            'ocr_pages':len(chunks),'document_ids':ids,'parent_task_id':task['task_id'],
            'child_task_id':task['child_task_id'],'findings':task['result']['findings'],
            'artifacts':outputs}
    target=ROOT/'benchmarks'/'sih-demo-result.json'
    target.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(f"SIH demo passed in {record['seconds']} s: OCR, agent task, Word/Excel/PPT; {target}")


if __name__=='__main__':
    main()
