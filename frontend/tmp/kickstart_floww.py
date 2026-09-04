#!/usr/bin/env python3
"""Kickstart script: start backend uvicorn + static proxy, verify health."""
from __future__ import annotations
import subprocess, time, sys, os, signal

PROJ = "/Users/nav/Documents/GitHub/floww"
PROXY_SCRIPT = "/Users/nav/.hermes/scripts/static_proxy.py"
BACKEND_PORT = 8000
PROXY_PORT = 3000

def kill_existing():
    for pat in ["uvicorn server:app", "static_proxy.py"]:
        subprocess.run(["pkill", "-f", pat], capture_output=True)
    time.sleep(2)

def start_backend():
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app",
         "--host", "127.0.0.1", "--port", str(BACKEND_PORT), "--workers", "1"],
        cwd=PROJ, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    print(f"backend PID: {proc.pid}")
    return proc

def start_proxy():
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    build_dir = os.path.join(PROJ, "frontend", "build")
    proc = subprocess.Popen(
        [sys.executable, PROXY_SCRIPT, "--build", build_dir, "--port", str(PROXY_PORT)],
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    print(f"proxy PID: {proc.pid}")
    return proc

def wait_health(url, label, timeout=30):
    import urllib.request, urllib.error
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                body = r.read().decode()[:200]
                print(f"{label} ({url}): {r.status} — {body}")
                return True
        except Exception as e:
            sys.stderr.write(f"  {label} not ready: {e}\n")
            time.sleep(2)
    print(f"{label} FAILED after {timeout}s")
    return False

def main():
    kill_existing()
    backend = start_backend()
    proxy = start_proxy()
    time.sleep(3)

    ok = True
    ok &= wait_health("http://127.0.0.1:8000/api/health", "backend")
    ok &= wait_health("http://localhost:3000/api/health", "proxy")

    if ok:
        print("\n=== ALL SYSTEMS GO ===")
        print(f"backend: http://localhost:{BACKEND_PORT}")
        print(f"proxy:   http://localhost:{PROXY_PORT}")
        print("floww is live. Ctrl-C to stop both.")
        try:
            backend.wait()
        except KeyboardInterrupt:
            proxy.terminate()
            backend.terminate()
    else:
        print("\n=== STARTUP FAILED — check logs ===")
        print("backend log:")
        for line in backend.stdout:
            print("  ", line.rstrip())
        sys.exit(1)

if __name__ == "__main__":
    main()
