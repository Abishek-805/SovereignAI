"""Conservative numeric comparison of printed measurements and SOP triggers."""
from datetime import datetime
import re
from backend.contracts import WorkbenchError
from rag.calculator import evaluate_expression
from rag.deliverables import write_deliverables

VALUE=r'(\d+(?:\.\d+)?)\s*(mm/s|bar|degrees Celsius|°C|C)\b'
MEASUREMENT=re.compile(r'\b([A-Z]-\d+)\b[^\n]{0,100}?\b(vibration|temperature|pressure)\b[^\n]{0,80}?\b(?:measured|reading|recorded)\s*'+VALUE,re.I)
TRIGGER=re.compile(r'\b([A-Z]-\d+)\b[^\n]{0,100}?\b(vibration|temperature|pressure)\b[^\n]{0,80}?\b(above|below|exceeds)\s*'+VALUE,re.I)


def _unit(text):
    return {'degrees celsius':'°C','c':'°C','°c':'°C'}.get(text.lower(),text.lower())


def create_maintenance_draft(store,settings,document_ids,task_id=None):
    if not document_ids or len(document_ids)>100:
        raise WorkbenchError('invalid_selection','Select report and requirement documents')
    chunks=[chunk for chunk,_ in store.active_chunks(document_ids)]
    if not chunks:
        raise WorkbenchError('missing_evidence','Selected documents contain no passages')
    labels={chunk.chunk_id:f'S{index}' for index,chunk in enumerate(chunks,1)}
    measurements=[]; triggers=[]
    for chunk in chunks:
        for line in chunk.text.splitlines():
            for match in MEASUREMENT.finditer(line):
                measurements.append({'equipment':match[1].upper(),'metric':match[2].lower(),
                                     'value':float(match[3]),'unit':_unit(match[4]),'line':line.strip(),
                                     'label':labels[chunk.chunk_id]})
            for match in TRIGGER.finditer(line):
                if not re.search(r'\b(investigate|limit|threshold|required|shall|must)\b',line,re.I):
                    continue
                triggers.append({'equipment':match[1].upper(),'metric':match[2].lower(),
                                 'direction':match[3].lower(),'value':float(match[4]),'unit':_unit(match[5]),
                                 'line':line.strip(),'label':labels[chunk.chunk_id]})
    if not measurements:
        raise WorkbenchError('missing_evidence','No supported equipment measurement pattern found; draft was not created')
    findings=[]; calculations=[]; open_questions=[]
    for measured in measurements:
        candidates=[item for item in triggers if all(item[field]==measured[field] for field in ('equipment','metric','unit'))]
        source_ids=[measured['label']]
        requirement='No matching threshold found in selected sources.'
        status='missing limit'
        calc_id=None
        if len({(item['direction'],item['value']) for item in candidates})>1:
            status='conflicting requirements'
            requirement='; '.join(item['line'] for item in candidates)
            source_ids += sorted({item['label'] for item in candidates})
            open_questions.append(f"{measured['equipment']} {measured['metric']}: selected requirements conflict; confirm the governing version.")
        elif candidates:
            trigger=candidates[0]
            requirement=trigger['line']
            source_ids.append(trigger['label'])
            difference=evaluate_expression(f"{measured['value']} - {trigger['value']}")
            calc_id=f'C{len(calculations)+1}'
            calculations.append({'id':calc_id,'expression':difference.expression,
                                 'result':difference.result,'rounded':difference.rounded,'unit':measured['unit'],
                                 'source_ids':source_ids})
            beyond=(measured['value']>trigger['value']) if trigger['direction'] in ('above','exceeds') else (measured['value']<trigger['value'])
            status='exceeds investigation threshold' if beyond else 'does not exceed investigation threshold'
        else:
            open_questions.append(f"{measured['equipment']} {measured['metric']}: no matching limit in selected sources; compliance cannot be determined.")
        findings.append({'observation':measured['line'],'requirement':requirement,'status':status,
                         'source_ids':source_ids,'calc_id':calc_id})
    if task_id is None:
        from uuid import uuid4
        task_id=uuid4().hex
    versions=[{'document_id':doc['document_id'],'version_hash':doc['active_hash']} for doc in store.documents() if doc['document_id'] in document_ids]
    references=[{'id':labels[chunk.chunk_id],
                 'description':f"{chunk.display_name}, version {chunk.version_hash[:12]}, " +
                 (f'page {chunk.page}' if chunk.page is not None else f'lines {chunk.line_start}-{chunk.line_end}')}
                for chunk in chunks]
    data={'task_id':task_id,'title':'Maintenance Evidence Draft',
          'document_date':datetime.now().astimezone().date().isoformat(),'source_versions':versions,
          'findings':findings,'calculations':calculations,
          'requested_action':'Review these source excerpts and numeric comparisons. This draft does not authorize operation, shutdown, or approval.',
          'open_questions':open_questions,'references':references}
    artifacts=write_deliverables(task_id,data,settings)
    return {'status':'completed','task_id':task_id,'findings':findings,'calculations':calculations,
            'open_questions':open_questions,'references':references,'source_versions':versions,**artifacts}
