"""Streaming fixed-worker llama.cpp adapter for isolated kernel trials."""
import json
from pathlib import Path
import time
import httpx
import psutil


class LocalWorker:
    def __init__(self, model_path, endpoint='http://127.0.0.1:8087', on_token=None):
        self.model_path = str(Path(model_path).resolve())
        self.endpoint = endpoint
        self.on_token = on_token
        self.calls = []
        self.identity = self.check_identity()

    def check_identity(self):
        servers = [p for p in psutil.process_iter(['name','cmdline'])
                   if (p.info['name'] or '').lower() == 'llama-server.exe']
        if len(servers) != 1:
            raise RuntimeError(f'Expected exactly one heavy server; observed {len(servers)}')
        arguments = servers[0].info['cmdline'] or []
        model = next((arguments[i+1] for i,arg in enumerate(arguments[:-1]) if arg in ('-m','--model')),None)
        if model is None or str(Path(model).resolve()).casefold() != self.model_path.casefold():
            raise RuntimeError('Active model differs from fixed task worker')
        return {'pid':servers[0].pid,'path':self.model_path}

    def generate(self, messages, *, max_tokens, temperature, timeout_seconds=120):
        """Transport only: return plain output, with measured usage in last_usage."""
        tokens, seconds = max_tokens, timeout_seconds
        self.last_usage = None
        if self.check_identity() != self.identity:
            raise RuntimeError('Worker process changed during task')
        started = time.monotonic()
        raw = ''
        usage = None
        trace = {'messages':messages,'identity':self.identity,'raw':'','usage':None}
        self.calls.append(trace)
        payload = {'model':'sovereign-code','temperature':temperature,'max_tokens':tokens,'stream':True,
                   'stream_options':{'include_usage':True},'response_format':{'type':'json_object'},
                   'messages':messages}
        try:
            with httpx.Client(timeout=max(.1,seconds)) as client:
                with client.stream('POST',self.endpoint+'/v1/chat/completions',json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if time.monotonic()-started >= seconds:
                            raise TimeoutError('Task deadline during model generation')
                        if not line.startswith('data:'): continue
                        data = line[5:].strip()
                        if data == '[DONE]': break
                        chunk = json.loads(data)
                        if chunk.get('usage'): usage = chunk['usage']
                        for choice in chunk.get('choices',[]):
                            text = choice.get('delta',{}).get('content') or ''
                            if text:
                                if 'first_output_seconds' not in trace:
                                    trace['first_output_seconds'] = time.monotonic()-started
                                raw += text
                                trace['raw'] = raw
                                if self.on_token: self.on_token(text)
            if not usage or type(usage.get('completion_tokens')) is not int:
                raise RuntimeError('Runtime did not report output token usage')
            trace['usage'] = usage
            self.last_usage = usage
            return raw
        finally:
            trace['elapsed_seconds'] = time.monotonic()-started
