"""Schedule bounded upstream worker passes and forward container shutdown."""
import os
import signal
import subprocess
import sys
import threading

stop = threading.Event()
child = None


def shutdown(signum, frame):
    stop.set()
    if child is not None and child.poll() is None:
        child.send_signal(signum)


for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, shutdown)

interval = float(os.environ.get("WORKER_INTERVAL_SECONDS", "30"))
if not 5 <= interval <= 3600:
    raise SystemExit("WORKER_INTERVAL_SECONDS must be between 5 and 3600")

while not stop.is_set():
    child = subprocess.Popen([
        sys.executable, "-m", "scope_recall.runtime.worker_entry",
        "--config", "/config/shared-runtime.json",
        "--env-file", "/config/model.env",
    ])
    code = child.wait()
    child = None
    if code:
        print(f"worker pass exited with status {code}", flush=True)
    stop.wait(interval)
