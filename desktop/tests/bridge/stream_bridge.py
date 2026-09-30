"""Test-only real bridge with a file-controlled, network-free streaming adapter.

This script is launched explicitly by native integration tests; production never
imports it. Each marker is written after its corresponding delta was delivered.
"""

import sys
import time
from pathlib import Path

from suan.desktop_bridge import projects
from suan.desktop_bridge.__main__ import main
from suan.project.request_executor import TextResponse


control = Path(sys.argv.pop(1))
legacy = sys.argv.pop(1) == "legacy"


class ControlledAdapter:
    def send_stream(self, frozen_input, cancel, on_text):
        def wait(step):
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    if int((control / "advance").read_text()) >= step:
                        return
                except (FileNotFoundError, ValueError):
                    pass
                time.sleep(0.01)
            raise TimeoutError("Test did not release the stream")

        prefix_file = control / "prefix.txt"
        prefix = prefix_file.read_text(encoding="utf-8") if prefix_file.exists() else "温度 "
        on_text(prefix)
        (control / "first").touch()
        wait(1)
        on_text("300")
        (control / "second").touch()
        wait(2)
        on_text(" K。")
        return TextResponse(prefix + "300 K。")


projects.AliyunTokenPlanAdapter = ControlledAdapter
original_provider = projects.provider_info
projects.provider_info = lambda: {**original_provider(), "configured": True}

if legacy:
    from suan.desktop_bridge import server

    original_init = server.Bridge.__init__

    def legacy_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        del self.methods["project.requests.progress"]

    server.Bridge.__init__ = legacy_init

main()
