#!/usr/bin/env python3
"""Explicit, local developer-tool entry points; never runs a model or product task."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SERENA_VERSION = "2.1.0"


def run(argv, *, cwd=ROOT):
    return subprocess.call(argv, cwd=cwd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install-serena", "install-checks", "configure-codex", "compile-db", "mcp", "index", "health", "duplicates", "knip-web", "knip-docs"])
    parser.add_argument("--build-dir", type=Path)
    args = parser.parse_args()
    # Product model credentials/settings are unnecessary for all these operations.
    os.environ["STK_TOKEN_PLAN_API_KEY"] = ""
    os.environ.pop("STK_TOKEN_PLAN_MODEL", None)
    os.environ["SERENA_USAGE_REPORTING"] = "false"
    if args.action == "install-serena":
        return run(["uv", "tool", "install", "--python", "3.13", f"serena-agent=={SERENA_VERSION}"])
    if args.action == "install-checks":
        return run(["npm", "ci", "--no-audit", "--no-fund"], cwd=ROOT / "tools/ai")
    if args.action == "compile-db":
        if not args.build_dir:
            parser.error("compile-db requires --build-dir from a configured local CMake build")
        source = args.build_dir.resolve() / "compile_commands.json"
        rows = json.loads(source.read_text())
        target = ROOT / "desktop/engine/lib/stk_app/src/editors/analysis_graph_editor.cc"
        if not any((Path(row["directory"]) / row["file"]).resolve() == target for row in rows):
            parser.error("compilation database does not cover this checkout's analysis editor")
        destination = ROOT / "compile_commands.json"
        if destination.exists() or destination.is_symlink():
            if destination.resolve() == source or destination.read_bytes() == source.read_bytes():
                print("Compilation database already bound")
                return 0
            parser.error("existing compilation database differs; inspect it before replacing")
        # Copy works on platforms where unprivileged symlinks are unavailable.
        shutil.copyfile(source, destination)
        print(f"Copied {len(rows)} compilation commands; refresh explicitly after CMake changes")
        return 0
    serena = shutil.which("serena")
    if args.action in {"configure-codex", "mcp", "index", "health"} and not serena:
        parser.error("Serena missing; run install-serena first")
    if args.action == "configure-codex":
        path = ROOT / ".codex/config.toml"
        config = ('# Generated local paths; rerun after moving this checkout.\n'
                  '[mcp_servers.serena]\n'
                  f'command = {json.dumps(serena)}\n'
                  f'cwd = {json.dumps(str(ROOT))}\n'
                  'args = ["start-mcp-server", "--context", "ide", "--project-from-cwd", "--enable-web-dashboard", "false", "--open-web-dashboard", "false", "--log-level", "WARNING"]\n'
                  'startup_timeout_sec = 180\ntool_timeout_sec = 120\n'
                  '[mcp_servers.serena.env]\nSERENA_USAGE_REPORTING = "false"\nSTK_TOKEN_PLAN_API_KEY = ""\n')
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            # Do not inspect or overwrite an existing potentially private config.
            parser.error(f"{path} exists; merge the documented Serena section manually")
        with path.open("x") as handle:
            handle.write(config)
        print("Created project-scoped Codex MCP configuration")
        return 0
    if args.action == "mcp":
        return run([serena, "start-mcp-server", "--context", "ide", "--project", str(ROOT), "--enable-web-dashboard", "false", "--open-web-dashboard", "false", "--log-level", "WARNING"])
    if args.action in {"index", "health"}:
        command = "index" if args.action == "index" else "health-check"
        return run([serena, "project", command, str(ROOT)])
    binary = "jscpd" if args.action == "duplicates" else "knip"
    executable = ROOT / "tools/ai/node_modules/.bin" / (binary + (".cmd" if os.name == "nt" else ""))
    if not executable.exists():
        parser.error("Check tools missing; run install-checks first")
    if args.action == "duplicates":
        return run([str(executable), "--config", "tools/ai/jscpd.json",
                    "--output", str(ROOT / ".ai-tools/reports/duplicates"), "--fail-on-empty"])
    workspace = "web" if args.action == "knip-web" else "docs"
    command = [str(executable), "--reporter", "json", "--no-progress"]
    if workspace == "web":
        command += ["--config", str(ROOT / "tools/ai/knip-web.json")]
    return run(command, cwd=ROOT / workspace)


if __name__ == "__main__":
    sys.exit(main())
