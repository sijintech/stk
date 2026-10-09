"""Test-only real bridge for local models: a one-entry catalog served by an in-process HTTP server and
tests/fake_llama_server.py as llama-server. Production never imports it; nothing reaches the internet."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))

from suan.desktop_bridge.__main__ import main  # noqa: E402
from local_models_fixture import FAKE_SERVER, Files, write_catalog  # noqa: E402

work = Path(sys.argv.pop(1))
files = Files()
os.environ["STK_MODEL_CATALOG"] = str(write_catalog(work, files))
os.environ["STK_LLAMA_SERVER"] = json.dumps([sys.executable, str(FAKE_SERVER)])
main()
