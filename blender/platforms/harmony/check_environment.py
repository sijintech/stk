#!/usr/bin/env python3
"""Report Harmony build prerequisites without claiming platform compatibility."""
import json
import os
from pathlib import Path
import shutil


def check():
    paths = {name: os.environ.get(name, "") for name in ("OHOS_SDK_HOME", "DEVECO_SDK_HOME", "HOS_SDK_HOME")}
    sdks = {name: value for name, value in paths.items() if value and Path(value).is_dir()}
    tools = {name: shutil.which(name) for name in ("hdc", "hvigor", "hvigorw", "ohpm")}
    return {"sdk_paths": sdks, "tools": tools, "sdk_available": bool(sdks),
            "blender_ghost_ohos_implemented": False, "simulator_verified": False,
            "hardware_verified": False, "release_ready": False}


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False, indent=2))
