"""One-click local models (S1c, docs/design/model-gateway.md): probe, recommend, download and verify, serve, register.

Nothing here reaches the internet: downloads come from an in-process HTTP server (tests/local_models_fixture.py) and the
model server is tests/fake_llama_server.py.
"""
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import threading
import time
from uuid import uuid4
import zipfile

import pytest

from suan.models import Endpoints, LocalModels, ModelPolicy
from suan.models import local as local_module
from suan.models.local import _extract, assess, download, endpoint_id, load_catalog, probe, recommend
from suan.project import ProjectError
from suan.scripting import Project
from local_models_fixture import FAKE_SERVER, Files, runtime_zip, sha, write_catalog
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_project_contexts import model, capture  # noqa: F401
from test_request_executor import eventually

GIB = 1 << 30


@pytest.fixture
def files():
    server = Files()
    yield server
    server.close()


@pytest.fixture
def managers():
    """LocalModels made by a test; every server they started is stopped afterwards, also when the test fails."""
    made = []
    yield made
    for local in made:
        local.shutdown()


def hardware(**fields):
    base = {"platform": "linux-x86_64", "cpu_count": 8, "memory_bytes": 16 * GIB, "memory_available_bytes": 12 * GIB,
            "disk_free_bytes": 500 * GIB, "gpus": []}
    return {**base, **fields}


ENTRIES = [
    {"id": "tiny-q4", "params_b": 1.7, "runtime": "llama.cpp", "quantization": "Q4_K_M", "min_memory_gb": 2, "total_bytes": GIB},
    {"id": "small-q4", "params_b": 8, "runtime": "llama.cpp", "quantization": "Q4_K_M", "min_memory_gb": 7, "total_bytes": 5 * GIB},
    {"id": "small-q8", "params_b": 8, "runtime": "llama.cpp", "quantization": "Q8_0", "min_memory_gb": 10, "total_bytes": 9 * GIB},
    {"id": "medium-q4", "params_b": 32, "runtime": "llama.cpp", "quantization": "Q4_K_M", "min_memory_gb": 22, "total_bytes": 20 * GIB},
    {"id": "large-vllm", "params_b": 72, "runtime": "vllm", "quantization": "bf16", "min_memory_gb": 160, "total_bytes": 145 * GIB},
]


def test_recommendations_fit_laptops_workstations_and_gpu_servers():
    laptop = recommend(hardware(), ENTRIES)
    assert {item["id"]: item["fits"] for item in laptop} == {"tiny-q4": True, "small-q4": True, "small-q8": True,
                                                             "medium-q4": False, "large-vllm": False}
    # 12 GB free is not 1.5 x the 8-bit model's need: the 4-bit build of the largest fitting model is recommended.
    assert [item["id"] for item in laptop if item["recommended"]] == ["small-q4"]
    assert next(item for item in laptop if item["id"] == "large-vllm")["reason"] == "needs_linux_nvidia"
    workstation = recommend(hardware(memory_available_bytes=60 * GIB, gpus=[{"vendor": "nvidia", "name": "RTX 4090",
                                                                              "memory_mib": 24576, "driver": "550", "unified": False}]), ENTRIES)
    assert [item["id"] for item in workstation if item["recommended"]] == ["medium-q4"]
    assert next(item for item in workstation if item["id"] == "medium-q4")["device"] == "gpu"
    # A GPU server fits the vLLM entry, but STK cannot start vLLM yet: the recommendation stays installable.
    server = recommend(hardware(memory_available_bytes=900 * GIB, gpus=[{"vendor": "nvidia", "name": "H100", "memory_mib": 81920,
                                                                         "driver": "550", "unified": False}] * 2), ENTRIES)
    assert next(item for item in server if item["id"] == "large-vllm")["fits"]
    assert [item["id"] for item in server if item["recommended"]] == ["medium-q4"]
    apple = {"vendor": "apple", "name": "Apple Silicon", "driver": "", "unified": True}
    mac = assess(hardware(platform="macos-arm64", gpus=[{**apple, "memory_mib": 65536}], memory_available_bytes=40 * GIB), ENTRIES[3])
    assert mac == {"fits": True, "device": "gpu", "reason": ""}  # unified memory: 64 GB x 0.75 = 48 GB, 36 GB free >= 22 GB
    # A 32 GB Mac gives Metal about two thirds (21 GB < 22 GB), and never more than is free.
    assert assess(hardware(platform="macos-arm64", gpus=[{**apple, "memory_mib": 32768}], memory_available_bytes=30 * GIB),
                  ENTRIES[3])["device"] == "cpu"
    assert assess(hardware(platform="macos-arm64", gpus=[{**apple, "memory_mib": 65536}], memory_available_bytes=8 * GIB),
                  ENTRIES[3])["reason"] == "memory"
    assert assess(hardware(disk_free_bytes=GIB), ENTRIES[1])["reason"] == "disk"
    assert assess(hardware(disk_free_bytes=GIB), ENTRIES[1], present=9 * GIB // 2)["fits"]  # most of it already downloaded


def test_probe_reads_nvidia_gpus_and_never_starts_anything(tmp_path, monkeypatch):
    monkeypatch.setattr(local_module.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)

    class Done:
        stdout = "NVIDIA A100-SXM4-80GB, 81920, 550.54\nnot, a, gpu\n"

    calls = []
    result = probe(tmp_path / "missing" / "models", run=lambda *a, **k: calls.append(a) or Done())
    assert result["gpus"][0] == {"vendor": "nvidia", "name": "NVIDIA A100-SXM4-80GB", "memory_mib": 81920, "driver": "550.54",
                                 "unified": False}
    assert result["memory_bytes"] > 0 and result["disk_free_bytes"] > 0 and calls[0][0][1].startswith("--query-gpu")


def test_the_catalog_must_give_every_file_a_size_and_checksum(tmp_path, files):
    path = write_catalog(tmp_path, files)
    assert load_catalog(path)["entries"][0]["id"] == "tiny-q4"
    data = json.loads(path.read_text())
    for broken in ({"sha256": None}, {"size_bytes": None}, {"name": "../escape.gguf"}, {"sha256": "abc"}):
        changed = json.loads(json.dumps(data))
        changed["entries"][0]["files"][0].update(broken)
        path.write_text(json.dumps(changed))
        with pytest.raises(ProjectError, match="size and SHA-256"):
            load_catalog(path)
    changed = json.loads(json.dumps(data))
    next(iter(changed["runtimes"]["llama.cpp"]["assets"].values()))["sha256"] = None
    path.write_text(json.dumps(changed))
    with pytest.raises(ProjectError, match="llama.cpp build"):
        load_catalog(path)
    for field, value in (("recommend_on", None), ("recommend_on", ["tpu"]), ("min_memory_gb", "8"), ("total_bytes", -1)):
        changed = json.loads(json.dumps(data))
        changed["entries"][0][field] = value
        path.write_text(json.dumps(changed))
        with pytest.raises(ProjectError, match=f"invalid {field}"):
            load_catalog(path)
    with pytest.raises(ProjectError, match="no size and SHA-256"):
        download([files.url + "/runtime.zip"], tmp_path / "x.zip", size=None, sha256=None)


def test_the_shipped_catalog_is_complete_and_recommends_qwen_by_machine(monkeypatch):
    from suan.desktop_bridge.schema import _resolved, check_value
    monkeypatch.delenv(local_module.CATALOG_ENV, raising=False)
    catalog = load_catalog()
    entries = catalog["entries"]
    assert set(catalog["runtimes"]["llama.cpp"]["assets"]) == {"linux-x86_64", "linux-arm64", "macos-arm64", "macos-x86_64",
                                                                "windows-x86_64"}
    assert len({endpoint_id(entry["id"]) for entry in entries}) == len(entries)
    for entry in entries:
        assert entry["total_bytes"] == sum(item["size_bytes"] for item in entry["files"])
        names = [source["name"] for source in entry["sources"]]
        assert names == ["ModelScope", "Hugging Face"] and all("{file}" in source["url"] for source in entry["sources"])
        assert "/resolve/master/" not in entry["sources"][1]["url"]  # Hugging Face is pinned to the hashed revision
        if entry["runtime"] == "llama.cpp":
            assert 0 < entry["serve_context"] <= entry["context_length"] and len(entry["files"]) == 1
    # Every entry, as the service reports it, matches the desktop protocol.
    for item in recommend(hardware(), entries):
        assert check_value(item, _resolved("#/$defs/localModelEntry")) == []

    def chosen(**fields):
        return [item["id"] for item in recommend(hardware(**fields), entries) if item["recommended"]]

    nvidia = {"vendor": "nvidia", "driver": "550", "unified": False}
    assert chosen(memory_available_bytes=4 * GIB) == []
    assert chosen(memory_available_bytes=5 * GIB) == ["qwen3.5-4b-q4_k_m-8k"]    # an 8 GB laptop: the small model, 8K context
    assert chosen(memory_available_bytes=7 * GIB) == ["qwen3.5-4b-q4_k_m"]       # Gemma is an alternative, never the default
    assert chosen(memory_available_bytes=10 * GIB) == ["qwen3.5-9b-q4_k_m"]      # a 16 GB laptop
    assert chosen(memory_available_bytes=50 * GIB) == ["qwen3.6-35b-a3b-q4_k_m"]  # CPU only: the 3B-active MoE
    assert chosen(memory_available_bytes=100 * GIB) == ["qwen3.6-35b-a3b-q8_0"]   # 8-bit with room to spare
    rtx4090, rtx3060 = {**nvidia, "name": "RTX 4090", "memory_mib": 24564}, {**nvidia, "name": "RTX 3060", "memory_mib": 12288}
    assert chosen(gpus=[rtx4090]) == ["qwen3.8-27b-q4_k_m"]
    # Plenty of RAM does not move the choice off the GPU: the dense 27B on the card, not the MoE on the CPU.
    assert chosen(gpus=[rtx4090], memory_available_bytes=50 * GIB) == ["qwen3.8-27b-q4_k_m"]
    assert chosen(gpus=[rtx3060], memory_available_bytes=19 * GIB) == ["qwen3.5-9b-q4_k_m"]  # on the card, not 8-bit on CPU
    assert chosen(gpus=[{**nvidia, "name": "H100", "memory_mib": 81559}] * 4) == ["qwen3.8-27b-q8_0"]  # vLLM: run it yourself
    assert chosen(gpus=[{**nvidia, "name": "RTX 6000 Ada", "memory_mib": 49140}]) == ["qwen3.8-27b-q8_0"]  # a 48 GB card
    # The shipped Windows and Linux arm64 builds have no GPU backend: their models run from memory.
    for system in ("windows-x86_64", "linux-arm64"):
        assert chosen(platform=system, gpus=[rtx4090], memory_available_bytes=10 * GIB) == ["qwen3.5-9b-q4_k_m"]
    assert chosen(gpus=[rtx4090], llama_gpu=False, memory_available_bytes=10 * GIB) == ["qwen3.5-9b-q4_k_m"]  # no Vulkan
    server = next(item for item in recommend(hardware(gpus=[{**nvidia, "name": "H100", "memory_mib": 81559}]), entries)
                  if item["id"] == "qwen3.8-27b-bf16")
    assert server["fits"]  # 81559 MiB is an "80 GB" card


def test_downloads_resume_fall_back_and_keep_only_verified_files(tmp_path, files):
    data = os.urandom(3 * (1 << 20) + 17)
    files.files["/m.bin"] = data
    target = tmp_path / "w" / "m.bin"
    target.parent.mkdir()
    part = target.with_name(f"m.bin.{sha(data)[:16]}.part")
    part.write_bytes(data[:1000])  # an earlier, interrupted download
    (target.parent / "m.bin.0123456789abcdef.part").write_bytes(b"for an older version")
    seen = []
    download([files.url + "/fail/m.bin", files.url + "/m.bin"], target, size=len(data), sha256=sha(data), progress=seen.append)
    assert target.read_bytes() == data and files.ranges == [1000] and seen[-1] == len(data)
    assert list(target.parent.glob("*.part")) == []  # the stale partial file of another version is gone too
    with pytest.raises(ProjectError, match="SHA-256 mismatch"):
        download([files.url + "/m.bin"], tmp_path / "w" / "bad.bin", size=len(data), sha256="0" * 64)
    assert not (tmp_path / "w" / "bad.bin").exists() and list((tmp_path / "w").glob("bad.bin*")) == []
    with pytest.raises(ProjectError, match="failed"):
        download([files.url + "/fail/nothing"], tmp_path / "w" / "none.bin", size=1, sha256="0" * 64)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(local_module._Cancelled):
        download([files.url + "/m.bin"], tmp_path / "w" / "c.bin", size=len(data), sha256=sha(data), cancel=cancel)


def test_an_interrupted_download_keeps_its_bytes_and_the_next_source_resumes(tmp_path, files):
    data = os.urandom(2 * (1 << 20) + 5)
    files.files["/m.bin"] = data
    target = tmp_path / "m.bin"
    # A source that closes cleanly after 1 MiB (Content-Length set), then one cut off mid-chunk, then a good one.
    download([f"{files.url}/short:{1 << 20}/m.bin", f"{files.url}/chunked/m.bin", f"{files.url}/m.bin"], target,
             size=len(data), sha256=sha(data))
    assert target.read_bytes() == data
    assert files.ranges and files.ranges[0] == 1 << 20  # resumed where the first source stopped
    # A server that ignores Range sends the whole file again, which replaces the partial bytes.
    files.honour_ranges = False
    other = tmp_path / "again.bin"
    other.with_name(f"again.bin.{sha(data)[:16]}.part").write_bytes(data[:5000])
    files.files["/again.bin"] = data
    download([f"{files.url}/again.bin"], other, size=len(data), sha256=sha(data))
    assert other.read_bytes() == data


def test_bad_resumed_bytes_are_dropped_and_fetched_again(tmp_path, files):
    data = os.urandom(1 << 20)
    files.files["/m.bin"] = data
    target = tmp_path / "m.bin"
    target.with_name(f"m.bin.{sha(data)[:16]}.part").write_bytes(b"x" * 1000)  # corrupt partial bytes
    download([files.url + "/m.bin"], target, size=len(data), sha256=sha(data))
    assert target.read_bytes() == data and files.requests.count("/m.bin") == 2


def test_runtime_archives_cannot_write_outside_their_folder(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../../escape.txt", "x")
    with pytest.raises(ProjectError, match="unsafe path"):
        _extract(archive, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()
    for kind in ("symlink", "hardlink"):
        archive = tmp_path / f"evil-{kind}.tar"
        with tarfile.open(archive, "w") as bundle:
            link = tarfile.TarInfo("bin/link")
            link.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
            link.linkname = "/etc/passwd" if kind == "symlink" else "../../outside"
            bundle.addfile(link)
            payload = tarfile.TarInfo("bin/link")
            payload.size = 1
            bundle.addfile(payload, io.BytesIO(b"x"))
        with pytest.raises(ProjectError):
            _extract(archive, tmp_path / f"out-{kind}")
        assert not (tmp_path / "outside").exists()
    good = tmp_path / "good.tar"
    with tarfile.open(good, "w") as bundle:
        info = tarfile.TarInfo("build/bin/llama-server")
        info.size, info.mode = 3, 0o755
        bundle.addfile(info, io.BytesIO(b"bin"))
    _extract(good, tmp_path / "ok")
    assert (tmp_path / "ok" / "build" / "bin" / "llama-server").read_bytes() == b"bin"


def test_endpoint_ids_follow_the_endpoint_rules():
    assert endpoint_id("qwen3-8b-q4_k_m") == "local-qwen3-8b-q4-k-m"
    long = endpoint_id("deepseek-r1-distill-qwen-32b-instruct-q8_0")
    assert long.startswith("local-") and len(long) <= 32
    assert endpoint_id("deepseek-r1-distill-qwen-32b-instruct-q4") != long


def server_env(monkeypatch, catalog):
    monkeypatch.setenv("STK_MODEL_CATALOG", str(catalog))
    monkeypatch.setenv("STK_LLAMA_SERVER", json.dumps([sys.executable, str(FAKE_SERVER)]))
    monkeypatch.setattr(local_module, "HEALTH_TIMEOUT_SECONDS", 30)


def make(state, managers, events=None):
    local = LocalModels(state, Endpoints(state), ModelPolicy(state),
                        emit=(lambda name, data: events.append((name, data))) if events is not None else None)
    managers.append(local)
    return local


def test_install_start_and_ask_a_local_model_through_the_service(inproc, model, files, tmp_path, monkeypatch):
    server_env(monkeypatch, write_catalog(tmp_path, files))
    monkeypatch.setenv("STK_TOKEN_PLAN_API_KEY", "")  # present, even empty: must not reach the model server
    monkeypatch.setenv("STK_MODEL_KEY_ELSEWHERE", "abcdefghijklmnopqrstu")
    monkeypatch.setenv("STK_MODEL_KEY_LOCAL_TINY_Q4", "abcdefghijklmnopqrstu")  # STK's own key for its server still wins
    h = inproc()
    store, _ = model
    operations = set(h.call("script.catalog")["operations"])
    assert "models.local.list" in operations
    assert not {"models.local.install", "models.local.start", "models.local.import", "models.local.remove"} & operations
    recommended = h.call("models.local.recommendations", {})
    assert [item["id"] for item in recommended["entries"] if item["recommended"]] == ["tiny-q4"]
    local = h.bridge.projects.local
    local.install("tiny-q4", wait=True)
    listed = h.call("models.local.list", {})
    assert listed["jobs"]["tiny-q4"]["state"] == "done", listed
    assert listed["installed"][0]["id"] == "tiny-q4" and listed["installed"][0]["server"] == {"state": "stopped"}
    assert Path(listed["runtimes"]["llama.cpp"]["binary"]).name.startswith("llama-server")
    # A question to the local endpoint is refused until its server runs.
    context = capture(model)
    message = store.discussion.add("Why do domains form?", message_id=str(uuid4()), context_id=context["id"])
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    project = Project(lambda method, params: h.call(method, params), handle)
    local.endpoints.add("local-tiny-q4", "Tiny chat", "http://127.0.0.1:9/v1", ["tiny-q4"])  # registered from an earlier run
    saved = project.requests.create(message["id"], request_id=str(uuid4()),
                                    configuration={"adapter": "openai-compatible/1:local-tiny-q4", "model": "tiny-q4"})
    with pytest.raises(Exception, match="not running"):
        project.requests.start(saved["id"])
    mark = h.mark()
    h.call("models.local.start", {"id": "tiny-q4"})
    h.wait_event(lambda e: e["event"] == "models.local.progress" and e["data"].get("stage") == "running", start=mark, timeout=30)
    endpoint = next(item for item in h.call("models.list", {})["endpoints"] if item["id"] == "local-tiny-q4")
    assert endpoint["location"] == "local" and endpoint["models"] == ["tiny-q4"] and endpoint["base_url"] != "http://127.0.0.1:9/v1"
    args = json.loads((local.root / "weights" / "tiny-q4" / "model.gguf.args.json").read_text())
    assert args[args.index("--host") + 1] == "127.0.0.1" and "--jinja" in args and args[args.index("--alias") + 1] == "tiny-q4"
    # The server needs a key (given by environment, never on the command line) and does not expose its prompts (slots).
    key = local.keys.get("local-tiny-q4")
    assert len(key) >= 40 and key not in json.dumps(args) and "--no-slots" in args
    assert args[args.index("--reasoning") + 1] == "off"  # as the Token Plan: answers without minutes of hidden thinking
    assert key not in json.dumps(h.call("models.list", {})) and key not in json.dumps(h.call("models.local.list", {}))
    # The server gets its own key, not this service's secrets.
    environment = json.loads((local.root / "weights" / "tiny-q4" / "model.gguf.env.json").read_text())
    assert environment["LLAMA_API_KEY"] == key and "STK_TOKEN_PLAN_API_KEY" not in environment
    assert "STK_MODEL_KEY_ELSEWHERE" not in environment and "PATH" in environment
    # Its key is managed by STK: it cannot be cleared or replaced, and the endpoint goes with the model.
    assert endpoint["managed"] is True
    for method, params in (("models.keys.clear", {"id": "local-tiny-q4"}),
                           ("models.keys.set", {"id": "local-tiny-q4", "key": "abcdefghijklmnopqrstu"}),
                           ("models.endpoints.remove", {"id": "local-tiny-q4"})):
        with pytest.raises(Exception, match="belongs to a local model"):
            h.call(method, params)
    assert local.keys.get("local-tiny-q4") == key and local.keys.info("local-tiny-q4")["source"] == "managed"
    with pytest.raises(Exception, match="kept for local models"):
        h.call("models.endpoints.add", {"id": "local-other", "name": "Other", "base_url": "http://127.0.0.1:9/v1", "models": ["m"]})
    # Private data may go to a model on this computer, even offline.
    h.call("models.policy.set", {"network": "offline"})
    project.requests.start(saved["id"])
    eventually(lambda: store.requests.get(saved["id"])["status"] == "completed", timeout=30)
    reply = store.discussion.get(store.requests.get(saved["id"])["assistant_message_id"])
    assert reply["text"] == "Domain walls move under the applied field."
    # Stopping keeps the files and no longer starts the server with the service.
    listed = h.call("models.local.stop", {"id": "tiny-q4"})
    assert listed["installed"][0]["server"] == {"state": "stopped"} and listed["installed"][0]["autostart"] is False
    assert local.keys.info("local-tiny-q4")["source"] == "environment"  # STK's key is gone with its server
    assert not h.violations


def test_cancelled_installs_keep_their_bytes_and_resume(tmp_path, files, monkeypatch, managers):
    weights = os.urandom(3 << 20)
    server_env(monkeypatch, write_catalog(tmp_path, files, weights=weights))
    local = make(tmp_path / "state", managers)
    gate = threading.Event()
    original = local_module.download

    def slow(urls, target, **kwargs):  # cancel once the first MiB of the weights arrived
        if target.name == "model.gguf":
            progress = kwargs["progress"]

            def seen(done):
                progress(done)
                if done >= 1 << 20:
                    local.cancel("tiny-q4")
                    gate.set()
            kwargs["progress"] = seen
        return original(urls, target, **kwargs)

    monkeypatch.setattr(local_module, "download", slow)
    monkeypatch.setattr(local_module, "CHUNK", 1 << 18)
    local.install("tiny-q4", wait=True)
    assert gate.is_set() and local.list()["jobs"]["tiny-q4"]["state"] == "cancelled"
    assert local.list()["installed"] == [] and list((local.root / "weights" / "tiny-q4").glob("*.part"))
    monkeypatch.setattr(local_module, "download", original)
    files.ranges.clear()
    local.install("tiny-q4", wait=True)
    assert local.list()["jobs"]["tiny-q4"]["state"] == "done" and files.ranges and files.ranges[0] >= 1 << 20


def test_installs_of_two_entries_share_one_runtime_download(tmp_path, files, monkeypatch, managers):
    second = {"id": "other-q4", "model": "Other", "params_b": 1, "tier": "tiny", "runtime": "llama.cpp", "quantization": "Q4_K_M",
              "files": [{"name": "other.gguf", "size_bytes": 64, "sha256": sha(b"o" * 64)}], "total_bytes": 64, "min_memory_gb": 0.001,
              "sources": [{"name": "mirror", "url": files.url + "/weights/{file}"}]}
    files.files["/weights/other.gguf"] = b"o" * 64
    server_env(monkeypatch, write_catalog(tmp_path, files, extra_entries=[second]))
    local = make(tmp_path / "state", managers)
    local.install("tiny-q4")
    local.install("other-q4")
    eventually(lambda: all(job["state"] != "running" for job in local.list()["jobs"].values()) and len(local.list()["jobs"]) == 2,
               timeout=30)
    assert {key: job["state"] for key, job in local.list()["jobs"].items()} == {"tiny-q4": "done", "other-q4": "done"}
    assert files.requests.count("/runtime.zip") == 1


def test_leaving_the_internet_setting_cancels_running_downloads(inproc, tmp_path, files, monkeypatch):
    server_env(monkeypatch, write_catalog(tmp_path, files, weights=os.urandom(4 << 20)))
    h = inproc()
    local = h.bridge.projects.local
    started = threading.Event()
    original = local_module.download

    def held(urls, target, **kwargs):
        if target.name == "model.gguf":
            started.set()
            cancel = kwargs["cancel"]
            assert cancel.wait(10), "the network change did not cancel the download"
            raise local_module._Cancelled()
        return original(urls, target, **kwargs)

    monkeypatch.setattr(local_module, "download", held)
    h.call("models.local.install", {"id": "tiny-q4"})
    assert started.wait(10)
    h.call("models.policy.set", {"network": "organization"})
    eventually(lambda: local.list()["jobs"]["tiny-q4"]["state"] == "cancelled", timeout=10)
    with pytest.raises(Exception, match="internet"):
        h.call("models.local.install", {"id": "tiny-q4"})
    assert not h.violations


def test_offline_import_installs_the_model_and_the_runtime(tmp_path, files, monkeypatch, managers):
    weights = b"offline weights " * 32
    server_env(monkeypatch, write_catalog(tmp_path, files, weights=weights))
    local = make(tmp_path / "state", managers)
    local.policy.set("offline")
    with pytest.raises(ProjectError, match="internet"):
        local.install("tiny-q4")
    usb = tmp_path / "usb"
    usb.mkdir()
    (usb / "model.gguf").write_bytes(weights)
    with pytest.raises(ProjectError, match="runtime.zip"):  # no runtime yet and none copied along
        local.import_file("tiny-q4", usb)
    (usb / "runtime.zip").write_bytes(runtime_zip())
    (usb / "model.gguf").write_bytes(weights[:-1] + b"!")
    unpack = local_module._extract

    def unpack_while_the_setting_changes(archive, folder):
        local.cancel_downloads()  # leaving the internet setting stops downloads, not an import
        unpack(archive, folder)
    monkeypatch.setattr(local_module, "_extract", unpack_while_the_setting_changes)
    local.import_file("tiny-q4", usb, wait=True)  # the runtime is installed, then the weights are checked (and wrong)
    assert local.list()["jobs"]["tiny-q4"]["state"] == "failed" and "does not match" in local.list()["jobs"]["tiny-q4"]["error"]
    assert local.list()["installed"] == [] and not (local.root / "weights" / "tiny-q4" / "model.gguf").exists()
    (usb / "model.gguf").write_bytes(weights)
    local.import_file("tiny-q4", usb, wait=True)
    assert local.list()["jobs"]["tiny-q4"]["state"] == "done"
    assert (local.root / "weights" / "tiny-q4" / "model.gguf").read_bytes() == weights
    assert Path(local.list()["runtimes"]["llama.cpp"]["binary"]).exists()  # the runtime came from the copied archive
    with pytest.raises(ProjectError, match="No catalog entry"):
        local.import_file("unknown", usb)


def test_servers_that_fail_or_exit_are_reported_and_not_relaunched(tmp_path, files, monkeypatch, managers):
    server_env(monkeypatch, write_catalog(tmp_path, files, name="fail-model.gguf"))
    events = []
    local = make(tmp_path / "a", managers, events)
    local.install("tiny-q4", wait=True)
    local.start("tiny-q4", wait=True)
    assert local.list()["installed"][0]["server"] == {"state": "failed", "port": local._servers["tiny-q4"]["port"],
                                                       "error": "the server exited"}
    assert local.list()["installed"][0]["autostart"] is False
    assert any(name == "models.local.progress" and data.get("error") == "the server exited" for name, data in events)
    assert local.endpoints.get("local-tiny-q4") is None
    # A server that becomes healthy and then exits by itself is reported, and no longer admitted.
    (tmp_path / "b").mkdir()
    server_env(monkeypatch, write_catalog(tmp_path / "b", files, name="die-model.gguf"))
    local = make(tmp_path / "b" / "state", managers)
    local.install("tiny-q4", wait=True)
    local.start("tiny-q4", wait=True)
    assert local.is_running("local-tiny-q4")
    eventually(lambda: local.list()["installed"][0]["server"]["state"] == "failed", timeout=15)
    assert not local.is_running("local-tiny-q4") and "exited" in local.list()["installed"][0]["server"]["error"]
    assert local.list()["installed"][0]["autostart"] is False


def test_stopping_during_startup_is_not_a_failure(tmp_path, files, monkeypatch, managers):
    server_env(monkeypatch, write_catalog(tmp_path, files))
    events = []
    local = make(tmp_path / "state", managers, events)
    local.install("tiny-q4", wait=True)
    local.start("tiny-q4")  # returns while the server is still starting
    local.stop("tiny-q4")
    time.sleep(1)
    assert local.list()["installed"][0]["server"] == {"state": "stopped"}
    assert not any(data.get("state") == "failed" for _, data in events)


def test_servers_stop_with_the_service_and_start_again_with_the_next(tmp_path, files, monkeypatch, managers):
    server_env(monkeypatch, write_catalog(tmp_path, files))
    state = tmp_path / "state"
    first = make(state, managers)
    first.install("tiny-q4", wait=True)
    first.start("tiny-q4", wait=True)
    process = first._servers["tiny-q4"]["process"]
    first.shutdown()
    assert process.poll() is not None and first.list()["installed"][0]["autostart"] is True
    second = make(state, managers)
    second.autostart()
    eventually(lambda: second.list()["installed"][0]["server"]["state"] == "running", timeout=30)
    # A service killed alone leaves its server running; the next service stops it before starting its own. (The killed
    # service's memory and threads are gone with it: its supervisor must not report the reaped server.)
    leftover = second._servers.pop("tiny-q4")["process"]
    third = make(state, managers)
    assert leftover.wait(10) is not None  # stopped by the new service
    third.autostart()
    eventually(lambda: third.list()["installed"][0]["server"]["state"] == "running", timeout=30)
    third.shutdown()
    # A model that cannot even be started (its runtime is gone) is not tried again at every start.
    monkeypatch.setenv("STK_LLAMA_SERVER", str(tmp_path / "missing" / "llama-server"))
    fourth = make(state, managers)
    fourth.autostart()
    assert fourth.list()["installed"][0]["server"]["state"] == "failed"
    assert fourth.list()["installed"][0]["autostart"] is False
    fourth.remove("tiny-q4")
    assert fourth.list()["installed"] == [] and not (fourth.root / "weights" / "tiny-q4").exists()
    assert Endpoints(state).get("local-tiny-q4") is None
