"""Read-only measurement operations compiled from actual fields and exact values."""
import re
from rag.identifiers import resolve_identifiers, named_field, words
from rag.tables import exact_identity_columns, identity_value, numeric_value
from backend.contracts import WorkbenchError


def analytics_requested(question):
    if re.search(r'\b(create|build|delete|update|install|run)\b',question,re.I):
        return False
    return bool(re.search(r'\b(avg|average|mean|sum|total|best|lowest|highest|top|attempted|missing|miss|absent|weighted|normalized)\b', question, re.I))


def compile_measurements(question, available, history=None, prior=None):
    if not analytics_requested(question):
        return None
    if re.search(r'\b(above|below|between|since|before|after|last year|last month)\b',question,re.I):
        raise WorkbenchError('needs_input','This measurement operation needs an explicit source-bound range/filter contract; no constraint was ignored.')
    if re.search(r'\b(avg|average)\b',question,re.I) and re.search(r'\b(best|lowest|highest|top)\b',question,re.I):
        raise WorkbenchError('needs_input','Specify whether to rank measurements or calculate their mean; both operations were not silently combined.')
    resolution = resolve_identifiers(question, available, history)
    population = bool(re.search(r'\b(students|entities|assets|employees|customers|projects|records)\b', question, re.I))
    if not resolution.explicit and not population:
        if not re.search(r'\b(he|she|his|her|they|their|those|these|it|instead)\b', question, re.I):
            return None
        if not prior:
            raise WorkbenchError('needs_input', 'No current verified result supports this follow-up. Specify the entity and source.')
        entities = prior['requested_entities']
        if re.search(r'\b(he|she|his|her|it)\b', question, re.I) and len(entities) != 1:
            raise WorkbenchError('needs_input', 'The previous result contains multiple entities; specify which one.')
        resolution.canonical = entities
        resolution.provenance = [{'identifier':v, 'origin':'verified_prior_result'} for v in entities]
    if resolution.unresolved:
        raise WorkbenchError('needs_input', 'Resolve the incomplete identifiers before calculating a result.')
    if available and resolution.explicit and not resolution.matches:
        raise WorkbenchError('needs_input','No exact matching record was found for: '+', '.join(resolution.canonical)+'. Check the identifier or select the relevant source. No measurement result was inferred from the authorized tables.')
    summed=bool(re.search(r'\b(?:sum|total)\b',question,re.I))
    if summed and not resolution.canonical:return None
    if summed and re.search(r'\b(?:average|avg|mean|best|highest|lowest|top)\b',question,re.I):
        raise WorkbenchError('needs_input','Specify the requested measurement operation; multiple statistics were not silently combined.')
    ranked = bool(re.search(r'\b(best|lowest|highest|top)\b', question, re.I))
    number = re.search(r'\b(?:best|lowest|highest|top)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b', question, re.I)
    counts = dict(zip('one two three four five six seven eight nine ten'.split(), range(1,11)))
    limit = (int(number[1]) if number and number[1].isdigit() else counts.get(number[1].lower(),1) if number else 1)
    if not 1 <= limit <= 40:
        raise WorkbenchError('invalid_query', 'Ranking limit must be between 1 and 40.')
    operation = ('measurement_rank' if ranked else 'measurement_missing' if re.search(r'\b(missing|miss|absent)\b', question, re.I)
                 else 'measurement_count' if re.search(r'\battempted\b', question, re.I) else 'measurement_sum' if summed else 'overall_average')
    if re.search(r'\b(weighted|normalized|percentage)\b', question, re.I):
        raise WorkbenchError('needs_input', 'A source-defined scale/weight policy is required; no grading formula was inferred.')
    candidates = []
    for key, (doc, table) in available.items():
        if prior and not resolution.explicit and (doc['document_id'] != prior['document_id'] or table['name'] != prior['table']):
            continue
        found = exact_identity_columns(table, resolution.canonical)
        if population and not resolution.explicit:
            found = {field:{} for field in table['columns'] if len({identity_value(r.get(field)) for r in table['records']}) == len(table['records'])
                     and table['records'] and all(re.search(r'[A-Za-z]', str(r.get(field))) and re.search(r'\d', str(r.get(field))) for r in table['records'])}
        if len(found) > 1:
            raise WorkbenchError('needs_input', 'Multiple exact identity fields match; specify the field.')
        if not found:
            continue
        identity = next(iter(found))
        excluded = re.compile(r'\b(id|identifier|number|phone|year|date|time|email|group|age)\b', re.I)
        numeric = [field for field in table['columns'] if field != identity and (not excluded.search(field) or named_field(field,question))
                   and (any(numeric_value(r.get(field)) is not None for r in table['records']) or
                        all(r.get(field) is None or str(r.get(field)).strip().casefold() in {'','ab'} for r in table['records']))]
        named = [field for field in numeric if named_field(field,question)]
        labels = [field for field in table['columns'] if words(field) & {'assessment','test','subject','measurement','metric'} and field != identity
                  and not any(numeric_value(row.get(field)) is not None for row in table['records'])]
        fields = named or [field for field in numeric if re.fullmatch(r'[A-Za-z][A-Za-z _-]*\d+', field) or words(field) & {'score','mark','result','total'}]
        if prior and not resolution.explicit and not named:
            fields = list(dict.fromkeys([*fields,*[field for field in prior['measurement_fields'] if field in numeric]]))
        if operation in {'overall_average','measurement_sum'} and not named and not labels and set(numeric)-set(fields):
            raise WorkbenchError('needs_input','Additional numeric fields have unresolved measurement roles: '+', '.join(field for field in numeric if field not in fields)+'. No partial overall average was inferred.')
        if not fields:
            continue
        if population:
            if len(fields) != 1:
                raise WorkbenchError('needs_input', 'Entity ranking requires one explicitly named numeric metric.')
            if len({identity_value(r.get(identity)) for r in table['records']}) != len(table['records']):
                raise WorkbenchError('needs_input', 'Entity ranking needs an aggregate for repeated identities.')
            operation = 'select'
        if len(labels)>1 or labels and len(fields)>1:
            raise WorkbenchError('needs_input', 'The measurement name/value relationship is ambiguous.')
        plan = {'table':key, 'operation':operation, 'columns':[identity,*fields] if population else fields,
                'measurement_fields':fields, 'label_column':labels[0] if labels else None,
                'unit_columns':[field for field in table['columns'] if words(field)&{'unit','scale'}],
                'identity_column':identity, 'requested_entities':resolution.canonical,
                'filters':[] if population else [{'column':identity,'operator':'in','value':resolution.canonical}],
                'identity_resolution':resolution.to_dict(), 'limit':limit if ranked else None,
                'direction':'asc' if re.search(r'\blowest\b', question,re.I) else 'desc',
                'missing_policy':'zero' if re.search(r'\bAB\s+(?:as|is|=)\s+zero\b',question,re.I) else 'exclude',
                'policy_origin':'explicit_user' if re.search(r'\bAB\s+(?:as|is|=)\s+zero\b',question,re.I) else 'raw_numeric_only'}
        if population:
            plan['order_by']=[{'column':fields[0],'direction':plan['direction']}]
            values=[numeric_value(row.get(fields[0])) for row in table['records']]
            values=[value for value in values if value is not None]
            if not values:
                raise WorkbenchError('needs_input','The ranking metric has no numeric values.')
            plan['filters']=[{'column':fields[0],'operator':'gte','value':min(values)}]
        plan['contract']={'original_question':question,'operation':operation, 'document_id':doc['document_id'],
            'version_hash':doc.get('active_hash',doc.get('version_hash')), 'table':table['name'], 'requested_entities':resolution.canonical,
            'measurement_fields':fields, 'filters':plan['filters'], 'rules':{'missing_policy':plan['missing_policy'],'policy_origin':plan['policy_origin']},
            'required_outputs':['result','contributing_cells','source_version'], 'evidence_required':True,
            'followup_resolved':bool(prior and not resolution.explicit), 'result_format':'computed_table',
            'completion_criteria':'complete source values; validated population, fields, operation and current source'}
        candidates.append(plan)
    from rag.table_resolution import select_logical_plan
    return select_logical_plan(candidates,available,prior)


def execute_measurements(table, plan, rows, result):
    """The existing executor validates schema, filters and locators before this call."""
    fields=plan['columns']; identity=plan.get('identity_column'); label=plan.get('label_column')
    if not identity or identity not in table['columns'] or label and label not in table['columns']:
        raise WorkbenchError('invalid_query', 'Measurement identity or label is unavailable.')
    if not fields or identity in fields or label in fields:
        raise WorkbenchError('invalid_query', 'Measurements must be distinct from identity and labels.')
    if plan.get('missing_policy','exclude') not in {'exclude','zero'}:
        raise WorkbenchError('invalid_query','Unknown missing-value policy.')
    if plan.get('missing_policy')=='zero' and plan.get('policy_origin')!='explicit_user':
        raise WorkbenchError('invalid_query','Zero substitution requires explicit user authorization.')
    scales=[re.findall(r'\(([^)]+)\)',field) for field in fields]
    known={part.casefold() for parts in scales for part in parts}
    if len(known)>1 and plan['operation'] in {'overall_average','measurement_sum'}:
        raise WorkbenchError('needs_input','Measurement scales/units differ. Supply a documented normalization rule.')
    for column in plan.get('unit_columns',[]):
        if column not in table['columns']:
            raise WorkbenchError('invalid_query','The unit field is unavailable.')
        units={identity_value(row.get(column)) for row in rows if row.get(column) is not None and str(row.get(column)).strip()}
        if len(units)>1 and plan['operation'] in {'overall_average','measurement_sum'}:
            raise WorkbenchError('needs_input','Measurement scales/units differ. Supply a documented normalization rule.')
    numbers=table.get('record_rows',range(table.get('header_row',1)+1,table.get('header_row',1)+1+len(table['records'])))
    locators={id(row):number for row,number in zip(table['records'],numbers)}
    groups=[]
    for entity in plan.get('requested_entities',[]):
        matched=[row for row in rows if identity_value(row.get(identity))==identity_value(entity)]
        cells=[]
        for row in matched:
            for field in fields:
                raw=row.get(field); value=numeric_value(raw)
                substituted=value is None and str(raw).strip().casefold()=='ab' and plan.get('missing_policy')=='zero'
                cells.append({'measurement':str(row.get(label)) if label else field,'column':field,'raw':raw,
                              'value':0.0 if substituted else value, 'substituted':substituted,
                              'sheet':table['name'],'row':locators[id(row)]})
        # Multiple records for the same entity/measurement must not double-count an assessment.
        names=[cell['measurement'] for cell in cells]
        if len(names)!=len(set(names)):
            raise WorkbenchError('needs_input','Repeated entity/measurement records require an explicit aggregation rule.')
        included=[cell for cell in cells if cell['value'] is not None]
        excluded=[cell for cell in cells if cell['value'] is None]
        op=plan['operation']; values=[cell['value'] for cell in included]
        selected=sorted(included,key=lambda cell:cell['value'],reverse=plan.get('direction')=='desc') if op=='measurement_rank' else excluded if op=='measurement_missing' else cells
        if op=='measurement_rank':selected=selected[:plan.get('limit',1)]
        groups.append({'entity':entity,'value':sum(values)/len(values) if op=='overall_average' and values else len(included) if op=='measurement_count' else sum(values) if op=='measurement_sum' and values else None,
                       'denominator':len(values),'sum':sum(values),'included':included,'excluded':excluded,
                       'selected':selected,'available_numeric':len(values),'missing_entity':not matched})
    result.update(measurements=groups,missing_policy=plan.get('missing_policy','exclude'),
                  policy_origin=plan.get('policy_origin','raw_numeric_only'),contract=plan.get('contract'),
                  tie_policy='stable source order; exactly requested limit',limit=plan.get('limit'))
    return result
