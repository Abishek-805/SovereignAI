"""Additional live denial/resource probes using only ephemeral project snapshots."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from router.sandbox import CodeSandbox
image=json.loads((Path(__file__).resolve().parents[1]/'data/sandbox-validation.json').read_text())['image_id']
with tempfile.TemporaryDirectory(prefix='sovereign-isolation-extra-') as folder:
    sandbox=CodeSandbox('docker',image_id=image,task_root=Path(folder))
    first=sandbox.execute("from pathlib import Path\nassert Path('/input/project-a.txt').read_text()=='A'\nPath('/output/private-a.txt').write_text('A')",input_files={'project-a.txt':b'A'})
    second=sandbox.execute("from pathlib import Path\nassert Path('/input/project-b.txt').read_text()=='B'\nassert not Path('/input/project-a.txt').exists()\nassert not Path('/output/private-a.txt').exists()",input_files={'project-b.txt':b'B'})
    memory=sandbox.execute("data=bytearray(600*1024*1024)\nprint('allocation unexpectedly succeeded')")
    pids=sandbox.execute("import subprocess\nchildren=[]\ntry:\n try:\n  for i in range(100): children.append(subprocess.Popen(['sleep','30']))\n except OSError:\n  print('bounded')\n else:\n  raise RuntimeError('100 child processes unexpectedly succeeded')\nfinally:\n for child in children:child.terminate()\n for child in children:child.wait()")
    output=sandbox.execute("from pathlib import Path\ntry:\n for i in range(64):Path('/output/fill-'+str(i)+'.bin').write_bytes(b'x'*(8*1024*1024))\nexcept OSError as e:\n assert e.errno==28\n print('bounded')\nelse:\n raise RuntimeError('512 MiB output unexpectedly succeeded')")
    checks={'cross_project_inputs_and_outputs':first.executed and second.executed and first.exit_code==second.exit_code==0,
        'memory_allocation_denied':memory.executed and memory.exit_code!=0,
        'process_creation_denied':pids.executed and pids.exit_code==0 and 'bounded' in pids.stdout,
        'output_fill_denied':output.executed and output.exit_code==0 and 'bounded' in output.stdout}
    print(json.dumps({'checks':checks,'exit_codes':{'memory':memory.exit_code,'pids':pids.exit_code,'output':output.exit_code}},indent=2))
    if not all(checks.values()):raise SystemExit(1)
