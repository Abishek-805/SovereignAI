"""Reproduce fixture-owned sources; no model or production code input."""
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = [
    ('cards', 'Restore the card layout, spacing and accent colors shown in the attached screenshot.',
     '<h1>Field notes</h1><div id="cards"><article id="a"><b>River survey</b><p>12 samples collected</p></article><article id="b"><b>Forest census</b><p>8 plots mapped</p></article><article id="c"><b>Coastal watch</b><p>4 stations online</p></article></div>',
     '#cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}article{padding:24px;background:white;border-top:6px solid #16836d;border-radius:8px}#b{border-color:#d39129}#c{border-color:#596cbe}',
     '#cards{display:block}article{padding:6px;background:white;border-top:1px solid gray;margin:4px}'),
    ('navigation', 'Fix the navigation alignment and selected tab styling to match the attached screenshot.',
     '<nav id="nav"><strong id="brand">Orbit library</strong><div id="tabs"><button id="books">Books</button><button id="active" aria-current="page">Collections</button><button id="saved">Saved</button></div></nav><h1>Your collections</h1><p>Arrange the books that matter to you.</p>',
     '#nav{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #cbd5e1;padding-bottom:20px}#tabs{display:flex;gap:12px}button{padding:12px 18px;border:0;background:transparent;border-radius:6px}#active{background:#173e66;color:white}',
     '#nav{display:block}#tabs{display:block}button{padding:3px;border:1px solid gray;background:white}#active{color:#111}'),
    ('form', 'Repair the form field arrangement and submit button shown in the reference screenshot. Keep labels associated with inputs.',
     '<h1>Reserve a desk</h1><form id="form"><label id="name-label" for="name">Full name<input id="name" value="Mira Shah"></label><label id="email-label" for="email">Email<input id="email" value="mira@example.test"></label><label id="date-label" for="date">Date<input id="date" type="date" value="2026-10-05"></label><label id="guests-label" for="guests">Guests<input id="guests" type="number" value="2"></label><button id="submit" type="submit">Confirm reservation</button></form>',
     '#form{display:grid;grid-template-columns:1fr 1fr;gap:20px;width:640px}label{display:flex;flex-direction:column;gap:8px;font-weight:bold}input{padding:12px;border:1px solid #9aaec0;border-radius:6px;font:inherit}#submit{grid-column:1/-1;padding:14px;background:#173e66;color:white;border:0;border-radius:6px;font:inherit}',
     '#form{display:block;width:320px}label{display:block}input{width:120px}#submit{padding:2px;background:white}'),
    ('table', 'Fix the shipment table column sizing, row spacing and delivered status badges to match the attached screenshot.',
     '<h1>Recent shipments</h1><table id="table"><thead><tr><th id="order">Order</th><th id="destination">Destination</th><th id="status">Status</th></tr></thead><tbody><tr id="row1"><td>PK-1042</td><td>Jaipur</td><td><span id="badge1">Delivered</span></td></tr><tr id="row2"><td>PK-1043</td><td>Kochi</td><td><span id="badge2">Delivered</span></td></tr></tbody></table>',
     'table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:20px;border-bottom:1px solid #d8e1e8}th{background:#173e66;color:white}th:first-child{width:30%}th:nth-child(2){width:40%}span{display:inline-block;padding:6px 12px;border-radius:20px;background:#d8f1e5;color:#176044}',
     'table{width:240px;border-collapse:collapse}th,td{padding:2px;text-align:center}span{background:#f2dddd;color:#a22}'),
    ('empty-state', 'Match the attached empty state screenshot by correcting the panel width, centered content, icon circle and action button.',
     '<section id="panel"><div id="icon" aria-hidden="true">+</div><h1 id="title">No notebooks yet</h1><p id="description">Capture your first idea in a fresh notebook.</p><button id="create">Create notebook</button></section>',
     '#panel{width:560px;margin:36px auto;background:white;padding:40px;text-align:center;border:1px solid #cad6df;border-radius:12px}#icon{width:64px;height:64px;line-height:64px;margin:auto;border-radius:50%;background:#dbe9f7;color:#173e66;font-size:40px}#create{padding:14px 24px;background:#173e66;color:white;border:0;border-radius:6px;font:inherit}',
     '#panel{width:280px;background:white;padding:8px;text-align:left}#icon{font-size:16px}#create{background:white;padding:2px}'),
]
BASE = 'html{box-sizing:border-box}*,*:before,*:after{box-sizing:inherit}body{margin:0;padding:48px;background:#eef3f7;color:#203344;font:16px Arial,sans-serif}h1{font-size:28px;margin:0 0 28px}p{line-height:1.5}'
def page(body, css):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>UI repair fixture</title><style>'+BASE+css+'</style></head><body>'+body+'</body></html>'

cases=[]
for name, request, body, good, bad in CASES:
    folder=ROOT/name
    folder.mkdir(parents=True,exist_ok=True)
    original=page(body,bad)
    (folder/'original.html').write_text(original,encoding='utf-8')
    (folder/'reference.html').write_text(page(body,good),encoding='utf-8')
    cases.append({'id':'vision-code-'+name,'category':'vision_code','request':request+' Return the complete corrected index.html. Preserve the existing content and element IDs.','history':[],'documents':False,'workspace':True,'image':True,'image_path':name+'/target.png','project_files':[{'name':'index.html','content':original}], 'expected':{'intent':['CODE','code_generation'],'workflow':['CODE','code_generation'],'worker':['vision','code'],'stage_order':['vision','code'],'tools':None,'achieved':None},'oracle':{'kind':'browser_geometry','reference':name+'/reference-metrics.json','validator':'validate.mjs','original':name+'/original.html'}})
for case in cases:
    original=case.pop('project_files')[0]['content']
    image_path=case.pop('image_path')
    case['category']='vision'
    case['context']={'active_file':'index.html','initial_files':{'index.html':original},'image_path':image_path}
    case['modality']='image'
    case['sandbox_required']=True
    case['context'].update(workspace_available=True,repository_scope='file')
    if (ROOT/image_path).exists():case['context']['image_sha256']=hashlib.sha256((ROOT/image_path).read_bytes()).hexdigest()
    case['allowed_change_paths']=['index.html']
    case['expected_task_type']='VISION_ASSISTED_CODE'
    case['complexity']='simple'
    case['expected_suitable_workers']=['code']
    case['execution_supported']=True
    case['stage_order']=['vision','code']
    name=case['id'].removeprefix('vision-code-')
    checks={'cards':['display:grid','grid-template-columns:repeat(3,1fr)','gap:20px'], 'navigation':['display:flex','justify-content:space-between','background:#173e66'], 'form':['display:grid','grid-template-columns:1fr 1fr','grid-column:1/-1'], 'table':['width:100%','text-align:left','background:#d8f1e5'], 'empty-state':['width:560px','text-align:center','border-radius:50%']}[name]
    # Narrow trusted checks prove content/structure preservation and required CSS declarations.
    # They do not claim pixel fidelity; browser oracle and semantic review remain required.
    verifier='''from html.parser import HTMLParser
from pathlib import Path
import re
class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.elements=[]; self.text=[]; self.labels=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.elements.append((tag,a['id']))
        if tag=='label':self.labels.append(a.get('for'))
    def handle_data(self,data):
        if data.strip():self.text.append(data.strip())
p=Parser(); source=Path('index.html').read_text(encoding='utf-8'); p.feed(source)
EXPECTED_ELEMENTS = '''+repr(__import__('re').findall(r'<(\w+)[^>]* id="([^"]+)"',original))+'''
assert p.elements==EXPECTED_ELEMENTS, 'preserve original element IDs and tags'
ids={value for tag,value in p.elements}
assert all(value in ids for value in p.labels), 'labels must reference inputs'
css=re.sub(r'\\s+','',source.lower())
for declaration in '''+repr(checks)+''':
    assert re.sub(r'\\s+', '', declaration) in css, 'missing required layout/style declaration: '+declaration
print('PASS narrow structure/style assertions; visual review still required')
'''
    case['oracle']={'kind':'trusted_tests','trusted_files':{'verify.py':verifier},'command':['python','verify.py'],'expected_exit_code':0,'semantic_review_required':True}
    case['visual_oracle']={'validator':'validate.mjs','reference':name+'/reference-metrics.json','original':name+'/original.html','scope':'supplemental browser geometry/style; not Docker pass evidence'}
payload={'version':1,'kind':'independently_authored_supplemental_vision_code','independent_held_out':False,'sources':[],'cases':cases}
raw=json.dumps(payload,indent=2)+'\n'
(ROOT/'fixtures.json').write_text(raw,encoding='utf-8')
canonical=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
provenance={'author':'independent vision fixture agent','created':'2026-10-02','inputs_read':['benchmarks/universal-agent-fixtures.json (schema only)','benchmarks/smart-code-router/main.json (schema only)'],'production_inspected':False,'heldout_inspected':False,'models_used':False,'docker_used':False,'independent_held_out':False,'datasets':[{'file':'fixtures.json','canonical_sha256':hashlib.sha256(canonical).hexdigest(),'file_sha256':hashlib.sha256((ROOT/'fixtures.json').read_bytes()).hexdigest(),'case_count':len(cases)}]}
(ROOT/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
