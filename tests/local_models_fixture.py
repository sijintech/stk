"""Shared helpers for local model tests (no pytest import: the desktop's test bridge uses them too)."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import threading
import zipfile

from suan.models.local import platform_key

FAKE_SERVER = Path(__file__).with_name("fake_llama_server.py")


class Files:
    """Serves byte strings by path, honouring Range requests unless ``ranges`` is False. Paths containing ``fail`` answer
    500; ``short:<n>/<path>`` sends only n bytes of the file and closes; ``chunked/<path>`` sends a chunked body and stops
    in the middle."""

    def __init__(self):
        self.files, self.ranges, self.requests = {}, [], []
        self.honour_ranges = True
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                owner.requests.append(self.path)
                path, cut, chunked = self.path, None, False
                if path.startswith("/short:"):
                    cut, path = path[len("/short:"):].split("/", 1)
                    cut, path = int(cut), "/" + path
                elif path.startswith("/chunked/"):
                    chunked, path = True, path[len("/chunked"):]
                data = owner.files.get(path)
                if data is None:
                    self.send_response(500 if "fail" in path else 404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                start = 0
                if self.headers.get("Range") and owner.honour_ranges:
                    start = int(self.headers["Range"].split("=")[1].split("-")[0])
                    owner.ranges.append(start)
                    self.send_response(206)
                else:
                    self.send_response(200)
                body = data[start:]
                if chunked:
                    self.send_header("Transfer-Encoding", "chunked")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    half = body[: len(body) // 2]
                    self.wfile.write(f"{len(body):x}\r\n".encode() + half)  # announces the whole body, sends half
                    self.wfile.flush()
                    self.close_connection = True
                    return
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body if cut is None else body[:cut])
                self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def runtime_zip():
    archive = io.BytesIO()
    binary = "llama-server.exe" if os.name == "nt" else "llama-server"
    with zipfile.ZipFile(archive, "w") as bundle:
        info = zipfile.ZipInfo(f"build/bin/{binary}")
        info.external_attr = 0o755 << 16
        bundle.writestr(info, "#!/bin/sh\nexit 0\n")
    return archive.getvalue()


def write_catalog(folder, files, *, weights=b"GGUF fake weights " * 64, name="model.gguf", extra_entries=()):
    """A catalog served by ``files``: entry ``tiny-q4`` (plus ``extra_entries``) and a llama.cpp build for this platform."""
    files.files[f"/weights/{name}"] = weights
    runtime = runtime_zip()
    files.files["/runtime.zip"] = runtime
    entry = {"id": "tiny-q4", "model": "Tiny chat", "params_b": 1.5, "tier": "tiny", "runtime": "llama.cpp",
             "quantization": "Q4_K_M", "files": [{"name": name, "size_bytes": len(weights), "sha256": sha(weights)}],
             "total_bytes": len(weights), "min_memory_gb": 0.001, "context_length": 32768, "serve_context": 4096,
             "license": "Apache-2.0", "license_url": "https://example.invalid/LICENSE", "commercial_use": "yes",
             "sources": [{"name": "broken", "url": files.url + "/fail/{file}"},
                         {"name": "mirror", "url": files.url + "/weights/{file}"}], "notes": ""}
    catalog = {"format": "stk.model-catalog/1",
               "runtimes": {"llama.cpp": {"tag": "b9999", "assets": {platform_key(): {
                   "name": "runtime.zip", "size_bytes": len(runtime), "sha256": sha(runtime),
                   "urls": [files.url + "/fail/runtime.zip", files.url + "/runtime.zip"]}}}},
               "entries": [entry, *extra_entries]}
    path = Path(folder) / "catalog.json"
    path.write_text(json.dumps(catalog))
    return path
