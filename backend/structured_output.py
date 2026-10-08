"""Strict JSON boundary shared by internal workers and the public adapter."""
import json
import re
from backend.contracts import WorkbenchError


def normalize_json(text):
    if not isinstance(text,str):raise WorkbenchError('generation_format','Structured content must be text')
    fence=re.fullmatch(r'\s*```(?:json)?\s*\n(.*?)\n```\s*',text,re.S)
    candidate=fence[1] if fence else text
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    try:
        value=json.loads(candidate,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        return json.dumps(value,ensure_ascii=False,allow_nan=False)
    except (ValueError,TypeError) as exc:
        raise WorkbenchError('generation_format','Malformed or ambiguous structured JSON') from exc


def normalize_completion(result, payload):
    if payload.get('response_format',{}).get('type') not in {'json_object','json_schema'}:return result
    for choice in result.get('choices',[]):
        if choice.get('finish_reason')!='stop':raise WorkbenchError('generation_format','Incomplete structured JSON')
        choice['message']['content']=normalize_json(choice['message'].get('content'))
    return result


def apply_explicit_json_contract(payload):
    """Honor an explicit output-format request using native JSON constraints."""
    if payload.get('response_format') or payload.get('stream'):return payload
    messages=payload.get('messages',[])
    latest=next((m.get('content') for m in reversed(messages) if m.get('role')=='user'),'')
    if isinstance(latest,str) and re.match(r'\s*(?:return|output|respond with)\s+(?:(?:exactly|only|strict)\s+)+JSON\b',latest,re.I):
        return {**payload,'response_format':{'type':'json_object'}}
    return payload
