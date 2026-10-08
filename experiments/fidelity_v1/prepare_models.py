"""Verify existing local model artifacts and source metadata; download no model."""
import hashlib,json,urllib.request
from dataclasses import asdict
from experiments.fidelity_v1.tasks import ROOT,OUT
from experiments.fidelity_v1.evaluate import model_definitions,save
def main():
 output=OUT/'reports/model-source-review.json'
 if output.exists():raise RuntimeError('Model review already frozen')
 old=json.loads((ROOT/'benchmarks/model-comparison/install-manifest.json').read_text())
 expected={m['path']:m['expected_sha256'] for m in old['models']}
 rows=[]
 for name,spec in model_definitions().items():
  path=ROOT/'models'/spec.model_file;hasher=hashlib.sha256()
  with path.open('rb') as file:
   for block in iter(lambda:file.read(8*1024*1024),b''):hasher.update(block)
  sha=hasher.hexdigest();known=expected.get(path.relative_to(ROOT).as_posix())
  if known and known!=sha:raise RuntimeError('Installed model hash mismatch: '+name)
  url=spec.license_source;repo=url.removeprefix('https://huggingface.co/')
  metadata=json.load(urllib.request.urlopen('https://huggingface.co/api/models/'+repo,timeout=30))
  save(OUT/'reports'/('model-card-'+name+'.json'),metadata)
  rows.append({'name':name,'spec':asdict(spec),'sha256':sha,'bytes':path.stat().st_size,'matched_prior_download_verification':bool(known),'source':url,'source_license':metadata.get('cardData',{}).get('license'),'source_revision':metadata.get('sha')})
  print('Verified existing artifact '+name,flush=True)
 manifest={'models':rows,'model_downloads':0,'production_registry_changes':0,'model_stage_scaffold':'native_v1 frozen snapshot','same_context':16384,'same_output_limit':4096,'only_artifact_model_changes':True,'quantization_limit':'mini-coder uses its existing IQ4_NL artifact; the other candidates use existing Q4_K_M artifacts. This is a practical artifact comparison, not a pure model-size experiment.'}
 save(output,manifest)
if __name__=='__main__':main()
