"""Worker-role broker; selection proposes resources, never grants tool authority."""
from backend.contracts import WorkbenchError
from .model_selection import ModelSelector, measured_value


ROLE_CAPABILITIES={'lightweight':'text','reasoning':'text','code':'code','vision':'vision'}


class ModelBroker:
    def __init__(self,registry,sampler=None,policy=None):
        self.registry=registry
        self.selector=ModelSelector(registry,sampler=sampler,policy=policy)

    def select(self,role,*,modality='text',required_context=None,resource_snapshot=None,
               current_residency=None,task_affinity=None,task_type=None):
        if role not in ROLE_CAPABILITIES:raise ValueError('Unknown worker role')
        # Omitted residency is observed, not inferred from a UI display label.
        if current_residency is None:
            current_residency=self.registry.verified_residency()
        elif any(current_residency==spec.alias and spec.alias!=spec.identifier
                 for spec in self.registry.specs.values()):
            # Legacy alias input cannot establish whether a configured Gemma or
            # Qwen actually owns the text runtime; resolve the real profile.
            current_residency=self.registry.verified_residency()
        decision=self.selector.select(ROLE_CAPABILITIES[role],modality=modality,
            required_context=required_context,resource_snapshot=resource_snapshot,
            current_residency=current_residency)
        decision.worker_role=role
        eligible=[]
        for candidate in decision.candidate_models:
            spec=self.registry.specs[candidate['registry_key']]
            candidate['worker_roles']=list(spec.worker_roles)
            candidate['model_file']=spec.model_file
            candidate['projector_file']=spec.projector_file
            candidate['revision']=spec.revision
            if task_type is not None:
                measurement_scope=ROLE_CAPABILITIES[role]+'.'+task_type
                candidate['quality']=measured_value(spec,measurement_scope,'quality')
                candidate['latency_seconds']=measured_value(spec,measurement_scope,'latency_seconds')
                candidate['measured_cost']=None
                candidate['measurement_scope']=measurement_scope
            if role not in spec.worker_roles:
                candidate['admissible']=False
                candidate['rejection_codes']=candidate['rejection_codes']+['unsuitable_worker_role']
                decision.candidate_rejection_codes[spec.identifier]=candidate['rejection_codes'][:]
                decision.candidate_rejection_reasons.setdefault(spec.identifier,[]).append('unsuitable_worker_role')
            if candidate['admissible']:eligible.append(candidate)
        # Keep all unknown measurements as None. Only compare an objective when
        # the complete eligible set has measurements for that objective.
        quality_comparable=bool(eligible) and all(item['quality'] is not None for item in eligible)
        comparison=[]
        for field,descending in (('quality',True),('latency_seconds',False)):
            if eligible and all(item[field] is not None for item in eligible):
                optimum=(max if descending else min)(item[field] for item in eligible)
                eligible=[item for item in eligible if item[field]==optimum]
                comparison.append(field+(' descending' if descending else ' ascending'))
        if eligible:
            affinity=[item for item in eligible if task_affinity in (item['model_id'],item['runtime_alias'])]
            warm=[item for item in eligible if current_residency in (item['model_id'],item['runtime_alias'])]
            if affinity:eligible=affinity;comparison.append('task affinity')
            elif warm:eligible=warm;comparison.append('verified residency')
            elif all(item['switch_seconds'] is not None for item in eligible):
                lowest=min(item['switch_seconds'] for item in eligible)
                eligible=[item for item in eligible if item['switch_seconds']==lowest]
                comparison.append('switch_seconds ascending')
            chosen=min(eligible,key=lambda item:item['model_id'])
            decision.registry_key=chosen['registry_key'];decision.selected_model=chosen['model_id']
            decision.resource_admission=chosen['admission'];decision.available_context=chosen['context_limit']
            decision.is_warm=current_residency in (chosen['model_id'],chosen['runtime_alias'])
            decision.switch_required=not decision.is_warm
            decision.failure_category=None
            decision.route_reason='Worker role '+role+'; hard compatibility passed; resource admission '+chosen['admission']['status']+'. '+(
                ', then '.join(comparison) if comparison else 'Stable identity priority; comparable performance measurements unavailable.')
        else:
            decision.registry_key=None;decision.selected_model=None;decision.available_context=None
            decision.is_warm=False;decision.switch_required=None
            role_candidates=[item for item in decision.candidate_models if role in item['worker_roles']]
            decision.failure_category=('RESOURCE_FAILURE' if role_candidates and any(
                item['admission']['status']=='rejected' and all(code in item['admission']['reason_codes']
                for code in item['rejection_codes']) for item in role_candidates) else 'CANDIDATE_FAILURE')
            decision.resource_admission={'status':'rejected'}
            decision.route_reason='No admissible worker for role '+role+'; no implicit role fallback.'
        decision.selection_policy='worker_role_hard_constraints_lexicographic_v1'
        decision.selection_evidence.update({'comparison':comparison,'task_affinity':task_affinity,
            'unknown_metrics_policy':'not comparable; never fabricated','worker_role':role,
            'admissible_candidates':sum(item['admissible'] for item in decision.candidate_models),
            'quality_comparable':quality_comparable,'task_type':task_type})
        return decision

    def acquire(self,decision,*,persist_before_swap=None):
        if decision.selected_model is None or decision.registry_key is None:
            raise WorkbenchError('model_unavailable',decision.route_reason)
        spec=self.registry.specs.get(decision.registry_key)
        if spec is None or spec.identifier!=decision.selected_model or decision.worker_role not in spec.worker_roles:
            raise WorkbenchError('model_unavailable','Selected worker identity or role changed; select again')
        # The registry rechecks actual ownership/profile and invokes checkpoint
        # only if a swap is necessary, under its existing single-server lock.
        return self.registry.acquire_lease(decision.registry_key,persist_before_swap=persist_before_swap)
