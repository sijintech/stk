"""Launch the compiled STK Blender distribution and its private network bridge."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from suan.control.templates import TEMPLATE_ID
from suan.runtime.common import atomic_json, instance_lock, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default=os.environ.get("STK_BLENDER", "blender"))
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".suan" / "blender")
    parser.add_argument("--url", help="HTTPS control origin (loopback HTTP is allowed)")
    parser.add_argument("--template", metavar="ID", help="Control template submitted by the workbench run button")
    parser.add_argument("--demo", action="store_true", help="Load a clearly labelled local demonstration surface")
    parser.add_argument("--scene", type=Path, help="Open a version-1 scientific display scene")
    parser.add_argument("blender_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.template is not None and not TEMPLATE_ID.fullmatch(args.template):
        parser.error("--template must be a control template ID (1-64 of a-z, 0-9, '.', '_' or '-', starting with a-z or 0-9)")
    binary = shutil.which(args.blender)
    if binary is None:
        parser.error("STK Blender executable not found; build blender/ first or pass --blender")
    root = args.state_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with instance_lock(root / "launcher.lock"):
            if args.url:
                from suan.control.agent import endpoint
                from .bridge import DEFAULT_CONTROL_URL
                config = read_json(root / "client.json", {})
                url = endpoint(args.url)
                # Without a url the bridge already uses the default service, so that is no change.
                if config.get("url", DEFAULT_CONTROL_URL) != url:
                    # A paired credential must never travel to a new service.
                    config = {"url": url, "token": ""}
                atomic_json(root / "client.json", {"url": url, "token": "", **config})
            if args.template:
                atomic_json(root / "client.json", {**read_json(root / "client.json", {}), "template": args.template})
            if args.demo or args.scene:
                from .scene import demo_scene, validate_scene
                scene = read_json(args.scene) if args.scene else demo_scene()
                atomic_json(root / "scene.json", validate_scene(scene))
            env = {**os.environ, "STK_BLENDER_STATE_DIR": str(root)}
            bridge = subprocess.Popen([sys.executable, "-m", "suan.blender_client.bridge",
                                       "--state-dir", str(root)], env=env)
            try:
                extra = args.blender_args
                if extra[:1] == ["--"]:
                    extra = extra[1:]
                return subprocess.call([binary, "--factory-startup", "--app-template", "STK", *extra], env=env)
            finally:
                # Runtime/node/control services have separate owners. Closing
                # the GUI only stops this launcher's bridge process.
                bridge.terminate()
                try:
                    bridge.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    bridge.kill()
                    bridge.wait()
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    sys.exit(main())
