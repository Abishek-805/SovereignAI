"""Run required negative probes before enabling generated-code execution."""
import argparse
import json
import os
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from router.sandbox import (CodeSandbox, LOCAL_ENGINE, MAX_OUTPUT_VOLUME_BYTES,
                            SANDBOX_VERIFICATION_VERSION, sandbox_policy_fingerprint)
from backend.settings import Settings


def verify(image_id: str):
    with TemporaryDirectory(prefix='sovereign-sandbox-check-') as directory:
        sandbox = CodeSandbox('docker', image_id=image_id, task_root=Path(directory))
        normal = sandbox.execute("from pathlib import Path\nPath('/output/result.csv').write_text('total\\n3\\n')\nprint('ok')")
        network = sandbox.execute("import socket\nsocket.create_connection(('1.1.1.1', 80), 2)")
        root_write = sandbox.execute("from pathlib import Path\nPath('/blocked.txt').write_text('bad')")
        input_write = sandbox.execute("from pathlib import Path\nPath('/input/data.csv').write_text('bad')", input_files={'data.csv': b'original'})
        user = sandbox.execute("import os\nprint(os.getuid())")
        inspection = sandbox.execute("""import json,os,pathlib
def read(path):
    p=pathlib.Path(path)
    return p.read_text().strip() if p.is_file() else ''
status=read('/proc/self/status')
print(json.dumps({'cap_eff':next((x.split(':',1)[1].strip() for x in status.splitlines() if x.startswith('CapEff:')),''),
 'no_new_privs':next((x.split(':',1)[1].strip() for x in status.splitlines() if x.startswith('NoNewPrivs:')),''),
 'pids':read('/sys/fs/cgroup/pids.max'),'memory':read('/sys/fs/cgroup/memory.max'),
 'swap':read('/sys/fs/cgroup/memory.swap.max'),
 'cpu':read('/sys/fs/cgroup/cpu.max'),'pid1':read('/proc/1/cmdline'),
 'output_capacity':os.statvfs('/output').f_blocks*os.statvfs('/output').f_frsize,
 'docker_socket':any(pathlib.Path(p).exists() for p in ('/var/run/docker.sock','/run/docker.sock'))}))""")
        try: details=json.loads(inspection.stdout)
        except ValueError: details={}
        old=os.environ.get('SOVEREIGN_SANDBOX_DUMMY_SECRET')
        os.environ['SOVEREIGN_SANDBOX_DUMMY_SECRET']='dummy-test-only'
        try:
            environment=sandbox.execute("import os\nprint(os.getenv('SOVEREIGN_SANDBOX_DUMMY_SECRET','absent'))")
        finally:
            if old is None: os.environ.pop('SOVEREIGN_SANDBOX_DUMMY_SECRET',None)
            else: os.environ['SOVEREIGN_SANDBOX_DUMMY_SECRET']=old
        secrets=sandbox.execute("from pathlib import Path\nprint(Path('/input/.env').exists())",input_files={'.env':b'DUMMY_TOKEN=not-real'})
        timed=sandbox.execute('import time\ntime.sleep(8)',timeout=1)
        cancelled=CodeSandbox('docker',image_id=image_id,task_root=Path(directory))
        cancelled.cancel_event=threading.Event()
        timer=threading.Timer(1.0,cancelled.cancel_event.set);timer.start()
        try: stopped=cancelled.execute('import time\ntime.sleep(8)',timeout=10)
        finally: timer.cancel()
        import subprocess
        remaining=subprocess.run([*sandbox.docker,'ps','-a','--filter','name=sovereign-code-','--format','{{.Names}}'],
                                 capture_output=True,text=True,timeout=8,check=True).stdout.strip()
        checks = {
            'normal_execution': normal.executed and normal.exit_code == 0 and normal.output_files.get('result.csv') == b'total\n3\n',
            'network_blocked': network.executed and network.exit_code != 0,
            'root_read_only': root_write.executed and root_write.exit_code != 0,
            'input_read_only': input_write.executed and input_write.exit_code != 0,
            'non_root': user.executed and user.exit_code == 0 and user.stdout.strip() == '65534',
            'capabilities_dropped': inspection.exit_code==0 and details.get('cap_eff')=='0000000000000000',
            'no_new_privileges': inspection.exit_code==0 and details.get('no_new_privs')=='1',
            'process_isolated': 'sleep' in details.get('pid1',''),
            'pids_bounded': details.get('pids')=='64',
            'memory_bounded': details.get('memory')==str(512*1024*1024) and details.get('swap')=='0',
            'cpu_bounded': details.get('cpu','').split()[:2] in (['100000','100000'],['1000000','1000000']),
            'output_bounded': 0 < details.get('output_capacity',0) <= MAX_OUTPUT_VOLUME_BYTES,
            'docker_socket_absent': details.get('docker_socket') is False,
            'host_env_excluded': environment.exit_code==0 and environment.stdout.strip()=='absent',
            'project_secret_excluded': secrets.exit_code==0 and secrets.stdout.strip()=='False',
            'timeout_stops': timed.exit_code==-1,
            'cancel_stops': stopped.exit_code==-1,
            'containers_cleaned': not remaining,
        }
        return checks


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('image_id', help='Local pinned sha256 image ID from docker image inspect')
    args = parser.parse_args()
    results = verify(args.image_id)
    print(json.dumps(results, indent=2))
    if all(results.values()):
        path = Settings().data_dir / 'sandbox-validation.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'image_id':args.image_id,
                                         'verification_version':SANDBOX_VERIFICATION_VERSION,
                                         'policy_fingerprint':sandbox_policy_fingerprint(),
                                         'checks':results,
                                         'validated_at':time.time()},indent=2),encoding='utf-8')
        os.replace(temporary,path)
    raise SystemExit(0 if all(results.values()) else 1)
