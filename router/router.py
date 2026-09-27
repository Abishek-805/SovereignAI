import logging
from typing import Optional
from backend.contracts import WorkbenchError

logger = logging.getLogger(__name__)

class CapabilityRouter:
    def __init__(self, model_registry):
        self.model_registry = model_registry

    def classify_agent_goal(self, goal: str, *, document_ids=None, workspace_id=None, image=False) -> str:
        """Classify explicit agent requests using bounded metadata, without chat history."""
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 2000:
            raise WorkbenchError('invalid_goal', 'Describe a goal under 2,000 characters')
        if image:
            return 'VISION'
        if workspace_id:
            return 'CODING'
        if goal.lstrip().lower().startswith('calculate:'):
            return 'CALCULATION'
        if document_ids:
            return 'ARTIFACT' if any(word in goal.lower() for word in ('draft', 'create', 'prepare', 'generate', 'compare')) else 'DOCUMENT_QA'
        if 'csv' in goal.lower() and 'demo' in goal.lower():
            return 'CODING_DEMO'
        raise WorkbenchError('unsupported_goal', 'Choose documents, a coding workspace, an image, or use Calculate:')
        
    def route_request(self, task_type: str) -> str:
        """Route a request to the appropriate capability tier and model."""
        if task_type == 'text':
            capability = 'text'
            
        elif task_type == 'vision':
            capability = 'vision'
            
        elif task_type == 'code':
            # Prototype spec states: A coding specialist is optional and must beat the current baseline...
            capability = 'text'
            
        elif task_type == 'calculation':
            # Calculation is a tool, but if routed to a model, text is best
            capability = 'text'
            
        else:
            raise WorkbenchError('routing_error', f"Unknown task capability requested: {task_type}")

        specs = getattr(self.model_registry, 'specs', None)
        if specs is not None:
            spec = specs.get(capability)
            if spec is None or not spec.enabled:
                raise WorkbenchError('model_unavailable', f'{capability.capitalize()} model is missing or disabled')
            required_modality = 'image' if task_type == 'vision' else 'text'
            if required_modality not in spec.modalities:
                raise WorkbenchError('routing_error', f'{capability.capitalize()} model lacks {required_modality} capability')
        logger.info('Routing %s task to %s capability', task_type, capability)
        return capability
