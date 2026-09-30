"""Bounded record extraction and hybrid row/schema indexing."""
import csv
import json
import re
from io import StringIO
from backend.contracts import WorkbenchError, Page, Chunk
import hashlib

FORMATS={'.csv','.tsv','.json','.jsonl','.yaml','.yml','.xml','.toml','.ini','.cfg'}
METHODS={'spreadsheet_cells','structured_records'}

def record_pages(text, suffix):
    records=[]; emitted_chars=0
    def emit(value):
        if len(records)>=20000: raise WorkbenchError('file_too_large','Structured data exceeds 20,000 records')
        nonlocal emitted_chars
        parts=[]; visited=0; part_chars=0
        def flatten(item,path,depth=0):
            nonlocal visited,part_chars
            visited+=1
            if depth>40 or visited>100000: raise WorkbenchError('file_too_large','Structured data nesting or field limit exceeded')
            if isinstance(item,dict):
                for key,child in item.items(): flatten(child,f'{path}.{key}' if path else str(key),depth+1)
            elif isinstance(item,list):
                for index,child in enumerate(item): flatten(child,f'{path}[{index}]',depth+1)
            else:
                part=f'{path or "value"}: {json.dumps(item,ensure_ascii=False,default=str)}'
                part_chars+=len(part)+3
                if emitted_chars+part_chars>2_000_000: raise WorkbenchError('file_too_large','Structured text exceeds two million characters')
                parts.append(part)
        flatten(value,'')
        record=f'Record {len(records)+1}: '+' | '.join(parts)
        emitted_chars+=len(record)+1
        records.append(record)
    try:
        if suffix in {'.csv','.tsv'}:
            rows=csv.reader(StringIO(text), delimiter='\t' if suffix=='.tsv' else ',')
            headers=next(rows,[])
            if len(headers)>256: raise WorkbenchError('file_too_large','Table exceeds 256 columns')
            for row in rows:
                if len(row)>256: raise WorkbenchError('file_too_large','Table exceeds 256 columns')
                if any(value.strip() for value in row):
                    # Column ordinals preserve duplicate and empty header names.
                    emit({f'{headers[i] if i<len(headers) else "column"} [{i+1}]':value for i,value in enumerate(row)})
            if not records and headers: emit({f'column [{i+1}]':v for i,v in enumerate(headers)})
        elif suffix=='.jsonl':
            for line in text.splitlines():
                if line.strip(): emit(json.loads(line))
        elif suffix=='.xml':
            from lxml import etree
            xml_text=re.sub(r'^\s*<\?xml[^?]*\?>','',text,count=1)
            root=etree.fromstring(xml_text.encode(),parser=etree.XMLParser(resolve_entities=False,no_network=True,huge_tree=False))
            if root.getroottree().docinfo.doctype:
                raise WorkbenchError('parse_failed','XML document types and entities are not supported')
            for child in list(root) or [root]:
                values={}
                for node in child.iter():
                    if not isinstance(node.tag,str): continue
                    path=node.getroottree().getpath(node)
                    if node.text and node.text.strip(): values[path]=node.text.strip()
                    for key,value in node.attrib.items(): values[path+'/@'+key]=value
                if values: emit(values)
        else:
            if suffix=='.toml':
                import tomllib
                value=tomllib.loads(text)
            elif suffix in {'.ini','.cfg'}:
                from configparser import ConfigParser
                config=ConfigParser(interpolation=None); config.read_string(text)
                value={section:dict(config[section]) for section in config.sections()}
                if config.defaults(): value['DEFAULT']=dict(config.defaults())
            elif suffix in {'.yaml','.yml'}:
                import yaml
                # Aliases can expand exponentially; reject them before construction.
                if any(isinstance(token,yaml.tokens.AliasToken) for token in yaml.scan(text)):
                    raise WorkbenchError('parse_failed','YAML aliases are not supported; expand aliases before importing')
                value=yaml.safe_load(text)
            else: value=json.loads(text)
            for item in value if isinstance(value,list) else [value]: emit(item)
    except WorkbenchError: raise
    except Exception as exc:
        raise WorkbenchError('parse_failed','Could not parse this structured data; check its format') from exc
    result='\n'.join(records)
    if len(result)>2_000_000: raise WorkbenchError('file_too_large','Structured text exceeds two million characters')
    return [Page(result,None,method='structured_records')] if result.strip() else []

def structured_chunks(page,tokenizer,document_id,display_name,source_hash,size):
    lines=page.text.splitlines()
    context=(lines[0]+'\nColumns: '+lines[1][:256] if len(lines)>1 else lines[0]) if page.method=='spreadsheet_cells' else 'Structured records'
    result=[]
    def add(text,line_start,line_end,kind,identity):
        result.append(Chunk(hashlib.sha256(f'{document_id}:{source_hash}:{identity}'.encode()).hexdigest(),
                            document_id,source_hash,display_name,text,None,line_start,line_end,
                            page.method,retrieval_kind=kind))
    # Semantic search identifies a table from its title and opening records.
    # Every record remains fully indexed by FTS, without expensive row embeddings.
    summary='Table overview: '+display_name+'\n'+ '\n'.join(lines[:4])
    offsets=[(a,b) for a,b in tokenizer.encode(summary,add_special_tokens=False).offsets if b>a]
    if len(offsets)>128: summary=summary[:offsets[127][1]]
    add(summary,page.line_base,page.line_base+min(3,len(lines)-1),'schema',f'{page.line_base}:{context}:schema')
    start=1 if page.method=='spreadsheet_cells' else 0
    for index,line in enumerate(lines[start:],start):
        text=context+'\n'+line
        offsets=[(a,b) for a,b in tokenizer.encode(text,add_special_tokens=False).offsets if b>a]
        for segment,begin in enumerate(range(0,len(offsets),size)):
            end=min(begin+size,len(offsets))
            add(text[offsets[begin][0]:offsets[end-1][1]],page.line_base+index,page.line_base+index,
                'lexical',f'{page.line_base}:{context}:{index}:{segment}')
    return result
