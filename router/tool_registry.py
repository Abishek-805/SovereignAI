from typing import Callable, Dict, Any
from dataclasses import dataclass
import json
import time
import logging
import re
from backend.contracts import WorkbenchError

logger = logging.getLogger(__name__)

def explicit_operation_requested(goal, operation):
    """A necessary current-request guard, separate from model classification.

    This does not resolve targets or grant filesystem scope; those guards remain
    with the tool. Quoted text and negative clauses cannot authorize operations.
    Unsupported or ambiguous command wording must clarify rather than write.
    """
    if not isinstance(goal,str) or not goal.strip():return False
    text=re.sub(r'"[^"\n]*"|\u201c[^\u201d\n]*\u201d','',goal)
    text=re.sub(r"(?<!\w)'[^'\n]+'(?!\w)",'',text)
    text=re.sub(r"\b(?:do\s+not|don't|don’t|without|never|no)\b[^.;,\n]*",'',text,flags=re.I)
    verbs={
        'project_create':r'create|make|build|start', 'project_delete':r'delete|remove',
        'file_edit':r'create|write|generate|modify|edit|change|fix|repair|solve|update|replace|implement|add|make',
        'document_create':r'create|crate|write|add|make', 'document_update':r'update|modify|edit|change|rewrite|expand|details?|add|make', 'document_import':r'import|upload|add',
        'document_rename':r'rename', 'document_move':r'move', 'document_copy':r'copy|duplicate',
        'document_delete':r'delete|remove', 'file_delete':r'delete|remove',
        'document_duplicates':r'find|list|show|check|identify', 'document_deduplicate':r'delete|remove|deduplicate',
        'file_move':r'move|put|place', 'file_copy':r'copy|duplicate', 'folder_create':r'create|add|make|generate',
        'file_run':r'run|execute|test', 'terminal':r'run|execute',
        'automation_create':r'automate|schedule|repeat|every', 'automation_pause':r'pause|resume|stop',
        'automation_delete':r'delete|remove', 'automation_list':r'list|show|view|what',
    }
    if operation in {'document_duplicates','document_deduplicate'} and not (
            re.search(r'\b(?:duplicate|duplicates|deduplicate)\b',text,re.I) and
            re.search(r'\b(?:knowledge|library)\b',text,re.I)):
        return False
    if operation in {'project_create','project_delete'} and not re.search(r'\b(?:project|workspace)\b',text,re.I):
        return False
    if operation=='file_edit' and re.search(r'\b(?:want|need|put)\b.{0,80}\b(?:codes?|programs?|scripts?)\b',text,re.I):
        return re.search(r'\b(?:explain|describe|review|read)\b',text,re.I) is None
    if operation not in {'automation_list','document_duplicates'} and re.match(r'\s*(?:read|explain|describe|tell|show)\b',text,re.I):
        # An explanatory question mentioning an operation is not its invocation.
        if not re.search(r'\b(?:and|then)\s+(?:please\s+)?(?:'+verbs.get(operation,r'(?!)')+r')\b',text,re.I):return False
    return operation in verbs and re.search(r'\b(?:'+verbs[operation]+r')\b',text,re.I) is not None

@dataclass(frozen=True)
class ToolContract:
    arguments: tuple[str, ...]
    required: tuple[str, ...]
    permission: str = 'local_workbench'
    timeout_seconds: int = 300
    max_input_bytes: int = 12000
    max_output_bytes: int = 200000

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.contracts: Dict[str, ToolContract] = {}
        
    def register(self, name: str, func: Callable, contract: ToolContract | None = None):
        if name in self.tools:
            raise WorkbenchError('tool_error', f"Tool {name} already registered")
        self.tools[name] = func
        if contract:
            self.contracts[name] = contract
        logger.info(f"Registered tool: {name}")
        
    def execute(self, name: str, kwargs: dict) -> Any:
        if name not in self.tools:
            raise WorkbenchError('tool_not_found', f"Tool {name} is not available")
        contract=self.contracts.get(name)
        if contract:
            if contract.permission!='local_workbench' or set(kwargs)-set(contract.arguments) or any(
                    kwargs.get(key) is None for key in contract.required):
                raise WorkbenchError('tool_input','Tool inputs or permission are invalid')
            if len(json.dumps(kwargs,default=str).encode('utf-8'))>contract.max_input_bytes:
                raise WorkbenchError('resource_limit','Tool input exceeds its budget')
            
        try:
            started=time.monotonic()
            result=self.tools[name](**kwargs)
            if contract and (time.monotonic()-started>contract.timeout_seconds or
                             len(json.dumps(result,default=str).encode('utf-8'))>contract.max_output_bytes):
                raise WorkbenchError('resource_limit','Tool time or output budget exceeded')
            return result
        except Exception as e:
            if isinstance(e, WorkbenchError):
                raise
            raise WorkbenchError('tool_execution_failed', f"Tool {name} failed: {e}")
