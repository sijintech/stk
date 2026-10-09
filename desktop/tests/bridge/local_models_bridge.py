"""Test-only real bridge for local models: a one-entry catalog served by an in-process HTTP server and
tests/fake_llama_server.py as llama-server. Production never imports it; nothing reaches the internet."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))

from suan.desktop_bridge.__main__ import main  # noqa: E402
from local_models_fixture import FAKE_SERVER, Files, sha, write_catalog  # noqa: E402

work = Path(sys.argv.pop(1))
files = Files()
# A second model whose server exits at once ("fail" in its file name; see fake_llama_server.py).
broken = b"GGUF broken weights " * 64
files.files["/weights/fail-model.gguf"] = broken
broken_entry = {"id": "broken-q4", "model": "Broken chat", "params_b": 1.5, "tier": "tiny", "runtime": "llama.cpp",
                "quantization": "Q4_K_M", "files": [{"name": "fail-model.gguf", "size_bytes": len(broken), "sha256": sha(broken)}],
                "total_bytes": len(broken), "min_memory_gb": 0.001, "context_length": 32768, "serve_context": 4096,
                "license": "Apache-2.0", "license_url": "https://example.invalid/LICENSE", "commercial_use": "yes",
                "sources": [{"name": "mirror", "url": files.url + "/weights/{file}"}], "notes": "", "recommend_on": []}
os.environ["STK_MODEL_CATALOG"] = str(write_catalog(work, files, extra_entries=[broken_entry]))
os.environ["STK_LLAMA_SERVER"] = json.dumps([sys.executable, str(FAKE_SERVER)])
main()
