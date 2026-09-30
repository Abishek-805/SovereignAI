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

def execute_query(table,plan):
    operation=plan.get('operation'); columns=plan.get('columns',[]); filters=plan.get('filters',[])
    if operation not in {'select','count','sum','average','min','max'} or not isinstance(columns,list) or not isinstance(filters,list) or len(columns)>12 or len(filters)>8:
        raise WorkbenchError('invalid_query','Unsupported table query')
    if any(c not in table['columns'] for c in columns): raise WorkbenchError('invalid_query','Query refers to an unknown column')
    for f in filters:
        if not isinstance(f,dict) or f.get('column') not in table['columns'] or f.get('operator') not in {'eq','ne','contains','gt','gte','lt','lte'} or not isinstance(f.get('value'),(str,int,float)):
            raise WorkbenchError('invalid_query','Query has an unknown column or operator')
    def match(row,f):
        a=row.get(f['column']); b=f['value']; op=f['operator']
        if op in {'eq','ne','contains'}:
            a=str(a).strip().casefold(); b=str(b).strip().casefold()
            return a==b if op=='eq' else a!=b if op=='ne' else b in a
        try: a=float(a); b=float(b)
        except (ValueError,TypeError): return False
        return {'gt':a>b,'gte':a>=b,'lt':a<b,'lte':a<=b}[op]
    rows=[r for r in table['records'] if all(match(r,f) for f in filters)]
    result={'table':table['name'],'operation':operation,'scanned_rows':len(table['records']),'matched_rows':len(rows),'columns':columns,'filters':filters}
    if operation=='select': result.update(records=[{c:r.get(c) for c in columns or table['columns']} for r in rows[:40]],truncated=len(rows)>40)
    elif operation=='count': result['value']=len(rows)
    else:
        if len(columns)!=1: raise WorkbenchError('invalid_query','Numeric aggregation requires one column')
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
