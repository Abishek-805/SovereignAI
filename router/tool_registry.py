from typing import Callable, Dict, Any
from dataclasses import dataclass
import json
import time
import logging
from backend.contracts import WorkbenchError

logger = logging.getLogger(__name__)

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
