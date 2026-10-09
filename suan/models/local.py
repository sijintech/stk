"""One-click local models (docs/design/model-gateway.md, S1c).

Probe this computer, recommend a catalog entry that fits, install the llama.cpp runtime and the weights (resumable downloads;
every file and the runtime archive are checked against the catalog's size and SHA-256 before they get their final name), start an
OpenAI-compatible server on 127.0.0.1 and register it as a local endpoint ``local-<entry>``. Everything lives in the service's
private state folder (``models/local``). Installing, importing, starting, stopping and removing are explicit actions of the person
at this computer; scripts can only read.

The catalog ships with STK (``catalog.json``); ``STK_MODEL_CATALOG`` points to another one (tests, on-prem deliveries with an
internal mirror). Entries without a size and SHA-256 for every file are refused. Downloads from the internet need the network
setting ``internet`` (changing it cancels running downloads); ``import_file`` installs an entry, and the runtime, from files copied to
this computer (offline installations), with the same checks.

Servers stay in this service's process group (the desktop stops the group with the service); their process IDs are recorded too,
so a service that was killed alone stops its leftover servers when it starts again.
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import urllib.error
import urllib.request
import zipfile

from suan.project.store import ProjectError

from .settings import TIERS, EndpointKeys, _read, _write_private

CATALOG_ENV = "STK_MODEL_CATALOG"
CATALOG_FORMAT = "stk.model-catalog/1"
STATE_FORMAT = "stk.local-models/1"
HEALTH_TIMEOUT_SECONDS = 600  # loading a large model from disk can take minutes
CHUNK = 1 << 20
PROGRESS_SECONDS = 0.25  # at most this often per entry, besides stage changes
_GIB = 1 << 30
_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _check_file(item, subject):
    if (not isinstance(item, dict) or not isinstance(item.get("name"), str) or not _NAME.fullmatch(item["name"])
            or type(item.get("size_bytes")) is not int or item["size_bytes"] <= 0
            or not isinstance(item.get("sha256"), str) or not _HEX.fullmatch(item["sha256"].lower())):
        raise ProjectError(f"The model catalog lists {subject} without a plain file name, size and SHA-256")


def load_catalog(path=None):
    """The model catalog ``{format, runtimes, entries}``; every file must carry a size and SHA-256."""
    source = Path(path or os.environ.get(CATALOG_ENV) or Path(__file__).with_name("catalog.json"))
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"The model catalog cannot be read: {exc}") from None
    if not isinstance(data, dict) or data.get("format") != CATALOG_FORMAT or not isinstance(data.get("entries"), list):
        raise ProjectError("The model catalog has an unknown format")
    seen = set()
    for entry in data["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not _ID.fullmatch(entry["id"]) or entry["id"] in seen:
            raise ProjectError("The model catalog has an entry without a unique, plain ID")
        seen.add(entry["id"])
        if entry.get("runtime") not in ("llama.cpp", "vllm") or not isinstance(entry.get("files"), list) or not entry["files"]:
            raise ProjectError(f"The catalog entry {entry['id']} has no runtime or files")
        for item in entry["files"]:
            _check_file(item, f"a file of {entry['id']}")
        for key in ("min_memory_gb", "total_bytes", "params_b", "serve_context"):
            value = entry.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                raise ProjectError(f"The catalog entry {entry['id']} has an invalid {key}")
        if entry.get("tier") is not None and entry["tier"] not in TIERS:
            raise ProjectError(f"The catalog entry {entry['id']} has an invalid tier")
        devices = entry.get("recommend_on", [])
        if not isinstance(devices, list) or not all(device in ("cpu", "gpu") for device in devices):
            raise ProjectError(f"The catalog entry {entry['id']} has an invalid recommend_on")
    for key, asset in ((data.get("runtimes") or {}).get("llama.cpp") or {}).get("assets", {}).items():
        _check_file(asset, f"the llama.cpp build for {key}")
    return data


def platform_key(system=None, machine=None):
    """``linux-x86_64``, ``macos-arm64``, ``windows-x86_64`` ... for runtime assets."""
    system = (system or platform.system()).lower()
    system = {"darwin": "macos"}.get(system, system)
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{machine}"


def _existing(path):
    path = Path(path)
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def probe(models_dir, run=subprocess.run):
    """Read-only facts about this computer for choosing a model; never installs or starts anything."""
    import psutil
    memory = psutil.virtual_memory()
    gpus = []
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = run([smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                      capture_output=True, text=True, timeout=10, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        for line in out.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) == 3 and parts[1].isdigit():
                gpus.append({"vendor": "nvidia", "name": parts[0], "memory_mib": int(parts[1]), "driver": parts[2], "unified": False})
    key = platform_key()
    if key == "macos-arm64":
        gpus.append({"vendor": "apple", "name": "Apple Silicon", "memory_mib": memory.total >> 20, "driver": "", "unified": True})
    return {"platform": key, "cpu_count": os.cpu_count() or 1, "memory_bytes": memory.total,
            "memory_available_bytes": memory.available, "disk_free_bytes": shutil.disk_usage(_existing(models_dir)).free,
            "gpus": gpus, "llama_gpu": _llama_gpu(key)}


_GPU_BUILDS = ("linux-x86_64", "macos-arm64")  # shipped llama.cpp builds with a GPU backend (Vulkan, Metal); others are CPU


def _llama_gpu(key):
    """Whether llama.cpp here can use a GPU: an administrator's own build (``STK_LLAMA_SERVER``), Apple Metal, or the Linux
    Vulkan build where the system's Vulkan loader is installed (without it the build runs on the CPU)."""
    if os.environ.get("STK_LLAMA_SERVER"):
        return True
    if key == "linux-x86_64":
        import ctypes.util
        return ctypes.util.find_library("vulkan") is not None
    return key == "macos-arm64"


def _nvidia_bytes(gpu):
    return ((gpu["memory_mib"] + 1023) >> 10) << 30  # nvidia-smi reports a little under the card's size (81559 MiB: "80 GB")


def _gpu_bytes(hardware):
    """Memory of the largest GPU llama.cpp can fill here: NVIDIA VRAM; for Apple unified memory Metal's default share
    (about two thirds up to 36 GB, three quarters above), never more than is free now. None without a GPU-capable build."""
    if not hardware.get("llama_gpu", hardware["platform"] in _GPU_BUILDS):
        return 0
    apple = []
    for gpu in hardware["gpus"]:
        if gpu["vendor"] == "apple":
            total = gpu["memory_mib"] << 20
            share = int(total * (0.75 if total > 36 * _GIB else 2 / 3))
            apple.append(min(share, int(hardware["memory_available_bytes"] * 0.9)))
    return max([_nvidia_bytes(gpu) for gpu in hardware["gpus"] if gpu["vendor"] == "nvidia"] + apple + [0])


def assess(hardware, entry, installed=False, present=0):
    """Whether an entry fits this computer: ``{fits, device, reason}``. Memory figures leave headroom; ``present`` bytes
    of the entry already downloaded need no more disk space."""
    need = float(entry.get("min_memory_gb") or 0) * _GIB
    nvidia = [gpu for gpu in hardware["gpus"] if gpu["vendor"] == "nvidia"]
    disk = max(0, int(entry.get("total_bytes") or 0) - present) * 1.05
    if not installed and disk > hardware["disk_free_bytes"]:
        return {"fits": False, "device": "", "reason": "disk"}
    if entry["runtime"] == "vllm":
        vram = sum(_nvidia_bytes(gpu) for gpu in nvidia)
        if not hardware["platform"].startswith("linux") or not nvidia:
            return {"fits": False, "device": "", "reason": "needs_linux_nvidia"}
        return {"fits": vram >= need, "device": "gpu", "reason": "" if vram >= need else "gpu_memory"}
    best_gpu = _gpu_bytes(hardware)
    if best_gpu >= need > 0:
        return {"fits": True, "device": "gpu", "reason": ""}
    if hardware["memory_available_bytes"] * 0.9 >= need:
        return {"fits": True, "device": "cpu", "reason": ""}
    return {"fits": False, "device": "", "reason": "memory"}


_TIERS = {"tiny": 0, "small": 1, "medium": 2, "large": 3}


def recommend(hardware, entries, installed=(), present=None):
    """Each entry with its assessment, and one llama.cpp entry recommended: the highest tier that fits; within it one
    that runs on the GPU, then the larger model; of a model's builds the 8-bit one only with 40% of its need to spare,
    else the 4-bit one. An entry with ``recommend_on`` is recommended only on those devices (``[]``: an alternative,
    never by default). vLLM entries are assessed but not recommended: STK cannot start vLLM yet, so a GPU server runs it
    itself and adds it as an endpoint. ``present``: bytes already downloaded, by entry."""
    present = present or {}
    assessed = [{**entry, **assess(hardware, entry, entry["id"] in installed, present.get(entry["id"], 0)), "recommended": False}
                for entry in entries]
    fitting = [item for item in assessed if item["fits"] and item["runtime"] == "llama.cpp"
               and item["device"] in item.get("recommend_on", ("cpu", "gpu"))]
    if fitting:
        def score(item):
            room = _gpu_bytes(hardware) if item["device"] == "gpu" else hardware["memory_available_bytes"]
            headroom = room >= 1.4 * float(item.get("min_memory_gb") or 0) * _GIB
            eight_bit = "8" in str(item.get("quantization", ""))
            return (_TIERS.get(item.get("tier"), 0), item["device"] == "gpu", float(item.get("params_b") or 0),
                    eight_bit and headroom, not eight_bit)
        max(fitting, key=score)["recommended"] = True
    return assessed


def _sha256(path, cancel=None):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            if cancel is not None and cancel.is_set():
                raise _Cancelled()
            digest.update(block)
    return digest.hexdigest()


class _Cancelled(Exception):
    pass


def _part(target, sha256):
    """The partial file of ``target``, named after the content it must become; partial files for other content are removed."""
    part = target.with_name(f"{target.name}.{sha256[:16]}.part")
    for stale in target.parent.glob(f"{target.name}.*.part"):
        if stale != part:
            stale.unlink(missing_ok=True)
    return part


def download(urls, target, *, size, sha256, progress=None, cancel=None, timeout=60):
    """Fetch ``target`` from the first source that delivers it, resuming a partial file across interruptions and sources.
    The file gets its name only when its size and SHA-256 match; an interrupted transfer keeps its partial file for the next
    source or attempt. Proxies follow the environment (campus proxies). Raises ``ProjectError`` or ``_Cancelled``."""
    if type(size) is not int or size <= 0 or not isinstance(sha256, str) or not _HEX.fullmatch(sha256.lower()):
        raise ProjectError(f"{Path(target).name} has no size and SHA-256 to check; it is not downloaded")
    sha256 = sha256.lower()
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = _part(target, sha256)
    if part.exists() and part.stat().st_size > size:
        part.unlink()
    errors = []
    attempts = list(urls)
    retried = set()
    while attempts:
        url = attempts.pop(0)
        resumed = part.exists() and part.stat().st_size > 0
        try:
            have = part.stat().st_size if part.exists() else 0
            if have < size:
                request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    if have and response.status != 206:
                        have = 0  # the server ignored the range: start again
                    expected = response.length  # remaining body bytes, or None when unknown (chunked)
                    with open(part, "ab" if have else "wb") as stream:
                        done = have
                        for block in iter(lambda: response.read(CHUNK), b""):
                            if cancel is not None and cancel.is_set():
                                raise _Cancelled()
                            stream.write(block)
                            done += len(block)
                            if progress is not None:
                                progress(done)
                    if expected is not None and done - have < expected:
                        raise ConnectionError(f"the connection closed after {done} of {size} bytes")
            have = part.stat().st_size
            if have < size:
                errors.append(f"{url}: incomplete ({have} of {size} bytes)")
                continue  # keep the partial file; the next source resumes it
            if have > size:
                part.unlink()
                errors.append(f"{url}: more bytes than expected")
                continue
            if _sha256(part, cancel) != sha256:
                part.unlink()
                errors.append(f"{url}: SHA-256 mismatch")
                if resumed and url not in retried:
                    retried.add(url)
                    attempts.insert(0, url)  # the earlier partial bytes may have been the bad ones: once more from scratch
                continue
            os.replace(part, target)
            return
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
    raise ProjectError(f"Download of {target.name} failed: " + "; ".join(errors)[:2000])


def _extract(archive, folder):
    """Unpack a zip or tar archive into ``folder``; refuses members that would land outside it, and links in tar files when
    this Python cannot filter them."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    root = folder.resolve()

    def inside(name):
        destination = (folder / name).resolve()
        if destination != root and root not in destination.parents:
            raise ProjectError(f"The runtime archive has an unsafe path: {name}")
        return destination

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                inside(member.filename)
            bundle.extractall(folder)
            for member in bundle.infolist():  # keep executable bits
                if (member.external_attr >> 16) & 0o111 and not member.is_dir():
                    (folder / member.filename).chmod(0o755)
        return
    try:
        with tarfile.open(archive) as bundle:
            members = bundle.getmembers()
            for member in members:
                inside(member.name)
            if hasattr(tarfile, "data_filter"):
                bundle.extractall(folder, filter="data")  # refuses links out of the folder, devices, absolute paths
            else:
                if any(not (member.isfile() or member.isdir()) for member in members):
                    raise ProjectError("This Python cannot safely unpack links in a tar archive; use a zip build or a newer Python")
                bundle.extractall(folder)
    except tarfile.TarError as exc:
        raise ProjectError(f"The runtime archive cannot be unpacked safely: {exc}") from None


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        return probe_socket.getsockname()[1]


_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASS|CREDENTIAL|CREDS|AUTH|PROXY", re.IGNORECASE)


def _server_environment(key):
    """The model server's environment: this service's, without secrets it has no use for (the Token Plan key, endpoint
    keys, Runtime tokens, proxies with credentials; it only listens on loopback and reads a local file), plus its own key."""
    return {**{name: value for name, value in os.environ.items() if not _SECRET_NAME.search(name)}, "LLAMA_API_KEY": key}


def endpoint_id(entry_id):
    """``local-<entry>`` within the endpoint ID rules (lowercase letters, digits, hyphens; at most 32)."""
    cleaned = "".join(c if c.isascii() and (c.isalnum() or c == "-") else "-" for c in entry_id.lower()).strip("-")
    if len(cleaned) > 26:
        cleaned = cleaned[:19].rstrip("-") + "-" + hashlib.sha256(entry_id.encode()).hexdigest()[:6]
    return "local-" + (cleaned or "model")


class LocalModels:
    def __init__(self, state_dir, endpoints, policy, emit=None, keys=None):
        self.root = Path(state_dir) / "models" / "local" if state_dir else None
        self.endpoints = endpoints
        self.policy = policy
        self.keys = keys if keys is not None else EndpointKeys()  # each server's API key, for this session only
        self.emit = emit or (lambda event, data: None)
        self._lock = threading.RLock()          # in-memory state and installed.json
        self._runtime_lock = threading.Lock()   # one runtime installation at a time
        self._jobs = {}      # entry id -> {"stage", "state", "done_bytes", "total_bytes", "error", "cancel"}
        self._servers = {}   # entry id -> {"process", "port", "state", "error"}
        self._emitted = {}   # entry id -> (time, stage) of the last progress event
        self._reap()

    # -- state -----------------------------------------------------------------------------------

    def _require_root(self):
        if self.root is None:
            raise ProjectError("This service has no private state folder for local models")
        return self.root

    def _state(self):
        if self.root is None:
            return {"entries": {}, "runtimes": {}, "servers": {}}
        with self._lock:
            data = _read(self.root / "installed.json") or {}
        if data.get("format") != STATE_FORMAT:
            return {"entries": {}, "runtimes": {}, "servers": {}}
        return {"entries": dict(data.get("entries") or {}), "runtimes": dict(data.get("runtimes") or {}),
                "servers": dict(data.get("servers") or {})}

    def _change(self, change):
        """Read, change and save ``installed.json`` atomically with respect to this service's other writers."""
        with self._lock:
            state = self._state()
            result = change(state)
            _write_private(self._require_root() / "installed.json", {"format": STATE_FORMAT, **state})
            return result

    def _reap(self):
        """Stop servers recorded by an earlier service that ended without stopping them (killed alone)."""
        if self.root is None or not (self.root / "installed.json").exists():
            return
        import psutil
        for record in self._state()["servers"].values():
            try:
                process = psutil.Process(int(record["pid"]))
                if abs(process.create_time() - float(record["created"])) < 1:
                    process.terminate()
                    try:
                        process.wait(10)
                    except psutil.TimeoutExpired:
                        process.kill()
            except (psutil.Error, KeyError, TypeError, ValueError):
                pass
        self._change(lambda state: state["servers"].clear())

    def catalog(self):
        return load_catalog()

    def _entry(self, entry_id):
        entry = next((item for item in self.catalog()["entries"] if item.get("id") == entry_id), None)
        if entry is None:
            raise ProjectError(f"No catalog entry {entry_id}")
        return entry

    def probe(self):
        return probe(self._require_root())

    def recommendations(self):
        hardware = self.probe()
        entries = self.catalog()["entries"]
        present = {entry["id"]: self._present_bytes(entry) for entry in entries}
        return {"hardware": hardware, "entries": recommend(hardware, entries, self._state()["entries"], present)}

    def _present_bytes(self, entry):
        """Bytes of the entry already on disk, complete or partial (an interrupted download resumes with them)."""
        folder = self._require_root() / "weights" / entry["id"]
        total = 0
        for item in entry["files"]:
            for path in (folder / item["name"], folder / f"{item['name']}.{item['sha256'][:16]}.part"):
                try:
                    total += min(path.stat().st_size, item["size_bytes"])
                    break
                except OSError:
                    continue
        return total

    @staticmethod
    def _server_view(value):
        state = value["state"]
        if state == "running" and (value.get("process") is None or value["process"].poll() is not None):
            state = "failed"  # exited between checks; the supervisor reports it too
        view = {"state": state}
        if value.get("port"):
            view["port"] = value["port"]
        if value.get("error"):
            view["error"] = value["error"]
        return view

    def list(self):
        """Installed entries with their server state, and installations (running or last finished)."""
        state = self._state()
        with self._lock:
            servers = {key: self._server_view(value) for key, value in self._servers.items()}
            jobs = {key: {k: v for k, v in value.items() if k != "cancel"} for key, value in self._jobs.items()}
        installed = [{"id": key, "endpoint": endpoint_id(key), "autostart": bool(value.get("autostart")),
                      "server": servers.get(key, {"state": "stopped"})} for key, value in state["entries"].items()]
        return {"installed": installed, "jobs": jobs, "runtimes": state["runtimes"]}

    def routing_view(self):
        """Installed llama.cpp entries for the automatic model choice: ``{id, endpoint, name, tier, state}``; entries the
        catalog of this STK no longer lists are left out (they cannot be started)."""
        entries = {entry["id"]: entry for entry in self.catalog()["entries"]}
        result = []
        for item in self.list()["installed"]:
            entry = entries.get(item["id"])
            if entry is None or entry["runtime"] != "llama.cpp":
                continue
            result.append({"id": item["id"], "endpoint": item["endpoint"], "name": str(entry.get("model") or item["id"])[:64],
                           "tier": entry.get("tier") or "small", "state": item["server"]["state"]})
        return result

    def is_running(self, endpoint):
        with self._lock:
            return any(endpoint_id(key) == endpoint and value["state"] == "running" and value.get("process") is not None
                       and value["process"].poll() is None for key, value in self._servers.items())

    def manages(self, endpoint):
        return any(endpoint_id(key) == endpoint for key in self._state()["entries"])

    # -- installing ------------------------------------------------------------------------------

    def _progress(self, entry_id, *, force=False, **fields):
        with self._lock:
            job = self._jobs.setdefault(entry_id, {})
            changed = fields.get("stage", job.get("stage")) != job.get("stage") or "state" in fields
            job.update(fields)
            data = {"id": entry_id, **{k: v for k, v in job.items() if k != "cancel"}}
            last = self._emitted.get(entry_id, 0.0)
            now = time.monotonic()
            if not (force or changed or now - last >= PROGRESS_SECONDS):
                return
            self._emitted[entry_id] = now
        self.emit("models.local.progress", data)

    def _begin(self, entry_id, total, stage):
        with self._lock:
            if self._jobs.get(entry_id, {}).get("state") == "running":
                raise ProjectError(f"{entry_id} is already being installed")
            if self._servers.get(entry_id, {}).get("state") in ("starting", "running"):
                raise ProjectError(f"Stop {entry_id} before installing it again")
            cancel = threading.Event()
            self._jobs[entry_id] = {"stage": stage, "state": "running", "done_bytes": 0, "total_bytes": total, "error": "",
                                    "cancel": cancel}
        self._progress(entry_id, force=True)
        return cancel

    def _run_job(self, entry_id, work, wait):
        def body():
            try:
                work()
                self._progress(entry_id, stage="done", state="done")
            except _Cancelled:
                self._progress(entry_id, stage="cancelled", state="cancelled")
            except Exception as exc:  # noqa: BLE001 - reported to the person; partial files stay for resuming
                self._progress(entry_id, stage="failed", state="failed", error=str(exc)[:2000])
        thread = threading.Thread(target=body, name="stk-model-install", daemon=True)
        thread.start()
        if wait:
            thread.join()

    def install(self, entry_id, *, wait=False):
        """Download the runtime (if needed) and the entry's files in the background; ``wait`` blocks (tests, scripts)."""
        entry = self._entry(entry_id)
        root = self._require_root()
        if self.policy.get()["network"] != "internet":
            raise ProjectError("Downloading models needs the network setting \"internet\"; or import the files from this computer")
        cancel = self._begin(entry_id, sum(item["size_bytes"] for item in entry["files"]), "queued")

        def work():
            if entry["runtime"] == "llama.cpp":
                self._install_runtime(entry_id, root, cancel)
            folder = root / "weights" / entry_id
            done_before = 0
            for item in entry["files"]:
                target = folder / item["name"]
                # A complete file was verified before it got its name (download keeps other bytes in a partial file).
                if not (target.exists() and target.stat().st_size == item["size_bytes"]):
                    self._progress(entry_id, stage="weights")
                    download(self._sources(entry, item["name"]), target, size=item["size_bytes"], sha256=item["sha256"],
                             cancel=cancel, progress=lambda done, base=done_before: self._progress(entry_id, done_bytes=base + done))
                done_before += item["size_bytes"]
            self._record(entry)

        self._run_job(entry_id, work, wait)
        return self.list()["jobs"][entry_id]

    def _record(self, entry):
        def change(state):
            previous = state["entries"].get(entry["id"], {})
            state["entries"][entry["id"]] = {"files": [item["name"] for item in entry["files"]], "runtime": entry["runtime"],
                                             "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                             "autostart": bool(previous.get("autostart"))}
        self._change(change)

    @staticmethod
    def _sources(entry, name):
        urls = [source["url"].replace("{file}", name) for source in entry.get("sources") or []
                if isinstance(source, dict) and isinstance(source.get("url"), str) and "{file}" in source["url"]]
        if not urls:
            raise ProjectError(f"The catalog gives no source for {name}")
        return urls

    def _runtime_asset(self):
        runtime = (self.catalog().get("runtimes") or {}).get("llama.cpp") or {}
        key = platform_key()
        asset = (runtime.get("assets") or {}).get(key)
        if not asset:
            raise ProjectError(f"The catalog has no llama.cpp build for {key}")
        return runtime["tag"], key, asset

    def _runtime_ready(self, tag, key):
        current = self._state()["runtimes"].get("llama.cpp") or {}
        return current.get("tag") == tag and current.get("platform") == key and Path(current.get("binary", "")).exists()

    def _install_runtime(self, entry_id, root, cancel, archive=None):
        """Download (or take ``archive``, already checked) and unpack the llama.cpp build for this platform, once."""
        tag, key, asset = self._runtime_asset()
        with self._runtime_lock:
            if self._runtime_ready(tag, key):
                return
            downloaded = archive is None
            if downloaded:  # an import keeps its stage: leaving the internet setting must not cancel it
                self._progress(entry_id, stage="runtime")
                archive = root / "downloads" / asset["name"]
                download(asset.get("urls") or [], archive, size=asset["size_bytes"], sha256=asset["sha256"], cancel=cancel)
            folder = root / "runtimes" / "llama.cpp" / f"{tag}-{key}"
            if folder.exists():
                shutil.rmtree(folder)
            _extract(archive, folder)
            names = ("llama-server.exe",) if key.startswith("windows") else ("llama-server",)
            binary = next((path for path in folder.rglob("*") if path.name in names and path.is_file()), None)
            if binary is None:
                raise ProjectError("The llama.cpp build contains no llama-server")
            if downloaded:
                archive.unlink(missing_ok=True)
            self._change(lambda state: state["runtimes"].__setitem__("llama.cpp", {"tag": tag, "platform": key, "binary": str(binary)}))

    def import_file(self, entry_id, path, *, wait=False):
        """Install an entry from files copied to this computer (offline), in the background: each must match the catalog's
        size and SHA-256 (checked on the copy). The llama.cpp build archive may be imported along, and is needed unless a
        runtime is installed already."""
        entry = self._entry(entry_id)
        if entry["runtime"] != "llama.cpp":
            raise ProjectError("Only llama.cpp entries can be imported; run vLLM yourself and add it as an endpoint")
        root = self._require_root()
        source = Path(path)
        if source.is_file():
            candidates = [source]
        elif source.is_dir():
            candidates = sorted(item for item in source.glob("*") if item.is_file())
        else:
            raise ProjectError(f"{path} is not a file or folder on this computer")
        files = {item["name"]: item for item in entry["files"]}
        found = {candidate.name: candidate for candidate in candidates if candidate.name in files}
        missing = sorted(set(files) - set(found))
        tag, key, asset = self._runtime_asset()
        runtime_file = next((candidate for candidate in candidates if candidate.name == asset["name"]), None)
        if not self._runtime_ready(tag, key) and runtime_file is None:
            missing.append(asset["name"])
        if missing:
            raise ProjectError("Missing files for this entry: " + ", ".join(missing))
        cancel = self._begin(entry_id, sum(item["size_bytes"] for item in entry["files"]), "import")

        def copy(candidate, item, folder):
            target = folder / item["name"]
            part = _part(target, item["sha256"].lower())
            shutil.copyfile(candidate, part)
            if part.stat().st_size != item["size_bytes"] or _sha256(part, cancel) != item["sha256"].lower():
                part.unlink(missing_ok=True)
                raise ProjectError(f"{item['name']} does not match the catalog; nothing was imported")
            return part, target

        def work():
            staged = []
            try:
                if runtime_file is not None and not self._runtime_ready(tag, key):
                    downloads = root / "downloads"
                    downloads.mkdir(parents=True, exist_ok=True)
                    part, target = copy(runtime_file, asset, downloads)
                    os.replace(part, target)
                    try:
                        self._install_runtime(entry_id, root, cancel, archive=target)
                    finally:
                        target.unlink(missing_ok=True)
                folder = root / "weights" / entry_id
                folder.mkdir(parents=True, exist_ok=True)
                for name, candidate in found.items():
                    staged.append(copy(candidate, files[name], folder))
                for part, target in staged:
                    os.replace(part, target)
                staged.clear()
                self._record(entry)
            finally:
                for part, _ in staged:
                    part.unlink(missing_ok=True)

        self._run_job(entry_id, work, wait)
        return self.list()

    def cancel(self, entry_id):
        with self._lock:
            job = self._jobs.get(entry_id)
            if job and job.get("state") == "running":
                job["cancel"].set()
        return self.list()

    def cancel_downloads(self):
        """The network setting left ``internet``: running downloads stop (their partial files stay)."""
        with self._lock:
            for job in self._jobs.values():
                if job.get("state") == "running" and job.get("stage") in ("queued", "runtime", "weights"):
                    job["cancel"].set()

    def remove(self, entry_id):
        with self._lock:
            if self._jobs.get(entry_id, {}).get("state") == "running":
                raise ProjectError(f"{entry_id} is being installed; cancel it first")
        self.stop(entry_id)
        root = self._require_root()
        with self._lock:  # once the entry is gone no start() can begin; stop one that began meanwhile
            self._change(lambda state: (state["entries"].pop(entry_id, None), state["servers"].pop(entry_id, None)))
            self._jobs.pop(entry_id, None)
            server = self._servers.pop(entry_id, None)
        if server:
            self._stop_process(server.get("process"))
            self.keys.clear(endpoint_id(entry_id))
        folder = root / "weights" / entry_id
        if folder.exists():
            shutil.rmtree(folder)
        try:
            self.endpoints.remove(endpoint_id(entry_id))
        except ProjectError:
            pass
        self.emit("models.changed", {})
        return self.list()

    # -- serving ---------------------------------------------------------------------------------

    def _binary(self):
        override = os.environ.get("STK_LLAMA_SERVER")  # administrators with their own build; tests (a JSON command list)
        if override:
            if override.startswith("["):
                command = json.loads(override)
                if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
                    raise ProjectError("STK_LLAMA_SERVER is a path or a JSON list of strings")
                return command
            return [override]
        binary = (self._state()["runtimes"].get("llama.cpp") or {}).get("binary")
        if not binary or not Path(binary).exists():
            raise ProjectError("The llama.cpp runtime is not installed; install a model or import the llama.cpp build")
        return [binary]

    def start(self, entry_id, *, wait=False):
        """Start the entry's server on a free loopback port; it is registered as a local endpoint once healthy. A start
        that cannot begin (not installed, no runtime, being installed ...) is also reported as a failed progress event,
        for whoever waits for this model (the desktop's automatic model choice), not only to the caller."""
        try:
            return self._start(entry_id, wait=wait)
        except Exception as exc:
            self.emit("models.local.progress", {"id": entry_id, "stage": "failed", "state": "failed", "error": str(exc)[:2000]})
            raise

    def _start(self, entry_id, *, wait):
        entry = self._entry(entry_id)
        if entry["runtime"] != "llama.cpp":
            raise ProjectError("Starting vLLM from STK is not available yet; start it yourself and add it as an endpoint")
        root = self._require_root()
        binary = self._binary()
        with self._lock:
            if entry_id not in self._state()["entries"]:
                raise ProjectError(f"{entry_id} is not installed")
            if self._jobs.get(entry_id, {}).get("state") == "running":
                raise ProjectError(f"{entry_id} is being installed")
            if self._servers.get(entry_id, {}).get("state") in ("starting", "running"):
                return self.list()
            port = _free_port()
            model = root / "weights" / entry_id / entry["files"][0]["name"]
            arguments = [*binary, "-m", str(model), "--host", "127.0.0.1", "--port", str(port), "--jinja",
                         "--alias", entry_id, "-c", str(int(entry.get("serve_context") or 8192)), "--no-slots",
                         # As for the Token Plan (enable_thinking false): a 4B model on a laptop CPU otherwise thinks
                         # for minutes before a two-sentence answer (measured: 2,300 hidden tokens, 3 minutes).
                         "--reasoning", "off"]
            # No -ngl: llama.cpp's default ("auto", fitted to the free VRAM) puts as many layers on a GPU as fit now.
            log = root / "logs" / f"{entry_id}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            # Same process group as this service (POSIX), so the desktop stops it with the service; Windows uses a job object.
            flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}
            # A fresh API key for each start: llama-server allows every CORS origin, so without a key any web page could use
            # the model and read its prompts. The key goes by environment (not the command line) and is kept for this session.
            key = secrets.token_urlsafe(32)
            with open(log, "ab") as stream:
                process = subprocess.Popen(arguments, stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                           env=_server_environment(key), **flags)
            self._servers[entry_id] = {"process": process, "port": port, "state": "starting", "error": ""}
            try:
                import psutil
                created = psutil.Process(process.pid).create_time()

                def change(state):
                    state["entries"][entry_id]["autostart"] = True
                    state["servers"][entry_id] = {"pid": process.pid, "created": created, "port": port}
                self._change(change)
            except Exception:
                self._servers.pop(entry_id, None)
                self._stop_process(process)
                raise
        self.emit("models.local.progress", {"id": entry_id, "stage": "starting", "state": "running"})
        thread = threading.Thread(target=self._supervise, args=(entry_id, process, port, key), name="stk-model-server",
                                  daemon=True)
        thread.start()
        if wait:
            deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS + 15
            while time.monotonic() < deadline and self._servers.get(entry_id, {}).get("state") == "starting":
                time.sleep(0.05)
        return self.list()

    def _current(self, entry_id, process):
        return self._servers.get(entry_id, {}).get("process") is process

    def _fail(self, entry_id, process, reason):
        """Report a server that did not start or stopped by itself (not one stopped on purpose)."""
        with self._lock:
            if not self._current(entry_id, process):
                return
            self._servers[entry_id].update(state="failed", error=reason)

            def change(state):
                state["servers"].pop(entry_id, None)
                if entry_id in state["entries"]:
                    state["entries"][entry_id]["autostart"] = False  # do not relaunch a model that fails
            self._change(change)
        self._stop_process(process)
        self.keys.clear(endpoint_id(entry_id))
        self.emit("models.local.progress", {"id": entry_id, "stage": "failed", "state": "failed", "error": reason})
        self.emit("models.changed", {})

    def _supervise(self, entry_id, process, port, key):
        """Wait for the health check, register the endpoint, then report the server if it exits by itself."""
        try:
            deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
            url = f"http://127.0.0.1:{port}/health"
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback: never a proxy
            healthy = False
            while time.monotonic() < deadline and process.poll() is None and self._current(entry_id, process):
                try:
                    with opener.open(url, timeout=5) as response:
                        if response.status == 200:
                            healthy = True
                            break
                except (urllib.error.URLError, http.client.HTTPException, OSError):
                    pass
                time.sleep(0.2)
            if not self._current(entry_id, process):
                return  # stopped on purpose meanwhile
            if not healthy:
                self._fail(entry_id, process, "the server exited" if process.poll() is not None else
                           "the server did not become ready in time")
                return
            entry = self._entry(entry_id)
            with self._lock:  # a stop() or remove() in between must not be undone by registering afterwards
                if not self._current(entry_id, process):
                    return
                self.endpoints.add(endpoint_id(entry_id), str(entry.get("model") or entry_id)[:64],
                                   f"http://127.0.0.1:{port}/v1", [entry_id])
                self.keys.set_managed(endpoint_id(entry_id), key)
                self._servers[entry_id]["state"] = "running"
            self.emit("models.local.progress", {"id": entry_id, "stage": "running", "state": "done"})
            self.emit("models.changed", {})
            code = process.wait()
            self._fail(entry_id, process, f"the server exited (code {code})")
        except Exception as exc:  # noqa: BLE001 - a supervisor that dies must not leave the server unreported
            self._fail(entry_id, process, f"the server could not be supervised: {exc}"[:2000])

    @staticmethod
    def _stop_process(process):
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(5)

    def stop(self, entry_id, *, keep_autostart=False):
        with self._lock:
            server = self._servers.pop(entry_id, None)
        if server:
            self._stop_process(server.get("process"))
        with self._lock:
            if entry_id in self._servers:  # started again while this one stopped: the new server owns key and record
                return self.list()
            if server:
                self.keys.clear(endpoint_id(entry_id))
            if self.root is not None:
                def change(state):
                    state["servers"].pop(entry_id, None)
                    if not keep_autostart and entry_id in state["entries"]:
                        state["entries"][entry_id]["autostart"] = False
                self._change(change)
        if server:
            self.emit("models.local.progress", {"id": entry_id, "stage": "stopped", "state": "done"})
        return self.list()

    def autostart(self):
        """Start again the servers that were running when the service last stopped."""
        for key, value in self._state()["entries"].items():
            if value.get("autostart"):
                try:
                    self.start(key)
                except Exception as exc:  # noqa: BLE001 - one entry must not stop the others
                    with self._lock:  # start() has reported it (models.local.progress)
                        self._servers[key] = {"process": None, "state": "failed", "error": str(exc)[:2000]}
                        # Not again at the next start (as for a server that fails after starting).
                        self._change(lambda state, key=key: state["entries"][key].update(autostart=False)
                                     if key in state["entries"] else None)

    def shutdown(self):
        """Stop every server this service started; they start again with the service (``autostart``)."""
        for key in list(self._servers):
            self.stop(key, keep_autostart=True)
