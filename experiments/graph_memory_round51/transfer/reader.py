"""Start an owned loopback llama.cpp reader and close it after completing sealed inference."""
import importlib.util
import sys
import socket
import subprocess
import time

import requests

from study import D, P, SERVER, MODEL, shared, check


def main():
    check()
    spec = importlib.util.spec_from_file_location("runtime", D/"runtime.py")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    sys.modules["runtime"] = runtime
    port = 18896
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    args = [str(SERVER), "-m", str(MODEL), "--host", "127.0.0.1", "--port", str(port),
            "--parallel", "1", "--ctx-size", "1024", "--n-gpu-layers", "all",
            "--flash-attn", "on", "--threads", "4", "--no-warmup"]
    with (P/"server.stderr").open("wb") as log, requests.Session() as session:
        session.trust_env = False
        proc = subprocess.Popen(args, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            (P/"qa.pid").write_text(str(proc.pid), encoding="ascii")
            for _ in range(150):
                if proc.poll() is not None:
                    raise RuntimeError("Reader exited during startup")
                try:
                    if session.get(f"http://127.0.0.1:{port}/health",timeout=1).ok: break
                except requests.RequestException:
                    pass
                time.sleep(.4)
            else:
                raise RuntimeError("Reader did not start")
            shared("inputs_sem").main()
            shared("reader_tokens").main()
            shared("hardware_receipt").main()
            shared("generate").main()
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=30)


if __name__ == "__main__":
    main()
