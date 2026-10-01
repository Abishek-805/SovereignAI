"""Small auditable spelling corrections; never rewrite identifiers or quotations."""
from dataclasses import dataclass
import re

CORRECTIONS={'creat':'create','maintanance':'maintenance','calcluate':'calculate','shwo':'show'}
PROTECTED=re.compile(r'''```[\s\S]*?```|`[^`\n]*`|"[^"\n]*"|(?<!\w)'[^'\n]*'(?!\w)|\u201c[^\u201d\n]*\u201d|\S*[\\/@.:]\S*|\b\w*\d\w*\b''')

@dataclass(frozen=True)
class NormalizedRequest:
    original: str
    normalized: str
    corrections: tuple

def normalize_request(request):
    if not isinstance(request,str):return NormalizedRequest(request,request,())
    spans=[match.span() for match in PROTECTED.finditer(request)]
    changes=[]
    def replace(match):
        word=match.group()
        correction=CORRECTIONS.get(word.casefold())
        if not correction or any(start<=match.start()<end for start,end in spans):return word
        correction=correction.capitalize() if word[0].isupper() else correction
        changes.append({'start':match.start(),'original':word,'normalized':correction})
        return correction
    return NormalizedRequest(request,re.sub(r'\b[A-Za-z]+\b',replace,request),tuple(changes))

def is_greeting(request):
    return bool(re.fullmatch(r'\s*(?:hi|hello|hey|thanks|thank you|good morning|good evening)[!.?\s]*',request,re.I))

def worker_role(request, *, image=False, documents=False, history=None):
    """Only narrow, high precision shortcuts; ambiguous requests use reasoning."""
    if image:return 'vision'
    normalized=normalize_request(request).normalized
    from router.tool_registry import explicit_operation_requested
    if explicit_operation_requested(request,'file_edit') and re.search(
            r'\b(?:python|py|javascript|typescript|java|rust|html|css|opencv|program|script|code)\b|\.(?:py|js|ts|html|css)\b',normalized,re.I):
        return 'code'
    if re.fullmatch(r'\s*(?:fix that|make it work|continue)[.!?\s]*',normalized,re.I) and history:
        prior=next((item for item in reversed(history) if isinstance(item,str) and re.match(r'user:',item,re.I)),None)
        if prior and worker_role(prior.split(':',1)[1])=='code':return 'code'
    if is_greeting(normalized):
        return 'lightweight'
    # Closed, read-only request shapes, not a list of subjects. Evidence-bearing
    # questions and contextual follow-ups remain with semantic interpretation.
    if not documents and not history and len(normalized)<100 and not PROTECTED.search(normalized.rstrip('?.! \t\r\n')):
        if re.fullmatch(r'\s*(?:what can you do|tell me a short joke|what is (?:a|an) [A-Za-z ]{1,60}|explain what [A-Za-z ]{1,60} is)[?.!\s]*',normalized,re.I):
            return 'lightweight'
    return 'reasoning'
