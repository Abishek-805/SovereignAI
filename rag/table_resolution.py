"""Logical tables retain source versions and physical record provenance."""
import time
import re
from backend.contracts import WorkbenchError
from rag.tables import identity_value


def logical_tables(available):
    """Coalesce only representations of the same sheet, schema and physical rows."""
    groups={};result={}
    for key,(doc,table) in available.items():
        signature=(doc['document_id'],doc.get('active_hash',doc.get('version_hash')),table['name'],tuple(table['columns']))
        if signature not in groups:
            groups[signature]=key
            result[key]=(doc,{**table,'records':list(table['records']),'record_rows':list(table.get('record_rows',[])),
                               'internal_references':[key]})
            continue
        canonical=result[groups[signature]][1]
        # A matching value at a different physical row is not a duplicate record.
        if not canonical['record_rows'] or not table.get('record_rows'):
            raise WorkbenchError('needs_input',f"Record provenance is unavailable for overlapping representations of {table['name']}; select a verified range.")
        rows=dict(zip(canonical['record_rows'],canonical['records']))
        for number,record in zip(table['record_rows'],table['records']):
            if number in rows and rows[number]!=record:
                raise WorkbenchError('needs_input',f"Conflicting source values at {doc.get('display_name','source')}, {table['name']}, row {number}; choose the intended source range.")
            rows[number]=record
        canonical['record_rows']=sorted(rows);canonical['records']=[rows[n] for n in canonical['record_rows']]
        canonical['internal_references'].append(key)
    return result


def select_logical_plan(candidates,available,prior=None):
    if not candidates:return None
    started=time.perf_counter()
    def matched(plan):
        table=available[plan['table']][1];field=plan.get('identity_column');entities={identity_value(v) for v in plan.get('requested_entities',[])}
        return [row for row in table['records'] if not entities or identity_value(row.get(field)) in entities]
    # Common named measurements must agree before a broader table replaces a narrow one.
    preferred=[p for p in candidates if prior and available[p['table']][0]['document_id']==prior['document_id'] and available[p['table']][1]['name']==prior['table']]
    if len(preferred)==1:selected=preferred[0];reason='current_verified_prior_logical_table'
    elif len(candidates)==1:selected=candidates[0];reason='single_matching_logical_table'
    else:
        documents={(available[p['table']][0]['document_id'],available[p['table']][0].get('active_hash')) for p in candidates}
        widest=max(len(p['columns']) for p in candidates)
        summaries=[p for p in candidates if len(p['columns'])==widest]
        if len(documents)==1 and len(summaries)==1:
            selected=summaries[0];reason='unique_wide_measurement_summary'
            wide_fields=set(selected['columns'])-{selected.get('identity_column')}
            coded=sum(bool(re.fullmatch(r'[A-Za-z][A-Za-z _-]*\d+',field)) for field in wide_fields)>=2
            generic={'score','mark','result','total'}
            from rag.identifiers import words
            for plan in candidates:
                fields=set(plan['columns'])-{plan.get('identity_column')}
                if fields<=wide_fields or coded and all(words(field) and words(field)<=generic for field in fields):continue
                raise WorkbenchError('needs_input','Assessment sheets contain different measurement sets; choose the sheet or specify which measurements to combine. No result was silently omitted.')
        else:
            choices=list(dict.fromkeys(available[p['table']][0].get('display_name','source')+
                ('' if re.fullmatch(r'[0-9a-f]{64}',available[p['table']][1]['name']) else ' / '+available[p['table']][1]['name']) for p in candidates))
            raise WorkbenchError('needs_input','Results match multiple source assessments. Which source or assessment should be used? Matching choices: '+', '.join(choices[:8])+'.')
    for left in [selected]:
        ld,lt=available[left['table']]
        for right in [p for p in candidates if p is not selected]:
            rd,rt=available[right['table']]
            if (ld['document_id'],ld.get('active_hash'))!=(rd['document_id'],rd.get('active_hash')):continue
            shared=(set(left['columns'])&set(right['columns']))-{left.get('identity_column'),right.get('identity_column')}
            for field in shared:
                lv={(identity_value(row.get(left['identity_column'])),str(row.get(field))) for row in matched(left)}
                rv={(identity_value(row.get(right['identity_column'])),str(row.get(field))) for row in matched(right)}
                if lv and rv and lv!=rv:
                    raise WorkbenchError('needs_input',f"Conflicting {field} results in {ld.get('display_name','source')}: {lt['name']} and {rt['name']}. Which assessment sheet should be used?")
    doc,table=available[selected['table']]
    selected['logical_resolution']={'document_id':doc['document_id'],'version_hash':doc.get('active_hash',doc.get('version_hash')),
        'filename':doc.get('display_name'),'sheet':table['name'],'internal_references':table.get('internal_references',[selected['table']]),
        'headers':table['columns'],'records':len(table['records']),'selection_reason':reason,
        'candidate_count':len(candidates),'table_resolution_seconds':time.perf_counter()-started}
    return selected
