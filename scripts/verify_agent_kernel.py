"""Real native multi-turn tools, staged draft and independent Docker oracle."""
import json
import os
from pathlib import Path
import urllib.request
from backend.model import LocalModel
from workflows.coding_workspace import CodingWorkspace
from workflows.agent_kernel import AgentLoop
from experiments.kernel_docker import DockerCommands

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/agent-kernel-rebuild';OUT.mkdir(parents=True,exist_ok=True)

def main():
    request=urllib.request.Request('http://127.0.0.1:8088/workbench/model/load',data=b'{"capability":"text"}',headers={'Content-Type':'application/json'})
    loaded=json.load(urllib.request.urlopen(request,timeout=120))
    (OUT/'runtime-load.json').write_text(json.dumps(loaded,indent=2))
    model=LocalModel();props=model._request_raw('GET','/props')
    (OUT/'runtime-template.json').write_text(json.dumps({'chat_template':props.get('chat_template'),'chat_template_caps':props.get('chat_template_caps')},indent=2))
    workspace=CodingWorkspace(OUT/'smoke-workspaces')
    wid=workspace.create('Native tools smoke')['workspace_id']
    workspace.write(wid,'input.txt','42\n')
    workspace.write(wid,'test_acceptance.py','import unittest,subprocess,sys\nclass Check(unittest.TestCase):\n def test_output(self):\n  result=subprocess.run([sys.executable,"main.py"],capture_output=True,text=True)\n  self.assertEqual(result.returncode,0)\n  self.assertEqual(result.stdout.strip(),"42")\n')
    sandbox=DockerCommands(ROOT,OUT/'sandbox').sandbox
    result=AgentLoop().run(workspace,wid,'Read input.txt, write main.py that reads and prints its contents, run python main.py, then finish. Preserve test_acceptance.py.',model,sandbox,'sovereign-text',progress=lambda s:print(s,flush=True))
    (OUT/'native-smoke.json').write_text(json.dumps(result,indent=2))
    assert result['state']=='completed',result.get('error')
    tools={event['tool'] for event in result['events']}
    assert {'read_file','write_file','run_command','finish'}<=tools,tools
    assert not (workspace.files_directory(wid)/'main.py').exists(),'Must remain staged'
    workspace.accept(wid,result['task_id'])
    assert workspace.read(wid,'main.py')['content']
    print('Native read/write/run multi-turn use, independent validation and acceptance PASS')

if __name__=='__main__':main()
