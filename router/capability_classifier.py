"""Evaluated CPU intent candidates. Scores are uncalibrated, never write permission.

Production gate is deliberately closed until independent release evidence exists.
The offline evaluator calls candidate classes directly; application-facing predict
always abstains without allocating an embedding runtime or reading user files.
"""
from collections import Counter
from dataclasses import asdict, dataclass
import re
import time

LABELS=('answer','calculate','clarify','create_report','edit_code','inspect_code','search_documents','vision')

# The registry describes routing categories, not permission to execute tools.
TAXONOMY={
    'answer':{'stage':'GENERAL','capability':'text','intents':['GENERAL','CONVERSATION']},
    'clarify':{'stage':'GENERAL','capability':None,'intents':['CLARIFICATION']},
    'search_documents':{'stage':'EVIDENCE','capability':'text','intents':['RETRIEVAL','DOCUMENT_ANALYSIS']},
    'create_report':{'stage':'EVIDENCE','capability':'text','intents':['REPORT_GENERATION']},
    'edit_code':{'stage':'ACTION','capability':'code','intents':['CODE_GENERATE','CODE_EDIT','CODE_DEBUG']},
    'inspect_code':{'stage':'ACTION','capability':'code','intents':['CODE_READ']},
    'application_tools':{'stage':'ACTION','capability':'agent','intents':['AGENT']},
    'vision':{'stage':'VISION','capability':'vision','intents':['VISION']},
    'calculate':{'stage':'CALCULATION','capability':'calculation','intents':['CALCULATION']},
}
V3_LABELS=tuple(TAXONOMY)

@dataclass(frozen=True)
class CapabilityPrediction:
    predicted: str | None
    decision: str
    method: str
    score: float | None
    margin: float | None
    classifier_time_ms: float
    production_enabled: bool = False
    mutation_authorized: bool = False
    reason: str = 'Release gate closed; defer to structured intent planner'
    def to_dict(self):return asdict(self)

class ConservativeCapabilityClassifier:
    """No production authority while evaluated candidates fail release gates."""
    def predict(self, text, context=None):
        start=time.perf_counter()
        if not isinstance(text,str) or not text.strip():
            decision='clarify';reason='An empty request needs clarification'
        else:
            decision='defer_to_planner';reason='CPU candidates have not passed independent safety and quality release gates'
        return CapabilityPrediction(None,decision,'disabled_evaluated_cpu',None,None,
                                    (time.perf_counter()-start)*1000,reason=reason)

def request_text(task):
    context=task.get('context',{})
    # Context is metadata only. Availability must not force evidence/mutation.
    markers=' '.join(key+'_available' for key in ('documents','workspace','image') if context.get(key) is True)
    return task['text']+ ('\nContext metadata: '+markers if markers else '')

def terms(text, character=False):
    value=' '.join(text.lower().split())
    if character:
        value=' '+value+' '
        return [value[i:i+n] for n in (3,4,5) for i in range(max(0,len(value)-n+1))]
    words=re.findall(r'\w+',value)
    return words+[' '.join(words[i:i+2]) for i in range(len(words)-1)]

class TfidfFeatures:
    def __init__(self,texts,character=False,max_features=20000):
        import numpy as np
        self.character=character
        df=Counter(term for text in texts for term in set(terms(text,character)))
        selected=sorted(sorted(df,key=lambda term:(-df[term],term))[:max_features])
        self.vocab={term:index for index,term in enumerate(selected)}
        self.idf=np.array([np.log((1+len(texts))/(1+df[term]))+1 for term in selected],dtype=np.float32)
    def encode(self,texts):
        import numpy as np
        rows=np.zeros((len(texts),len(self.vocab)),dtype=np.float32)
        for row,text in enumerate(texts):
            for term,count in Counter(terms(text,self.character)).items():
                index=self.vocab.get(term)
                if index is not None:rows[row,index]=(1+np.log(count))*self.idf[index]
        return rows/np.maximum(np.linalg.norm(rows,axis=1,keepdims=True),1e-12)

class LinearTfidfCandidate:
    """L2-regularized least squares multiclass linear model, NumPy dual solve.

    Fits coefficients to +/-1 labels, not nearest labeled prototypes. No sklearn
    dependency. Ridge coefficient alpha is frozen before held-out inspection.
    """
    def __init__(self,tasks,mode='word',alpha=.5,labels=None):
        import numpy as np
        if mode not in {'word','character','hybrid'}:raise ValueError('Unknown feature mode')
        self.method=mode+'-tfidf-ridge';self.labels=tuple(labels or LABELS)
        texts=[request_text(task) for task in tasks]
        self.encoders=[TfidfFeatures(texts,mode=='character')]
        if mode=='hybrid':self.encoders=[TfidfFeatures(texts),TfidfFeatures(texts,True)]
        x=self.encode(texts)
        y=np.full((len(tasks),len(self.labels)),-1,dtype=np.float32)
        for index,task in enumerate(tasks):y[index,self.labels.index(task['expected'])]=1
        coefficients=np.linalg.solve(x@x.T+alpha*np.eye(len(x),dtype=np.float32),y)
        self.weights=(x.T@coefficients).astype(np.float32)
    def encode(self,texts):
        import numpy as np
        parts=[encoder.encode(texts) for encoder in self.encoders]
        return np.concatenate(parts,axis=1)/np.sqrt(len(parts))
    def scores(self,task):
        return self.encode([request_text(task)])[0]@self.weights

class EmbeddingPrototypeCandidate:
    """Installed BGE CPU embeddings with maximum similarity per labeled class."""
    method='local-bge-prototypes'
    def __init__(self,tasks,encoder,labels=None):
        self.labels=tuple(labels or LABELS);self.encoder=encoder
        self.example_labels=[task['expected'] for task in tasks]
        self.vectors=encoder.encode([request_text(task) for task in tasks])
    def scores(self,task):
        import numpy as np
        similarities=self.vectors@self.encoder.encode([request_text(task)])[0]
        return np.array([max(similarities[index] for index,label in enumerate(self.example_labels) if label==candidate)
                         for candidate in self.labels])

class HierarchicalCandidate:
    """Learn a broad capability family first, then its member task labels."""
    def __init__(self,tasks,mode='hybrid',alpha=.5,encoder=None):
        self.labels=V3_LABELS
        self.method='hierarchical-'+('local-bge-prototypes' if encoder else mode+'-tfidf-ridge')
        groups=tuple(dict.fromkeys(value['stage'] for value in TAXONOMY.values()))
        factory=lambda rows,labels:EmbeddingPrototypeCandidate(rows,encoder,labels) if encoder else LinearTfidfCandidate(rows,mode,alpha,labels)
        self.parent=factory([{**task,'expected':TAXONOMY[task['expected']]['stage']} for task in tasks],groups)
        self.children={}
        for group in groups:
            labels=tuple(label for label in self.labels if TAXONOMY[label]['stage']==group)
            if len(labels)>1:self.children[group]=factory([task for task in tasks if task['expected'] in labels],labels)
        self.last_parent=None
    def scores(self,task):
        import numpy as np
        parent=self.parent.scores(task);order=np.argsort(parent)[::-1]
        group=self.parent.labels[int(order[0])]
        self.last_parent={'stage':group,'score':float(parent[order[0]]),'margin':float(parent[order[0]]-parent[order[1]])}
        result=np.full(len(self.labels),-10.,dtype=np.float32)
        child=self.children.get(group)
        if child:
            values=child.scores(task)
            for label,value in zip(child.labels,values):result[self.labels.index(label)]=value
        else:
            label=next(label for label in self.labels if TAXONOMY[label]['stage']==group)
            result[self.labels.index(label)]=parent[order[0]]
        return result

def evaluate_prediction(candidate,task,policy):
    start=time.perf_counter();scores=candidate.scores(task)
    ranked=sorted(zip(candidate.labels,(float(value) for value in scores)),key=lambda item:item[1],reverse=True)
    label,score=ranked[0];margin=score-ranked[1][1]
    accepted=score>=policy['minimum_score'] and margin>=policy['minimum_margin']
    hierarchy=getattr(candidate,'last_parent',None)
    if hierarchy:
        accepted=accepted and hierarchy['score']>=policy.get('minimum_parent_score',-100) and hierarchy['margin']>=policy.get('minimum_parent_margin',-100)
    # Classification is advisory even if confident. No mutation authorization.
    result=CapabilityPrediction(label,label if accepted else 'defer_to_planner',candidate.method,score,margin,
                                (time.perf_counter()-start)*1000,
                                reason='Offline candidate decision; score is not calibrated probability').to_dict()
    if hierarchy:result['hierarchy']=dict(hierarchy)
    return result

class ReleasedCpuClassifier:
    """Explicit opt-in replay of a reviewed artifact; never grants mutation."""
    def __init__(self,artifact):
        import json
        import hashlib
        from pathlib import Path
        self.manifest=json.loads(Path(artifact).read_text(encoding='utf-8'))
        if not self.manifest.get('release_ready'):
            raise ValueError('Classifier artifact has not passed its release gates')
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=self.manifest.get('module_sha256'):
            raise ValueError('Classifier module changed after evaluation')
        development=Path(artifact).parent/self.manifest['development_file']
        if hashlib.sha256(development.read_bytes()).hexdigest()!=self.manifest['development_sha256']:
            raise ValueError('Classifier development artifact changed after evaluation')
        data=json.loads(development.read_text(encoding='utf-8'))
        self.candidate=HierarchicalCandidate(data['training'],self.manifest['feature_mode'],self.manifest['ridge_alpha'])
        self.policy=self.manifest['policy']
    def predict(self,text,context=None):
        if not isinstance(text,str) or not text.strip():return ConservativeCapabilityClassifier().predict(text,context)
        context=context or {}
        result=evaluate_prediction(self.candidate,{'text':text,'context':context},self.policy)
        label=result['predicted'];allowed=label in self.manifest['accepted_labels']
        if label=='edit_code' and context.get('mode')!='chat':allowed=False
        if not allowed:result['decision']='defer_to_planner'
        result['production_enabled']=True
        result['mutation_authorized']=False
        result['reason']='Frozen CPU artifact; advisory classification never authorizes a mutation'
        return _PredictionView(result)

class _PredictionView:
    def __init__(self,value):self.value=value
    def to_dict(self):return dict(self.value)
    def __getattr__(self,key):return self.value[key]
