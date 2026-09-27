"""Observe SovereignAI process sockets during a bounded local demo.

This is diagnostic evidence, not an OS-enforced egress block: polling can miss
brief connections and cannot prove that a connection was never attempted.
"""
import argparse
import json
import time
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]


def _target_processes():
    results=[]
    expected_model=str(ROOT / 'runtime' / 'llama-b11132' / 'llama-server.exe').lower()
    expected_python=str(ROOT / '.app-venv' / 'Scripts' / 'python.exe').lower()
    for name in ('server.pid','workbench.pid'):
        record=ROOT/'benchmarks'/name
        if not record.is_file():
            continue
        try:
            process=psutil.Process(int(record.read_text().strip()))
            exe=str(process.exe() or '').lower()
            command=' '.join(process.cmdline())
            if exe==expected_model or (exe==expected_python and 'backend.app:create_app' in command):
                results.append(process)
                if exe==expected_python:
                    results.extend(process.children(recursive=False))
        except (ValueError,OSError,psutil.NoSuchProcess,psutil.AccessDenied):
            continue
    return results


def _external(address):
    host=address.ip if hasattr(address,'ip') else address[0]
    return host not in {'127.0.0.1','::1','0.0.0.0','::',''}


def monitor(seconds,interval):
    started=time.time()
    observed=[]
    samples=0
    pids=set()
    while time.time()-started<seconds:
        samples+=1
        for process in _target_processes():
            pids.add(process.pid)
            try:
                connections=process.net_connections(kind='inet')
            except (psutil.NoSuchProcess,psutil.AccessDenied):
                continue
            for connection in connections:
                if connection.raddr and _external(connection.raddr):
                    observed.append({'at':time.time(),'pid':process.pid,'status':connection.status,
                                     'remote':f'{connection.raddr.ip}:{connection.raddr.port}'})
        time.sleep(interval)
    return {'started_at':started,'finished_at':time.time(),'sample_count':samples,
            'target_pids':sorted(pids),'observed_external_sockets':observed,
            'limitation':'Polling does not detect every short-lived connection or blocked attempt; use OS-enforced egress blocking for the air-gap release gate.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=float,default=30)
    parser.add_argument('--interval',type=float,default=.2)
    parser.add_argument('--output',type=Path,default=ROOT/'benchmarks'/'network-monitor.json')
    args=parser.parse_args()
    if not 1<=args.seconds<=3600 or not .05<=args.interval<=5:
        parser.error('Use 1–3600 seconds and 0.05–5 second polling intervals')
    record=monitor(args.seconds,args.interval)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(f"Observed {len(record['observed_external_sockets'])} external sockets across {record['sample_count']} samples; see {args.output}")


if __name__=='__main__':
    main()
