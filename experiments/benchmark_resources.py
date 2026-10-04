"""Passive resource observations; does not alter worker/context/budgets."""
import threading
import time
import subprocess
import psutil

class ResourceSamples:
    def __init__(self, pid):
        self.pid = pid
        self.samples = []
        self.stop = threading.Event()
    def sample(self):
        row = {'unix_time':time.time(), 'system_used_ram_bytes':psutil.virtual_memory().used}
        try:
            row['worker_rss_bytes'] = psutil.Process(self.pid).memory_info().rss
        except psutil.Error as error:
            row['process_error'] = str(error)
        try:
            raw = subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.total',
                '--format=csv,noheader,nounits'], text=True, timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW)
            row['gpu_used_mib'] = int(raw.split(',')[0].strip())
        except Exception as error:
            row['gpu_error'] = type(error).__name__
        self.samples.append(row)
    def loop(self):
        while not self.stop.is_set():
            self.sample()
            self.stop.wait(2)
    def __enter__(self):
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self
    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(4)
        self.sample()
    def result(self):
        return {'samples':self.samples, 'sampling_interval_seconds':2,
                'worker_peak_rss_bytes':max((s.get('worker_rss_bytes',0) for s in self.samples),default=None),
                'gpu_peak_used_mib':max((s['gpu_used_mib'] for s in self.samples if 'gpu_used_mib' in s),default=None),
                'gpu_is_device_total_not_process_allocation':True}
