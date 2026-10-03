"""Five independently authored actual PNG UI references; no borrowed V1 assets."""
import hashlib
from PIL import Image, ImageDraw

def author_vision(root,start):
    cases=[]
    themes=[('progress','Upload progress','68% complete','#176b87','68%'),('notice','Maintenance notice','Returns at 18:00','#855623','Scheduled'),('profile','Research profile','Lena Rao','#6355a4','Available'),('ticket','Support ticket','T-302 awaiting reply','#a34368','Waiting'),('meter','Energy meter','42 kWh today','#28754b','42 kWh')]
    for j,(name,title,subtitle,color,label) in enumerate(themes):
        folder=root/'vision'/name;folder.mkdir(parents=True,exist_ok=True)
        css=f'body{{margin:0;background:#eef2f5;font:20px Arial}}#panel{{position:absolute;left:40px;top:40px;width:480px;padding:24px;background:white;border-left:8px solid {color}}}h1{{font-size:28px}}#badge{{display:inline-block;background:{color};color:white;padding:10px 18px;border-radius:8px}}'
        body=f'<section id="panel"><h1>{title}</h1><p>{subtitle}</p><span id="badge">{label}</span></section>'
        reference=f'<!doctype html><html><head><style>{css}</style></head><body>{body}</body></html>'
        original=f'<!doctype html><html><head><style>body{{font:20px Arial}}#panel{{width:160px}}#badge{{color:white;background:white}}</style></head><body>{body}</body></html>'
        (folder/'reference.html').write_text(reference,encoding='utf-8');(folder/'original.html').write_text(original,encoding='utf-8')
        image=Image.new('RGB',(640,300),'#eef2f5');draw=ImageDraw.Draw(image)
        draw.rectangle((40,40,568,256),fill='white');draw.rectangle((40,40,48,256),fill=color)
        draw.text((72,68),title,fill='#172635',font_size=28);draw.text((72,118),subtitle,fill='#172635',font_size=20)
        draw.rounded_rectangle((72,168,260,214),radius=8,fill=color);draw.text((90,180),label,fill='white',font_size=20)
        image.save(folder/'target.png')
        checks=['width:480px','padding:24px',f'border-left:8px solid {color}',f'background:{color}','color:white','border-radius:8px']
        verifier=f'''from pathlib import Path
from html.parser import HTMLParser
import re
s=Path('index.html').read_text(encoding='utf-8')
class P(HTMLParser):
 def __init__(self): super().__init__(); self.ids=[];self.text=[]
 def handle_starttag(self,t,a):
  d=dict(a)
  if 'id' in d:self.ids.append(d['id'])
 def handle_data(self,d):self.text.append(d)
p=P();p.feed(s)
assert p.ids==['panel','badge']
for text in {[title,subtitle,label]!r}: assert text in ''.join(p.text)
compact=re.sub(r'\\s+','',s.lower())
for expected in {checks!r}:assert re.sub(r'\\s+','',expected) in compact
'''
        cases.append({'id':f'v2-main-{start+j:03d}','contract_id':'visual-'+name,'category':'vision','request':'Fix index.html to match the supplied reference image. Preserve its labels and IDs. Use a 480px panel with 24px padding, an 8px left accent border, and a visible rounded badge. Return complete corrected source.','expected_task_type':'VISION_ASSISTED_CODE','expected_suitable_workers':['vision','code'],'stage_order':['vision','code'],'complexity':'simple','modality':'image','context':{'active_file':'index.html','workspace_available':True,'repository_scope':'file','initial_files':{'index.html':original},'image_path':f'vision/{name}/target.png','image_sha256':hashlib.sha256((folder/'target.png').read_bytes()).hexdigest()},'allowed_change_paths':['index.html'],'sandbox_required':True,'execution_supported':True,'oracle':{'kind':'trusted_tests','language':'html','trusted_files':{'test_visual_structure.py':verifier},'command':['python','test_visual_structure.py'],'expected_exit_code':0,'test_mount':'outside_editable_workspace','success_endpoint':'READY_FOR_REVIEW','semantic_review_required':True,'limitation':'Actual PNG is an authored interface reference, not a browser screenshot. Structural/style assertions do not prove pixel fidelity; independent visual review is mandatory.'},'properties':{'typo':False,'followup':False,'ambiguous':False,'repair':True}})
    return cases
