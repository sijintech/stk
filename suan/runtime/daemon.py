"""Launch/stop API and supervisor independently. Never kill user tasks on exit."""

from pathlib import Path
import os
import subprocess
import sys
import time

from .common import alive, load_config, read_json


def start(state_dir):
    config = load_config(state_dir)
    state = Path(config["state_dir"])
    for component, module in [("supervisor", "suan.runtime.supervisor"), ("api", "suan.runtime.server")]:
        if alive(read_json(state / (component + ".pid"))):
            continue
        env = os.environ.copy()
        root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        with open(state / (component + ".log"), "ab") as log:
            process = subprocess.Popen([sys.executable, "-m", module, "--state-dir", str(state)],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env,
                                       start_new_session=os.name != "nt",
                                       creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            info = read_json(state / (component + ".pid"))
            if alive(info):
                break
            if process.poll() is not None:
                raise RuntimeError(f"{component} failed to start; inspect {state / (component + '.log')}")
            time.sleep(0.1)
        else:
            raise RuntimeError(f"{component} startup timed out; inspect its log")
    return status(state)


def status(state_dir):
    config = load_config(state_dir)
    state = Path(config["state_dir"])
    api = read_json(state / "api.pid")
    return {"api_running": alive(api), "supervisor_running": alive(read_json(state / "supervisor.pid")),
            "url": f"http://127.0.0.1:{api['port'] if api and alive(api) else config['port']}"}


def stop(state_dir, supervisor=False):
    import psutil
    config = load_config(state_dir)
    state = Path(config["state_dir"])
    for component in (["api", "supervisor"] if supervisor else ["api"]):
        info = read_json(state / (component + ".pid"))
        if alive(info):
            process = psutil.Process(info["pid"])
            process.terminate()
            try:
                process.wait(timeout=25)
            except psutil.TimeoutExpired as exc:
                raise RuntimeError(f"{component} is still shutting down") from exc
    return status(state)
