"""Exercise local document QA while rejecting non-loopback Python sockets."""
from __future__ import annotations

import json
import socket
import sys
from ipaddress import ip_address

from backend.service import Workbench


def run(document_id: str, question: str) -> dict:
    original = socket.socket.connect
    rejected = []

    def local_only(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            host = address[0]
            try:
                allowed = ip_address(host).is_loopback
            except ValueError:
                allowed = host == 'localhost'
            if not allowed:
                rejected.append(host)
                raise RuntimeError(f'Non-loopback socket blocked: {host}')
        return original(sock, address)

    socket.socket.connect = local_only
    try:
        result = Workbench().ask(question, [document_id])
        return {'status': result['status'], 'answer': result['answer'],
                'sources': len(result['sources']), 'blocked_attempts': rejected}
    finally:
        socket.socket.connect = original


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python -m scripts.loopback_smoke DOCUMENT_ID QUESTION')
    print(json.dumps(run(sys.argv[1], sys.argv[2]), ensure_ascii=False))
