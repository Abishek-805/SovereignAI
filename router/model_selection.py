"""Hard compatibility/admission, measured quality first, then latency + switch."""
from dataclasses import dataclass, field
import math
import time
from .resource_admission import ResourceSnapshot, ResourceSampler, admit_resources


@dataclass(frozen=True)
class SelectionPolicy:
    quality_threshold: float | None = None
    latency_weight: float = 1.0
    switch_weight: float = 1.0
    quality_threshold_source: str | None = None

    def __post_init__(self):
        # Latency and switch are already in seconds. Arbitrary coefficients
        # belong in an explicitly evaluated experiment, not production ranking.
        if self.latency_weight!=1.0 or self.switch_weight!=1.0:
            raise ValueError('Production selection uses unweighted measured latency plus switch seconds')
        if self.quality_threshold is not None and (isinstance(self.quality_threshold,bool) or
                not isinstance(self.quality_threshold,(int,float)) or not math.isfinite(self.quality_threshold) or
                not 0<=self.quality_threshold<=1):
            raise ValueError('Quality floor must be a finite fraction or None')


@dataclass
class ModelSelection:
    capability: str
    modality: str
    required_context: int | None
    registry_key: str | None = None
    selected_model: str | None = None
    candidate_models: list = field(default_factory=list)
    candidate_rejection_reasons: dict = field(default_factory=dict)
    route_reason: str = ''
    available_context: int | None = None
    resource_admission: dict | None = None
    current_residency: str | None = None
    switch_required: bool | None = None
    routing_time: float | None = None
    fallback: dict | None = None
    candidate_rejection_codes: dict = field(default_factory=dict)
    failure_category: str | None = None
    selection_policy: str = 'hard_filter_quality_first_latency_switch_residency_v2'
    selection_evidence: dict = field(default_factory=dict)

    def to_dict(self):
        return {key:value for key,value in vars(self).items() if key!='registry_key'}


def measured_value(spec, capability, name):
    value=dict(spec.measured_metrics).get(capability+'.'+name)
    return float(value) if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0 and (name!='quality' or value<=1) else None


class ModelSelector:
    def __init__(self, registry, sampler=None, policy=None):
        self.registry=registry
        self.sampler=sampler or ResourceSampler()
        self.policy=policy or SelectionPolicy()

    def select(self, capability, *, modality='text', required_context=None, resource_snapshot=None, current_residency=None):
        started=time.perf_counter()
        if required_context is not None and (not isinstance(required_context,int) or isinstance(required_context,bool) or required_context<1):
            raise ValueError('Required context must be a positive token count or None')
        snapshot=self.sampler.sample() if resource_snapshot is None else resource_snapshot
        if isinstance(snapshot,dict):
            snapshot=ResourceSnapshot(**snapshot)
        decision=ModelSelection(capability,modality,required_context,current_residency=current_residency)
        eligible=[]
        resource_blocked_compatible=False
        for key,spec in self.registry.specs.items():
            reasons=[]
            if not spec.enabled:reasons.append('disabled')
            if not spec.license_reviewed or not spec.license_id or not spec.license_reference:
                reasons.append('license_not_reviewed')
            try:
                if not self.registry.installed(spec):reasons.append('missing_model_assets')
            except Exception as error:
                reasons.append('invalid_model_assets: '+str(error))
            if spec.runtime_adapter!='llama.cpp':reasons.append('unsupported_runtime')
            elif callable(getattr(self.registry,'runtime_available',None)) and not self.registry.runtime_available(spec):
                reasons.append('runtime_unavailable')
            if capability not in spec.supported_capabilities:reasons.append('unsupported_capability')
            if modality not in spec.modalities:reasons.append('unsupported_modality')
            if required_context is not None and required_context>spec.context:reasons.append('insufficient_context')
            codes=[reason.split(':',1)[0] for reason in reasons]
            compatible=not reasons
            admission=admit_resources(spec,snapshot,resident=current_residency in (spec.identifier,spec.alias),required_context=required_context)
            if admission['status']=='rejected':
                reasons.extend(admission['reasons']);codes.extend(admission['reason_codes'])
                resource_blocked_compatible=resource_blocked_compatible or compatible
            quality=measured_value(spec,capability,'quality')
            if self.policy.quality_threshold is not None:
                if quality is None:reasons.append('quality_threshold_unmeasured');codes.append('quality_threshold_unmeasured')
                elif quality<self.policy.quality_threshold:reasons.append('quality_below_threshold');codes.append('quality_below_threshold')
            latency=measured_value(spec,capability,'latency_seconds')
            switch=0.0 if current_residency in (spec.identifier,spec.alias) else measured_value(spec,capability,'switch_seconds')
            # Unknown quality/cost does not become a fabricated zero or a comparable score.
            score=None if quality is None or latency is None or switch is None else latency+switch
            if score is not None and not math.isfinite(score):score=None
            candidate={'model_id':spec.identifier,'registry_key':key,'display_name':spec.display_name or spec.alias,
                       'capabilities':list(spec.supported_capabilities),'modalities':list(spec.modalities),
                       'context_limit':spec.context,'admissible':not reasons,'admission':admission,
                       'quality':quality,'latency_seconds':latency,'switch_seconds':switch,'measured_cost':score,
                       'rejection_codes':codes,'runtime_alias':spec.alias,'runtime':spec.runtime_adapter,
                       'quantization':spec.quantization,'license_id':spec.license_id,'license_reviewed':spec.license_reviewed}
            decision.candidate_models.append(candidate)
            if reasons:
                decision.candidate_rejection_reasons[spec.identifier]=reasons
                decision.candidate_rejection_codes[spec.identifier]=codes
            else:eligible.append((key,spec,candidate))
        admissible_count=len(eligible)
        if not eligible:
            decision.route_reason='No model satisfies capability, modality, context, availability and observed resource policy; no implicit fallback.'
            decision.failure_category='RESOURCE_FAILURE' if resource_blocked_compatible else 'CANDIDATE_FAILURE'
            decision.resource_admission={'status':'rejected','observed':snapshot.to_dict(),
                                         'reason_codes':sorted({code for candidate in decision.candidate_models for code in candidate['admission']['reason_codes']})}
        else:
            # Accuracy is the first objective. Runtime cost only breaks ties
            # between equally capable candidates; unknown quality is not zero.
            quality_comparable=all(item[2]['quality'] is not None for item in eligible)
            if quality_comparable:
                best_quality=max(item[2]['quality'] for item in eligible)
                eligible=[item for item in eligible if item[2]['quality']==best_quality]
            if all(item[2]['measured_cost'] is not None for item in eligible):
                chosen=min(eligible,key=lambda item:(item[2]['measured_cost'],
                    current_residency not in (item[1].identifier,item[1].alias),item[1].identifier))
                reason=('Highest measured capability quality, then ' if quality_comparable else 'Quality evidence incomplete; ')+ 'lowest measured latency plus required switch cost; no claim of global optimality.'
                decision.selection_evidence={'status':'measured','cost_unit':'seconds','comparison':('quality descending, then latency_seconds + required_switch_seconds' if quality_comparable else 'latency_seconds + required_switch_seconds; quality unknown')}
            else:
                resident=[item for item in eligible if current_residency in (item[1].identifier,item[1].alias)]
                chosen=resident[0] if resident else eligible[0]
                reason=('Only admissible candidate.' if len(eligible)==1 else 'Retained admissible resident candidate.' if resident else 'Stable registry priority among admissible candidates.')+' Comparable quality/latency/switch measurements are incomplete; optimizer not established.'
                decision.selection_evidence={'status':'incomplete','comparison':None}
                if quality_comparable:
                    reason='Highest measured capability quality. '+reason
                    decision.selection_evidence['comparison']='quality descending; runtime cost incomplete'
            decision.selection_evidence['quality_comparable']=quality_comparable
            key,spec,candidate=chosen
            decision.registry_key=key;decision.selected_model=spec.identifier;decision.route_reason=reason
            decision.available_context=spec.context;decision.resource_admission=candidate['admission']
            decision.switch_required=None if current_residency is None else current_residency not in (spec.identifier,spec.alias)
        decision.selection_evidence.update({'quality_threshold':self.policy.quality_threshold,
            'quality_threshold_source':self.policy.quality_threshold_source,
            'registered_candidates':len(decision.candidate_models),'admissible_candidates':admissible_count})
        decision.routing_time=time.perf_counter()-started
        return decision
