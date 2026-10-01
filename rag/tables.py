"""Original table previews and bounded, read-only queries over complete records.

The model selects a table/columns/operators; it never supplies executable code.
Source values remain unchanged. Presentation and retrieval use the same schema.
"""
from pathlib import Path
from functools import lru_cache
from zipfile import ZipFile
import csv
import json
import re
import math
from backend.contracts import WorkbenchError

TABULAR={'.xlsx','.csv','.tsv','.json','.jsonl'}

def scalar(value):
    if isinstance(value,float) and not math.isfinite(value): return None
    return value.isoformat() if hasattr(value,'isoformat') else value

def _table(name, rows, styles=None, merges=None, widths=None):
    nonempty=[(n,row) for n,row in enumerate(rows) if any(v is not None and v!='' for v in row)]
    candidates=nonempty[:20]
    # A title row has few cells; column labels are predominantly strings.
    headers=[(n,row) for n,row in candidates if sum(isinstance(v,str) and bool(v.strip()) for v in row)>=max(1,.8*sum(v is not None and v!='' for v in row))]
    header,row=max(headers or candidates,key=lambda item:sum(v is not None and v!='' for v in item[1]),default=(0,[]))
    columns=[str(v) if v is not None and v!='' else f'Column {i+1}' for i,v in enumerate(row)]
    columns=[v if columns.count(v)==1 else f'{v} [{i+1}]' for i,v in enumerate(columns)]
    return {'name':name,'columns':columns,'header_row':header+1,'rows':rows,
            'records':[{columns[i]:scalar(v) for i,v in enumerate(row[:len(columns)])} for n,row in nonempty if n>header],
            'styles':styles or {},'merges':merges or [],'widths':widths or {}}

@lru_cache(maxsize=2)
def _load(path,mtime,size):
    path=Path(path)
    if size>20*1024*1024: raise WorkbenchError('file_too_large','Preview exceeds file limit')
    if path.suffix.lower()=='.xlsx':
        from openpyxl import load_workbook
        with ZipFile(path) as archive:
            if len(archive.infolist())>4000 or sum(i.file_size for i in archive.infolist())>80*1024*1024:
                raise WorkbenchError('file_too_large','Spreadsheet expansion exceeds preview limit')
        book=load_workbook(path,data_only=True,read_only=False,keep_links=False)
        try:
            if len(book.worksheets)>200 or sum(len(s._cells) for s in book)>100000:
                raise WorkbenchError('file_too_large','Spreadsheet exceeds cell or sheet limit')
            tables=[]
            for sheet in book:
                # Bound stored coordinates; do not allocate attacker-controlled dimensions.
                cells=list(sheet._cells.values())
                maxrow=max((c.row for c in cells),default=0); maxcol=max((c.column for c in cells),default=0)
                if maxrow>20000 or maxcol>256 or maxrow*maxcol>200000:
                    raise WorkbenchError('file_too_large','Worksheet preview exceeds 20,000 rows or 256 columns')
                rows=[[None]*maxcol for _ in range(maxrow)]; styles={}
                for c in cells:
                    rows[c.row-1][c.column-1]=scalar(c.value)
                    styles[c.coordinate]={'bold':bool(c.font.bold),'italic':bool(c.font.italic),
                        'color':c.font.color.rgb[-6:] if c.font.color and c.font.color.type=='rgb' else None,
                        'fill':c.fill.fgColor.rgb[-6:] if c.fill.patternType=='solid' and c.fill.fgColor.type=='rgb' else None,
                        'align':c.alignment.horizontal or 'general','format':c.number_format}
                tables.append(_table(sheet.title,rows,styles,[str(m) for m in sheet.merged_cells.ranges],
                    {k:v.width for k,v in sheet.column_dimensions.items()}))
            return tables
        finally: book.close()
    data=path.read_bytes()
    try: text=data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    except UnicodeError as exc: raise WorkbenchError('parse_failed','Table must use UTF-8 or UTF-16 text') from exc
    if path.suffix.lower() in {'.csv','.tsv'}:
        rows=list(csv.reader(text.splitlines(),delimiter='\t' if path.suffix.lower()=='.tsv' else ','))
        if len(rows)>20000 or any(len(r)>256 for r in rows): raise WorkbenchError('file_too_large','Table exceeds preview limits')
        return [_table(path.stem,rows)]
    values=[json.loads(line) for line in text.splitlines() if line.strip()] if path.suffix.lower()=='.jsonl' else json.loads(text)
    if isinstance(values,dict):
        groups={k:v for k,v in values.items() if isinstance(v,list) and v and all(isinstance(x,dict) for x in v)}
        if not groups: groups={path.stem:[values]}
    else: groups={path.stem:values}
    tables=[]
    for name,records in groups.items():
        if not isinstance(records,list) or len(records)>20000: raise WorkbenchError('file_too_large','Table exceeds record limit')
        columns=list(dict.fromkeys(k for r in records if isinstance(r,dict) for k in r))
        if len(columns)>256: raise WorkbenchError('file_too_large','Table exceeds column limit')
        rows=[columns]+[[r.get(k) if isinstance(r.get(k),(str,int,float,bool,type(None))) else json.dumps(r.get(k),ensure_ascii=False) for k in columns] for r in records if isinstance(r,dict)]
        tables.append(_table(str(name),rows))
    return tables

def load_tables(path):
    path=Path(path); stat=path.stat()
    return _load(str(path.resolve()),stat.st_mtime_ns,stat.st_size)

def preview(path,sheet=0,offset=0,limit=100):
    from openpyxl.utils import get_column_letter
    tables=load_tables(path)
    if not 0<=sheet<len(tables) or offset<0 or not 1<=limit<=200: raise WorkbenchError('invalid_request','Invalid worksheet or row range')
    table=tables[sheet]; rows=table['rows']
    return {'sheets':[{'name':t['name'],'row_count':len(t['rows']),'column_count':max(map(len,t['rows']),default=0)} for t in tables],
        'sheet':sheet,'name':table['name'],'offset':offset,'total':len(rows),'columns':table['columns'],
        'merges':table['merges'],'widths':table['widths'],
        'rows':[{'number':i+1,'cells':[{'coordinate':f'{get_column_letter(j+1)}{i+1}','value':value,
            **table['styles'].get(f'{get_column_letter(j+1)}{i+1}',{})} for j,value in enumerate(row)]} for i,row in enumerate(rows[offset:offset+limit],offset)]}

def find_cells(path,q,sheet=None,match_case=False,whole_cell=False,offset=0,limit=200):
    from openpyxl.utils import get_column_letter
    if not isinstance(q,str) or not q.strip() or len(q)>256 or offset<0 or not 1<=limit<=200:
        raise WorkbenchError('invalid_request','Enter a search value under 256 characters and a valid result range')
    tables=load_tables(path)
    if sheet is not None and not 0<=sheet<len(tables): raise WorkbenchError('invalid_request','Unknown worksheet')
    needle=q if match_case else q.casefold()
    matches=[];total=0
    for index,table in enumerate(tables):
        if sheet is not None and index!=sheet: continue
        for row,values in enumerate(table['rows'],1):
            for column,value in enumerate(values,1):
                if value is None: continue
                text=str(value);candidate=text if match_case else text.casefold()
                if (candidate==needle if whole_cell else needle in candidate):
                    if offset<=total<offset+limit:
                        matches.append({'sheet':index,'name':table['name'],'row':row,'column':column,
                            'coordinate':f'{get_column_letter(column)}{row}','value':value})
                    total+=1
    return {'matches':matches,'total':total,'offset':offset,'limit':limit}

def compile_outcome_query(intent,available,question,history=None):
    """Bind a semantic cohort/outcome measure to complete source records.

    Exact identities and prefixes are resolved from actual records, and every
    compatible assessment is included without model-authored arithmetic.
    """
    outcomes=list(dict.fromkeys(intent.get('result_values',[])))
    polarity=intent.get('outcome')
    canonical={'pass':{'pass','passed'},'fail':{'fail','failed'}}
    if polarity in canonical:
        # The model chooses meaning, never an arbitrary union of outcome values.
        outcomes=sorted({str(row.get(column)).strip() for _,table in available.values()
            for row in table['records'] for column in table['columns']
            if str(row.get(column)).strip().casefold() in canonical[polarity]})
    entities=list(dict.fromkeys(intent.get('entity_values',[])))
    context=question+'\n'+'\n'.join(history or []) if intent.get('followup') else question
    # Bind literal identifiers/prefixes even when the semantic model omits
    # them. Only tokens present in one real source column qualify; ordinary
    # words and standalone thresholds cannot silently become cohort filters.
    user_context=question
    if intent.get('followup'):
        user_context+='\n'+'\n'.join(item for item in (history or []) if not item.lower().startswith('assistant:'))
    inferred=[]
    for token in dict.fromkeys(re.findall(r'\b[A-Za-z0-9]+\b',user_context)):
        if not (any(c.isalpha() for c in token) and any(c.isdigit() for c in token)): continue
        candidates={column for _,table in available.values() for column in table['columns']
            if any(str(row.get(column)).strip().casefold().startswith(token.casefold()) for row in table['records'])}
        if len(candidates)==1: inferred.append(token)
    if inferred:
        if entities and {v.casefold() for v in entities}!={v.casefold() for v in inferred}:
            raise WorkbenchError('invalid_query','Planned cohort does not match the source-bound user identifiers')
        entities=inferred
    if any(str(value).casefold() not in context.casefold() for value in entities):
        raise WorkbenchError('invalid_query','Cohort identities must come from the current question')
    threshold=intent.get('threshold')
    if threshold is not None:
        if not isinstance(threshold,(int,float)) or not math.isfinite(threshold) or intent.get('threshold_operator') not in {'gte','gt','lt','lte'}:
            raise WorkbenchError('invalid_query','Invalid numeric outcome rule')
        supplied=[float(v) for v in re.findall(r'(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])',user_context)]
        if threshold not in supplied: raise WorkbenchError('invalid_query','Outcome threshold must be supplied by the user')
        if not intent.get('score_columns'): raise WorkbenchError('needs_input','Specify the assessment score columns for the numeric rule')
    queries=[]; documents=set(); unavailable=[]
    for identifier,(doc,table) in available.items():
        if intent.get('scope')!='all' and intent.get('assessments') and table['name'] not in intent['assessments']: continue
        criteria=[]
        for column in table['columns']:
            values={str(row.get(column)).strip().casefold() for row in table['records']}
            if threshold is not None and column in intent['score_columns']:
                if any(isinstance(row.get(column),(int,float)) and not isinstance(row.get(column),bool) for row in table['records']):
                    criteria.append({'column':column,'operator':intent['threshold_operator'],'value':threshold})
            elif threshold is None and outcomes:
                bound=[value for value in outcomes if str(value).casefold() in values]
                if bound and (polarity in canonical or len(bound)==len(outcomes)):
                    criteria.append({'column':column,'operator':'in','value':bound})
        if not criteria:
            unavailable.append(table['name']);continue
        filters=[]
        if entities:
            candidates=[]
            for column in table['columns']:
                values={str(row.get(column)).strip().casefold() for row in table['records']}
                exact=all(str(entity).casefold() in values for entity in entities)
                partial=all(any(str(entity).casefold() in value for value in values) for entity in entities)
                if exact or partial: candidates.append((column,exact))
            exact=[candidate for candidate in candidates if candidate[1]]
            candidates=exact or candidates
            if len(candidates)!=1:
                raise WorkbenchError('needs_input','The cohort does not resolve to one identity column in '+table['name']+'. Specify the identity field.')
            column,is_exact=candidates[0]
            if is_exact: filters=[{'column':column,'operator':'in','value':entities}]
            elif len(entities)==1: filters=[{'column':column,'operator':'contains','value':entities[0]}]
            else: raise WorkbenchError('needs_input','Use complete identities or one cohort prefix for percentages')
        queries.append({'table':identifier,'columns':[],'filters':filters,'criteria':criteria})
        documents.add(doc['document_id'])
    if len(documents)>1: raise WorkbenchError('needs_input','Connect one results document for this multi-assessment percentage')
    if not queries: raise WorkbenchError('needs_input','No explicit result values were found. Specify the numeric pass rule before calculating percentages.')
    operation=intent.get('operation','percentage')
    # A consolidated score table already covers each assessment. Avoid counting
    # its duplicate weekly views as additional tests.
    consolidated=[query for query in queries if len(query['criteria'])>1]
    if threshold is not None and len(consolidated)==1:
        queries=consolidated;unavailable=[]
    first,*rest=queries
    return {**first,'operation':operation,'additional_queries':rest,'unavailable_assessments':unavailable}


def execute_query(table,plan):
    operation=plan.get('operation'); columns=plan.get('columns',[]); filters=plan.get('filters',[])
    if operation not in {'select','count','sum','average','min','max','percentage'} or not isinstance(columns,list) or not isinstance(filters,list) or len(columns)>12 or len(filters)>8:
        raise WorkbenchError('invalid_query','Unsupported table query')
    if any(c not in table['columns'] for c in columns): raise WorkbenchError('invalid_query','Query refers to an unknown column')
    for f in filters:
        if not isinstance(f,dict) or f.get('column') not in table['columns'] or f.get('operator') not in {'eq','ne','contains','in','gt','gte','lt','lte'}:
            raise WorkbenchError('invalid_query','Query has an unknown column or operator')
        value=f.get('value')
        if (f['operator']=='in' and (not isinstance(value,list) or not 1<=len(value)<=40 or any(not isinstance(v,(str,int,float)) for v in value)) or
            f['operator']!='in' and not isinstance(value,(str,int,float))):
            raise WorkbenchError('invalid_query','Query filter has an invalid value or alternative list')
    equalities={}
    for f in filters:
        if f['operator']=='eq':
            value=str(f['value']).strip().casefold()
            if f['column'] in equalities and equalities[f['column']]!=value:
                raise WorkbenchError('invalid_query','Query has mutually exclusive equalities; use an alternative-value filter')
            equalities[f['column']]=value
    def match(row,f):
        a=row.get(f['column']); b=f['value']; op=f['operator']
        if op=='in': return str(a).strip().casefold() in {str(v).strip().casefold() for v in b}
        if op in {'eq','ne','contains'}:
            a=str(a).strip().casefold(); b=str(b).strip().casefold()
            return a==b if op=='eq' else a!=b if op=='ne' else b in a
        try: a=float(a); b=float(b)
        except (ValueError,TypeError): return False
        return {'gt':a>b,'gte':a>=b,'lt':a<b,'lte':a<=b}[op]
    rows=[r for r in table['records'] if all(match(r,f) for f in filters)]
    result={'table':table['name'],'operation':operation,'scanned_rows':len(table['records']),'matched_rows':len(rows),'columns':columns,'filters':filters}
    if operation=='select': result.update(records=[{c:r.get(c) for c in columns or table['columns']} for r in rows[:40]],truncated=len(rows)>40)
    elif operation=='count':
        criteria=plan.get('criteria',[])
        if criteria:
            if not isinstance(criteria,list) or len(criteria)>12: raise WorkbenchError('invalid_query','Too many result count criteria')
            result['summaries']=[{'column':criterion.get('column'),'value':execute_query({**table,'records':rows},
                {'operation':'count','columns':[],'filters':[criterion]})['value'],'total':len(rows)} for criterion in criteria]
            if len(criteria)==1: result['value']=result['summaries'][0]['value']
        else: result['value']=len(rows)
    elif operation=='percentage':
        criteria=plan.get('criteria',[])
        if not criteria or len(criteria)>12:
            raise WorkbenchError('invalid_query','A percentage requires an explicit result value or a source/user supplied threshold for each assessment')
        # Reuse the same validated comparison contract for numerator predicates.
        summaries=[]
        for criterion in criteria:
            if criterion.get('operator')=='in':
                existing={str(row.get(criterion.get('column'))).strip().casefold() for row in table['records']}
                values=criterion.get('value',[])
                if isinstance(values,list) and any(str(value).strip().casefold() not in existing for value in values):
                    raise WorkbenchError('invalid_query','Percentage criterion values do not exist in '+table['name']+'. Choose a result column from categorical_values in the catalog; numeric mark columns do not contain PASS.')
            probe=execute_query({**table,'records':rows},{'operation':'count','columns':[], 'filters':[criterion]})
            summaries.append({'column':criterion['column'],'passed':probe['value'],'total':len(rows),
                'percentage':round(100*probe['value']/len(rows),2) if rows else None,'criterion':criterion})
        result['summaries']=summaries
    else:
        if not columns: raise WorkbenchError('invalid_query','Numeric aggregation requires at least one column')
        if len(columns)>1:
            result['summaries']=[{'column':column, **{k:v for k,v in execute_query(table,{**plan,'columns':[column]}).items() if k in {'value','numeric_rows'}}} for column in columns]
            return result
        numbers=[]
        for row in rows:
            value=row.get(columns[0])
            if isinstance(value,bool): continue
            try: number=float(value)
            except (TypeError,ValueError): continue
            if math.isfinite(number): numbers.append(number)
        result['numeric_rows']=len(numbers)
        result['value']=sum(numbers) if operation=='sum' else sum(numbers)/len(numbers) if operation=='average' and numbers else min(numbers) if operation=='min' and numbers else max(numbers) if operation=='max' and numbers else None
    return result
