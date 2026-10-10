"""Optional software modules (E0b, docs/design/multiscale-engines.md): simulation engines (LAMMPS, ABACUS) and modeling
tools (Packmol; mBuild, foyer, GMSO and RDKit) that STK can use on this computer.

A person chooses which modules to add. For each module STK first **detects** an installation that is already there
(on PATH, in common conda environments, or in folders the person names) and uses it; only when none is found does it
**install** one, after the person confirms. It uses micromamba (``STK_MICROMAMBA``, one on PATH, or STK's own copy,
downloaded once and checked against the SHA-256 in ``catalog.json``) to create an environment from conda-forge in STK's
own folder. Engines then look their programs up here (``find_program``), on the same computer where they run.

The modules folder is ``~/.stk/modules`` (``STK_MODULES_DIR``), shared by the desktop's service and a Runtime started
by the same user on this computer; its ``registry.json`` is written under a file lock. Installing needs the network
setting to allow the internet; switching it off cancels running installations. An environment being made carries a
marker (``envs/<id>.incomplete``) until it is checked, so a half-made one is never taken for an installed module.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform as _platform
import queue
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time

from suan.project.store import ProjectError

CATALOG = Path(__file__).with_name("catalog.json")
REGISTRY_FORMAT = "stk.module-registry/1"
PROBE_TIMEOUT = 20
INSTALL_TIMEOUT = 3 * 3600
SILENCE_TIMEOUT = 1800  # an installer that prints nothing for this long is stopped
_LOG_LINES = 40
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.+-]{0,63}")
_PACKAGE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.=*<>-]{0,59}")
# What an installer may see of this service's environment (never keys or tokens).
_INSTALL_ENV = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "http_proxy", "https_proxy", "no_proxy",
                "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
                "SYSTEMROOT", "SYSTEMDRIVE", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "COMSPEC", "PATHEXT", "WINDIR")


def default_root():
    return Path(os.environ.get("STK_MODULES_DIR", str(Path.home() / ".stk" / "modules")))


def platform_key(system=None, machine=None):
    system = (system or _platform.system()).lower()
    machine = (machine or _platform.machine()).lower()
    arm = machine in ("arm64", "aarch64")
    if system == "linux":
        return "linux-aarch64" if arm else "linux-64"
    if system == "darwin":
        return "osx-arm64" if arm else "osx-64"
    if system == "windows":
        return "win-64"
    return f"{system}-{machine}"


def load_catalog(path=None):
    data = json.loads(Path(path or os.environ.get("STK_MODULE_CATALOG") or CATALOG).read_text(encoding="utf-8"))
    if data.get("format") != "stk.modules/1":
        raise ProjectError("Not an STK module catalog")
    for entry in data["modules"]:
        if entry.get("kind") not in ("engine", "tool", "python") or not re.fullmatch(r"[a-z0-9-]{1,40}", entry.get("id", "")):
            raise ProjectError(f"Invalid module entry {entry.get('id')!r}")
        install, detect = entry.get("install", {}), entry.get("detect", {})
        packages = install.get("packages")
        if (not isinstance(install.get("channel"), str) or not _NAME.fullmatch(install["channel"]) or not packages
                or not all(isinstance(item, str) and _PACKAGE.fullmatch(item) for item in packages)):
            raise ProjectError(f"Invalid installation of module {entry['id']}")
        names = detect.get("imports") if entry["kind"] == "python" else detect.get("executables")
        if (not names or not all(isinstance(name, str) and _NAME.fullmatch(name) for name in names)
                or not all(isinstance(arg, str) and arg.startswith("-") and len(arg) <= 32 for arg in detect.get("version_args", []))):
            raise ProjectError(f"Invalid detection of module {entry['id']}")
        if entry["kind"] == "python" and detect.get("version_of") not in names:
            raise ProjectError(f"Invalid detection of module {entry['id']}")
    return data


def _now():
    return datetime.now(timezone.utc).isoformat()


def _bin_folders(prefix):
    """Where a conda environment keeps programs: bin (Linux, macOS); Scripts, Library\\bin and the root (Windows)."""
    prefix = Path(prefix)
    if os.name == "nt":
        return [prefix / "Scripts", prefix / "Library" / "bin", prefix]
    return [prefix / "bin"]


def _conda_bins(home=None):
    """Program folders of common conda installations and their environments (most specific first)."""
    home = Path(home or Path.home())
    roots = [Path(os.environ["CONDA_PREFIX"])] if os.environ.get("CONDA_PREFIX") else []
    for name in ("miniforge3", "mambaforge", "miniconda3", "anaconda3", "micromamba"):
        roots.append(home / name)
    roots += [Path("/opt/conda"), Path("/opt/miniforge3")]
    found = []
    for root in roots:
        for prefix in sorted(root.glob("envs/*")) + [root]:
            for folder in _bin_folders(prefix):
                if folder.is_dir() and folder not in found:
                    found.append(folder)
    return found


def _kill_group(process):
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def _run(argv, timeout=PROBE_TIMEOUT):
    """Output of a short probe (stdout and stderr together), or None when it cannot run. Runs in an empty folder (so
    nothing in the service's folder is read or written) in its own process group, which a timeout ends entirely."""
    with tempfile.TemporaryDirectory(prefix="stk-probe-") as folder:
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       cwd=folder, start_new_session=os.name != "nt")
        except OSError:
            return None
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(process)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            return None
    return output.decode("utf-8", errors="replace")


@contextmanager
def _file_lock(path):
    """An exclusive lock between processes sharing the modules folder (the service and a Runtime)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            for _ in range(600):
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _clean_entry(entry):
    """A registry entry of the right shape (what another STK version or a person wrote may not be), or None."""
    if (not isinstance(entry, dict) or entry.get("source") not in ("detected", "installed")
            or not isinstance(entry.get("programs"), dict)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in entry["programs"].items())):
        return None
    version = entry.get("version")
    return {**entry, "version": version[:100] if isinstance(version, str) else None,
            "prefix": entry.get("prefix") if isinstance(entry.get("prefix"), str) else None}


class InstallCancelled(Exception):
    pass


class Modules:
    def __init__(self, root=None, policy=None, emit=None, catalog=None, extra_paths=()):
        self.root = Path(root) if root else default_root()
        self.policy = policy
        self.emit = emit
        self._catalog = catalog
        self.extra_paths = [Path(path) for path in extra_paths]
        self._lock = threading.Lock()
        self._download_lock = threading.Lock()
        self._jobs = {}

    # ---- catalog and registry ----

    def catalog(self):
        if self._catalog is None:
            self._catalog = load_catalog()
        return self._catalog

    def _entry(self, module_id):
        entry = next((item for item in self.catalog()["modules"] if item["id"] == module_id), None)
        if entry is None:
            raise ProjectError(f"Unknown module {module_id}")
        return entry

    def _registry(self):
        try:
            data = json.loads((self.root / "registry.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None  # missing or damaged: rebuilt by the next detection
        if not isinstance(data, dict) or data.get("format") != REGISTRY_FORMAT or not isinstance(data.get("modules"), dict):
            return {"format": REGISTRY_FORMAT, "modules": {}, "detected_at": None}
        modules = {key: entry for key, entry in ((key, _clean_entry(value)) for key, value in data["modules"].items()) if entry}
        detected = data.get("detected_at")
        return {"format": REGISTRY_FORMAT, "modules": modules, "detected_at": detected if isinstance(detected, str) else None}

    @contextmanager
    def _update(self):
        """Read, change and write the registry under the file lock (and this service's lock)."""
        with self._lock, _file_lock(self.root / "registry.lock"):
            registry = self._registry()
            yield registry
            self.root.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(prefix="registry.", suffix=".tmp", dir=self.root)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(registry, ensure_ascii=False, indent=1) + "\n")
            os.replace(temporary, self.root / "registry.json")

    def _env(self, module_id):
        return self.root / "envs" / module_id

    def _marker(self, module_id):
        return self.root / "envs" / f"{module_id}.incomplete"

    def _complete(self, module_id):
        return self._env(module_id).is_dir() and not self._marker(module_id).exists()

    # ---- detection ----

    def _search_path(self, module_id):
        """Where to look, most preferred first: STK's own environment (when complete), folders the person named, PATH,
        conda installations."""
        own = _bin_folders(self._env(module_id)) if self._complete(module_id) else []
        folders = own + self.extra_paths + [Path(item) for item in os.environ.get("PATH", "").split(os.pathsep) if item]
        folders += _conda_bins()
        seen, result = set(), []
        for folder in folders:
            key = str(folder)
            if key not in seen:
                seen.add(key)
                result.append(folder)
        return result

    def _managed(self, module_id, path):
        try:
            return self._complete(module_id) and Path(path).resolve().is_relative_to(self._env(module_id).resolve())
        except OSError:
            return False

    def _detect_program(self, entry):
        rules = entry["detect"]
        for folder in self._search_path(entry["id"]):
            for name in rules["executables"]:
                candidate = shutil.which(name, path=str(folder))
                if not candidate:
                    continue
                version = None
                if rules.get("version_args"):
                    output = _run([candidate, *rules["version_args"]]) or ""
                    match = re.search(rules.get("version_pattern", r"([0-9][0-9A-Za-z._-]*)"), output)
                    version = next((group.strip()[:100] for group in match.groups() if group), None) if match else None
                return {"programs": {name: candidate}, "prefix": str(Path(candidate).resolve().parent.parent),
                        "version": version, "managed": self._managed(entry["id"], candidate)}
        return None

    def _detect_python(self, entry):
        rules = entry["detect"]
        probe = ("import importlib, json; names = %r; mods = [importlib.import_module(n) for n in names]; "
                 "print(json.dumps({'version': getattr(mods[names.index(%r)], '__version__', None)}))"
                 % (rules["imports"], rules["version_of"]))
        candidates = []
        for folder in self._search_path(entry["id"]):
            for name in ("python3", "python"):
                found = shutil.which(name, path=str(folder))
                if found and found not in candidates:
                    candidates.append(found)
        for python in candidates:
            output = _run([python, "-I", "-c", probe], timeout=60)
            if not output:
                continue
            try:
                version = json.loads(output.strip().splitlines()[-1])["version"]
            except (ValueError, KeyError, IndexError, TypeError):
                continue
            return {"programs": {"python": python}, "prefix": str(Path(python).resolve().parent.parent),
                    "version": str(version)[:100] if version is not None else None, "managed": self._managed(entry["id"], python)}
        return None

    def _running(self, module_id):
        with self._lock:
            job = self._jobs.get(module_id)
            return job is not None and job["state"] == "running"

    def detect(self, module_id=None, *, installing=False):
        """Look for each module (or one) and record what was found; returns the listing. A module being installed is
        left to its installation (which checks its own result with ``installing``)."""
        entries = [self._entry(module_id)] if module_id else self.catalog()["modules"]
        found = {}
        for entry in entries:
            if not installing and self._running(entry["id"]):
                continue
            found[entry["id"]] = self._detect_python(entry) if entry["kind"] == "python" else self._detect_program(entry)
        with self._update() as registry:
            for identity, result in found.items():
                current = registry["modules"].get(identity)
                if result is None:
                    # An installation that finished while this probe ran stays (its environment is complete).
                    if not (current and current["source"] == "installed" and self._complete(identity)):
                        registry["modules"].pop(identity, None)
                elif result["managed"] and not self._complete(identity):
                    registry["modules"].pop(identity, None)  # removed while this probe ran
                else:
                    registry["modules"][identity] = {**result, "source": "installed" if result["managed"] else "detected",
                                                     "detected_at": _now()}
            registry["detected_at"] = _now()
        return self.list()

    def list(self):
        """Every module of the catalog with what is known about it on this computer, and any install in progress."""
        registry = self._registry()
        key = platform_key()
        with self._lock:
            jobs = {identity: {name: value for name, value in job.items() if not name.startswith("_")}
                    for identity, job in self._jobs.items()}
        items = []
        for entry in self.catalog()["modules"]:
            found = registry["modules"].get(entry["id"])
            state = "missing" if found is None else found["source"]
            if entry["id"] in jobs and jobs[entry["id"]]["state"] == "running":
                state = "installing"
            items.append({"id": entry["id"], "name": entry["name"], "kind": entry["kind"], "scale": entry["scale"],
                          "purpose": entry["purpose"], "license": entry["license"], "homepage": entry["homepage"],
                          "state": state, "version": (found or {}).get("version"), "programs": (found or {}).get("programs", {}),
                          "prefix": (found or {}).get("prefix"), "installable": key in entry["platforms"],
                          "approximate_mb": entry["install"]["approximate_mb"], "packages": entry["install"]["packages"],
                          "job": jobs.get(entry["id"])})
        return {"root": str(self.root), "platform": key, "detected_at": registry["detected_at"], "modules": items}

    def find_program(self, module_id, name=None):
        """The path of a module's program as registered here (detected or installed), else None."""
        found = self._registry()["modules"].get(module_id)
        if not found or (found["source"] == "installed" and not self._complete(module_id)):
            return None
        programs = found.get("programs", {})
        path = programs.get(name) if name else next(iter(programs.values()), None)
        return path if path and Path(path).exists() else None

    # ---- installation ----

    def _micromamba(self, cancel, progress):
        """A micromamba program: STK_MICROMAMBA or one on PATH (used as the person installed it), else STK's own copy,
        downloaded once (one download at a time) and checked against the catalog's SHA-256."""
        named = os.environ.get("STK_MICROMAMBA")
        if named:
            return named
        found = shutil.which("micromamba")
        if found:
            return found
        spec = self.catalog()["micromamba"]
        key = platform_key()
        file = spec["files"].get(key)
        if file is None:
            raise ProjectError(f"No micromamba for {key}")
        target = self.root / "bin" / ("micromamba.exe" if os.name == "nt" else "micromamba")
        with self._download_lock:
            if not target.exists():
                from suan.models.local import _Cancelled, download
                progress(stage="micromamba")
                try:
                    download([spec["url"].format(platform=key)], target, size=file["size_bytes"], sha256=file["sha256"],
                             cancel=cancel)
                except _Cancelled:
                    raise InstallCancelled() from None
                target.chmod(0o755)
        return str(target)

    def install(self, module_id, *, wait=False):
        """Install a module that was not found (after detecting again); returns its job. The same module again while it
        installs returns that job."""
        entry = self._entry(module_id)
        if platform_key() not in entry["platforms"]:
            raise ProjectError(f"{entry['name']} cannot be installed here ({platform_key()})")
        if self.policy is not None and not self.policy.allows("external"):
            raise ProjectError("Installing needs the network setting to allow the internet (Models and network)")
        if self._running(module_id):
            return self.job(module_id)
        self.detect(module_id)
        if self._registry()["modules"].get(module_id):
            raise ProjectError(f"{entry['name']} is already on this computer; it is used as it is")
        cancel = threading.Event()
        with self._lock:
            job = self._jobs.get(module_id)
            if job is not None and job["state"] == "running":  # another request started it meanwhile
                return {key: value for key, value in job.items() if not key.startswith("_")}
            self._jobs[module_id] = {"id": module_id, "state": "running", "stage": "starting", "log": [], "error": None,
                                     "started_at": _now(), "finished_at": None, "_cancel": cancel, "_process": None}
        thread = threading.Thread(target=self._install, args=(entry, cancel), name="stk-module-install", daemon=True)
        thread.start()
        if wait:
            thread.join()
        return self.job(module_id)

    def _progress(self, module_id, **fields):
        with self._lock:
            job = self._jobs[module_id]
            line = fields.pop("line", None)
            if line:
                job["log"] = (job["log"] + [line[:300]])[-_LOG_LINES:]
            job.update(fields)
            snapshot = {key: value for key, value in job.items() if not key.startswith("_")}
        if self.emit is not None:
            self.emit("modules.progress", {"id": module_id, "state": snapshot["state"], "stage": snapshot["stage"],
                                           "line": snapshot["log"][-1] if snapshot["log"] else None})

    def _install(self, entry, cancel):
        module_id = entry["id"]
        prefix, marker = self._env(module_id), self._marker(module_id)
        process = None
        try:
            micromamba = self._micromamba(cancel, lambda **fields: self._progress(module_id, **fields))
            if cancel.is_set():
                raise InstallCancelled()
            prefix.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(_now())  # until the result is checked, this environment is not a module
            if prefix.exists():
                shutil.rmtree(prefix)  # a half-made environment of an earlier attempt
            self._progress(module_id, stage="installing")
            env = {key: os.environ[key] for key in _INSTALL_ENV if key in os.environ}
            env.update(MAMBA_ROOT_PREFIX=str(self.root / "mamba"), CONDA_PKGS_DIRS=str(self.root / "pkgs"))
            argv = [micromamba, "create", "--yes", "--prefix", str(prefix), "--override-channels",
                    "--channel", entry["install"]["channel"], *entry["install"]["packages"]]
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                       env=env, start_new_session=os.name != "nt")
            with self._lock:
                self._jobs[module_id]["_process"] = process
            lines = queue.Queue()

            def read():
                for raw in process.stdout:
                    lines.put(raw)
                lines.put(None)
            threading.Thread(target=read, name="stk-module-output", daemon=True).start()
            started = last = time.monotonic()
            while True:
                if cancel.is_set():
                    raise InstallCancelled()
                now = time.monotonic()
                if now - started > INSTALL_TIMEOUT or now - last > SILENCE_TIMEOUT:
                    raise ProjectError("The installation took too long and was stopped")
                try:
                    raw = lines.get(timeout=0.5)
                except queue.Empty:
                    continue
                if raw is None:
                    break
                last = time.monotonic()
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self._progress(module_id, line=line)
            code = process.wait(timeout=60)
            if cancel.is_set():
                raise InstallCancelled()
            if code != 0:
                raise ProjectError(f"micromamba exited with {code}")
            marker.unlink(missing_ok=True)
            self.detect(module_id, installing=True)
            if (self._registry()["modules"].get(module_id) or {}).get("source") != "installed":
                marker.write_text(_now())
                raise ProjectError(f"{entry['name']} was installed but its programs were not found in {prefix}")
            self._progress(module_id, state="done", stage="done", finished_at=_now())
        except InstallCancelled:
            self._abandon(process, prefix, marker)
            self._progress(module_id, state="cancelled", stage="cancelled", finished_at=_now())
        except Exception as exc:  # noqa: BLE001 - a job ends recorded
            self._abandon(process, prefix, marker)
            self._progress(module_id, state="failed", stage="failed", error=str(exc)[:1000], finished_at=_now())

    @staticmethod
    def _abandon(process, prefix, marker):
        """Stop the installer (it may be in the middle of writing) before removing what it made."""
        if process is not None:
            _terminate(process)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                _kill_group(process)
        shutil.rmtree(prefix, ignore_errors=True)
        marker.unlink(missing_ok=True)

    def job(self, module_id):
        with self._lock:
            job = self._jobs.get(module_id)
            if job is None:
                raise ProjectError(f"No installation of {module_id} in this service")
            return {key: value for key, value in job.items() if not key.startswith("_")}

    def cancel(self, module_id):
        with self._lock:
            job = self._jobs.get(module_id)
            if job is None:
                raise ProjectError(f"No installation of {module_id} in this service")
            job["_cancel"].set()
            process = job.get("_process")
        if process is not None:
            _terminate(process)
        return self.job(module_id)

    def cancel_all(self):
        """Stop every running installation (for example when the network setting no longer allows the internet)."""
        with self._lock:
            jobs = [job for job in self._jobs.values() if job["state"] == "running"]
        for job in jobs:
            job["_cancel"].set()
            if job.get("_process") is not None:
                _terminate(job["_process"])

    def remove(self, module_id):
        """Remove a module STK installed (never one that was detected elsewhere)."""
        self._entry(module_id)
        if self._running(module_id):
            raise ProjectError("The module is being installed; cancel it first")
        with self._update() as registry:
            found = registry["modules"].get(module_id)
            if found and found["source"] != "installed":
                raise ProjectError("This module was found on this computer, not installed by STK; STK leaves it alone")
            registry["modules"].pop(module_id, None)
            if self._env(module_id).exists():
                self._marker(module_id).write_text(_now())
        # The (possibly large) folder goes outside the locks; its marker keeps it from being taken for a module meanwhile.
        shutil.rmtree(self._env(module_id), ignore_errors=True)
        self._marker(module_id).unlink(missing_ok=True)
        return self.list()

    def shutdown(self):
        self.cancel_all()


def _terminate(process):
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except (OSError, ProcessLookupError):
        pass


def find_program(module_id, name=None, root=None):
    """For engine launchers: a module's program registered on this computer, else None."""
    return Modules(root).find_program(module_id, name)


__all__ = ["Modules", "default_root", "find_program", "load_catalog", "platform_key"]
