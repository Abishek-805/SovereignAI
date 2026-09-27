"""Run required negative probes before enabling generated-code execution."""
import argparse
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from router.sandbox import CodeSandbox
from backend.settings import Settings


def verify(image_id: str):
    with TemporaryDirectory(prefix='sovereign-sandbox-check-') as directory:
        sandbox = CodeSandbox('docker', image_id=image_id, task_root=Path(directory))
        normal = sandbox.execute("from pathlib import Path\nPath('/output/result.csv').write_text('total\\n3\\n')\nprint('ok')")
        network = sandbox.execute("import socket\nsocket.create_connection(('1.1.1.1', 80), 2)")
        root_write = sandbox.execute("from pathlib import Path\nPath('/blocked.txt').write_text('bad')")
        input_write = sandbox.execute("from pathlib import Path\nPath('/input/data.csv').write_text('bad')", input_files={'data.csv': b'original'})
        user = sandbox.execute("import os\nprint(os.getuid())")
        checks = {
            'normal_execution': normal.executed and normal.exit_code == 0 and normal.output_files.get('result.csv') == b'total\n3\n',
            'network_blocked': network.executed and network.exit_code != 0,
            'root_read_only': root_write.executed and root_write.exit_code != 0,
            'input_read_only': input_write.executed and input_write.exit_code != 0,
            'non_root': user.executed and user.exit_code == 0 and user.stdout.strip() == '65534',
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
        temporary.write_text(json.dumps({'image_id':args.image_id,'checks':results,
                                         'validated_at':time.time()},indent=2),encoding='utf-8')
        os.replace(temporary,path)
    raise SystemExit(0 if all(results.values()) else 1)
