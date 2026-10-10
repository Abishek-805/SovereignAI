"""Exact, source-verified identifiers shared by deterministic table lookups."""
from dataclasses import dataclass, asdict,field
import re
import time
import unicodedata
from rag.tables import identity_value, exact_identity_columns,numeric_value
from backend.contracts import WorkbenchError


def full_identifiers(text):
    text=unicodedata.normalize('NFC',text)
    return list(dict.fromkeys(token for token in re.findall(r'(?<!\w)[\w]+(?:[.-][\w]+)*(?!\w)', text)
        if any(c.isalpha() for c in token) and any(c.isdigit() for c in token)
        or re.fullmatch(r'0\d{2,}',token)))


@dataclass
class IdentifierResolution:
    raw_text: str
    explicit: list
    canonical: list
    provenance: list
    unresolved: list
    matches: list
    timings: dict
    diagnostics: list=field(default_factory=list)

    def to_dict(self):
        return {**asdict(self), 'complete': not self.unresolved}


def resolve_identifiers(question, available, history=None):
    started=time.perf_counter()
    identity_text=question
    for doc,_ in available.values():
        name=doc.get('display_name','')
        if name:identity_text=re.sub(re.escape(name),' ',identity_text,flags=re.I)
    assessment_codes={re.sub(r'\W','',field).casefold() for _,table in available.values() for field in table['columns']}
    assessment_codes.update(re.sub(r'\W','',str(row.get(field))).casefold()
        for _,table in available.values() for field in table['columns']
        if words(field)&{'assessment','test','subject'} for row in table['records'])
    assessment_families={re.sub(r'\d+$','',code) for code in assessment_codes if re.fullmatch(r'[a-z]+\d+',code)}
    requested=full_identifiers(identity_text)
    source_values={identity_value(row.get(column)) for _,table in available.values() for column in table['columns'] for row in table['records']}
    unknown_assessments=[token for token in requested if identity_value(token) not in source_values and re.sub(r'\d+$','',token.casefold()) in assessment_families
                         and token.casefold() not in assessment_codes]
    if unknown_assessments:
        raise WorkbenchError('needs_input','Requested assessment is unavailable in the authorized source schema: '+', '.join(unknown_assessments)+'. No score was inferred.')
    explicit=[token for token in requested if re.sub(r'\W','',token).casefold() not in assessment_codes]
    parsed=time.perf_counter()
    canonical=list(explicit)
    provenance=[{'identifier':value,'origin':'current_user'} for value in explicit]
    unresolved=[]
    previous=next((item[6:] for item in reversed(history or [])
                   if isinstance(item,str) and item.startswith('User: ')), '')
    antecedents=[token for token in full_identifiers(previous) if re.sub(r'\W','',token).casefold() not in assessment_codes]
    if not {identity_value(v) for v in explicit}&{identity_value(v) for v in antecedents}:
        antecedents=[]
    # Only a coordinated bare number is shorthand; thresholds and assessment codes are not.
    if explicit:
        for alias in re.findall(r'\band\s+(\d+)\b(?!\s*(?:marks?|scores?|percent|%|students?|records?|years?))',identity_text,re.I):
            candidates=[value for value in antecedents if re.search(r'(\d+)$',value)
                        and int(re.search(r'(\d+)$',value)[1])==int(alias)
                        and any(exact_identity_columns(table,[value]) for _,table in available.values())]
            if len(candidates)==1:
                if identity_value(candidates[0]) not in {identity_value(v) for v in canonical}:
                    canonical.append(candidates[0])
                    provenance.append({'identifier':candidates[0],'origin':'immediate_user_antecedent',
                                       'alias':alias,'verified_in_scope':True})
            else:unresolved.append(alias)
    contextual=time.perf_counter()
    matches=[]
    for key,(doc,table) in available.items():
        for column,counts in exact_identity_columns(table,canonical).items():
            matches.append({'table':key,'document_id':doc['document_id'],'version_hash':doc.get('active_hash',doc.get('version_hash')),
                            'identity_column':column,'counts':counts,
                            'record_rows':[number for number,row in zip(table.get('record_rows',range(2,len(table['records'])+2)),table['records'])
                                           if identity_value(row.get(column)) in {identity_value(v) for v in canonical}]})
    return IdentifierResolution(question,explicit,canonical,provenance,unresolved,matches,
        {'parsing_seconds':parsed-started,'history_resolution_seconds':contextual-parsed,
         'exact_id_lookup_seconds':time.perf_counter()-contextual})


def words(text):
    return {word.rstrip('s') for word in re.findall(r'[a-z]+',text.casefold()) if len(word)>2}


def named_field(field,question):
    tokens=re.findall(r'[A-Za-z]+|\d+',field)
    return bool(tokens) and re.search(r'(?<!\w)'+r'[\W_]*'.join(re.escape(token) for token in tokens)+r'(?!\w)',question,re.I) is not None


def compile_exact_lookup(question,available,history=None,prior=None):
    """Compile only unambiguous result lookups; other operations retain their existing planner."""
    if re.search(r'\b(count|how many|average|sum|highest|lowest|top|pass|passed|fail|percentage|create|delete|update|why|reason|rationale|justification)\b',question,re.I):return None
    resolution=resolve_identifiers(question,available,history)
    if not resolution.explicit:return None
    query_words=words(question)
    candidates=[]
    named_tables={key for key,(_,table) in available.items() if named_field(table['name'],question) and
                  (any(c.isdigit() for c in table['name']) or re.search(r'\b(?:sheet|table)\s+'+re.escape(table['name'])+r'\b',question,re.I))}
    named_measurements={field for _,table in available.values() for field in table['columns']
                        if named_field(field,question) and (any(c.isdigit() for c in field) or
                           any(numeric_value(row.get(field)) is not None for row in table['records']))}
    for key,(doc,table) in available.items():
        if named_tables and key not in named_tables:continue
        discovered=exact_identity_columns(table,resolution.canonical)
        # Exact absent IDs still produce not-found when a unique assessment schema is named.
        fields=[field for field in table['columns'] if named_field(field,question) or
                not any(c.isdigit() for c in field) and (len(words(field)&query_words)>=2
                or words(field) and words(field)<=query_words)]
        fields=[field for field in fields if field not in discovered]
        if not named_measurements and re.search(r'\b(results?|marks?|scores?)\b',question,re.I):
            fields.extend(field for field in table['columns'] if field not in discovered and
                    (re.fullmatch(r'[A-Za-z][A-Za-z _-]*\d+',field) or words(field)&{'score','result','mark','total'})
                    and (any(numeric_value(row.get(field)) is not None for row in table['records']) or
                         all(row.get(field) is None or str(row.get(field)).strip().casefold() in {'','ab'} for row in table['records'])))
            fields.extend(field for field in table['columns'] if words(field)&{'assessment','test','subject','measurement','metric'} and
                          not any(numeric_value(row.get(field)) is not None for row in table['records']))
            if not fields:
                fields.extend(field for field in table['columns'] if field not in discovered and
                    not re.search(r'\b(id|identifier|number|phone|year|date|time|email|group|age|serial)\b',field,re.I) and
                    any(numeric_value(row.get(field)) is not None for row in table['records']))
        filters=[]
        # Long tables bind assessment labels to their actual source values.
        for field in table['columns']:
            if field in discovered:continue
            labels=[value for value in dict.fromkeys(str(row.get(field)) for row in table['records'])
                    if numeric_value(value) is None and any(c.isalpha() for c in value)
                    and (named_field(value,question) or len(words(value)&query_words)>=2)]
            if labels:
                filters.append({'column':field,'operator':'in','value':labels})
                fields.extend(column for column in table['columns'] if words(column)&{'score','result','mark','total'})
                fields.append(field)
        fields=list(dict.fromkeys(fields))
        if not fields:continue
        identity_fields=list(discovered)
        if len(identity_fields)>1:raise WorkbenchError('needs_input','Identifiers match multiple fields; choose the identity field.')
        if identity_fields:identity=identity_fields[0]
        else:
            # Infer an absent-ID field only from the verified identifier family, never a header guess.
            family=re.sub(r'\d+$','',resolution.explicit[0]).casefold()
            possible=[column for column in table['columns'] if family and any(
                str(row.get(column)).casefold().startswith(family) for row in table['records'])]
            if len(possible)!=1:continue
            identity=possible[0]
        filters.insert(0,{'column':identity,'operator':'in','value':resolution.canonical})
        candidates.append({'table':key,'operation':'select','columns':[identity,*fields],
            'filters':filters,'requested_entities':resolution.canonical,
            'identity_column':identity,'identity_resolution':resolution.to_dict(),
            'unresolved_identifiers':resolution.unresolved})
    verified={match['table'] for match in resolution.matches}
    with_records=[plan for plan in candidates if plan['table'] in verified]
    if with_records:candidates=with_records
    from rag.table_resolution import select_logical_plan
    return select_logical_plan(candidates,available,prior)
