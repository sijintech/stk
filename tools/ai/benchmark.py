#!/usr/bin/env python3
"""Measure three local navigation cases; requires the pinned Serena environment.

Reports UTF-8 output bytes and elapsed time, never estimates model token savings.
The bounded source ranges are deliberately explicit; review them after source edits.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".ai-tools/reports/navigation"
CASES = [
    ("python", "TaskSpec/to_dict", "suan/runtime/models.py", 121, 126,
     ["rg", "-n", r"\.to_dict\(", "suan", "tests", "examples", "toolkits", "plugins",
      "-g", "*.py", "-g", "!**/pyqode/**", "-g", "!*_rc.py"]),
    ("cpp", "stk/app/AnalysisParameterDraft::undo",
     "desktop/engine/lib/stk_app/src/analysis_parameter_draft.cc", 790, 793,
     ["rg", "-n", r"\.undo\(", "desktop/engine/lib/stk_app/src", "desktop/tests/app",
      "-g", "analysis*", "-g", "!analysis_document*"]),
    ("typescript", "cameraSignature", "web/src/camera.ts", 37, 42,
     ["rg", "-n", "cameraSignature", "web/src", "web/tests"]),
]


def shell(argv):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Command failed: {argv!r}; inspect paths before benchmarking")
    return result.stdout


def response_text(result):
    return "\n".join(block.text for block in result.content if block.type == "text")


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    executable = shutil.which("serena")
    if not executable:
        raise RuntimeError("Install serena-agent==2.1.0 first")
    # Do not inherit provider credentials or product model selection.
    env = {key: os.environ[key] for key in ("HOME", "PATH", "LANG", "SYSTEMROOT", "TEMP", "TMP")
           if key in os.environ}
    env.update(STK_TOKEN_PLAN_API_KEY="", SERENA_USAGE_REPORTING="false")
    params = StdioServerParameters(command=executable, cwd=str(ROOT), env=env, args=[
        "start-mcp-server", "--context", "ide", "--project-from-cwd",
        "--enable-web-dashboard", "false", "--open-web-dashboard", "false",
        "--log-level", "WARNING"])
    report = {"serena_version": "2.1.0", "cases": [], "units": "UTF-8 bytes, seconds",
              "scope": "Three known-file definitions and language-server references; warm disk caches, one sample each"}
    started = time.perf_counter()
    with (OUT / "stderr.log").open("w") as log:
        async with stdio_client(params, errlog=log) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                report["initialize_seconds"] = time.perf_counter() - started
                available = await session.list_tools()
                report["tool_names"] = [tool.name for tool in available.tools]
                report["tool_schema_json_bytes"] = len(available.model_dump_json().encode())
                instructions = await session.call_tool("initial_instructions", {})
                report["initial_instructions_text_bytes"] = len(response_text(instructions).encode())
                for language, name, path, first, last, references in CASES:
                    t = time.perf_counter()
                    located = shell(["rg", "-n", "-F", name.split("/")[-1], path])
                    lines = (ROOT / path).read_text().splitlines()
                    body = "\n".join(lines[first - 1:last])
                    bounded = "\n".join(f"{i + first}: {line}" for i, line in enumerate(lines[first - 1:last]))
                    refs = shell(references)
                    baseline = located + b"\n" + bounded.encode() + b"\n" + refs
                    baseline_seconds = time.perf_counter() - t
                    (OUT / f"{language}-rg.txt").write_bytes(baseline)
                    t = time.perf_counter()
                    definition = await session.call_tool("find_symbol", {
                        "name_path_pattern": name, "relative_path": path, "include_body": True,
                        "max_matches": 1, "max_answer_chars": 16000})
                    definition_seconds = time.perf_counter() - t
                    t = time.perf_counter()
                    # clangd uses different name paths for an out-of-class definition
                    # and its declaration. Query references at the declaration.
                    reference_path = path
                    reference_name = name
                    if language == "cpp":
                        reference_path = "desktop/engine/lib/stk_app/include/stk/app/analysis_parameter_draft.hh"
                        reference_name = "stk/app/AnalysisParameterDraft/undo"
                    reference_result = await session.call_tool("find_referencing_symbols", {
                        "name_path": reference_name, "relative_path": reference_path, "max_answer_chars": 32000})
                    reference_seconds = time.perf_counter() - t
                    definition_text = response_text(definition)
                    reference_text = response_text(reference_result)
                    (OUT / f"{language}-definition.json").write_text(definition.model_dump_json(indent=2))
                    (OUT / f"{language}-references.json").write_text(reference_result.model_dump_json(indent=2))
                    try:
                        symbols = json.loads(definition_text)
                        match = len(symbols) == 1 and symbols[0]["body"].strip() == body.strip()
                    except (ValueError, TypeError, KeyError):
                        match = False
                    report["cases"].append({
                        "language": language, "symbol": name, "file": path,
                        "source_file_bytes": (ROOT / path).stat().st_size,
                        "body_matches_explicit_source_range": match,
                        "rg_commands": 2, "bounded_reads": 1, "serena_queries": 2,
                        "rg_output_bytes": len(baseline), "rg_seconds": baseline_seconds,
                        "rg_definition_bytes": len(located + b"\n" + bounded.encode()),
                        "rg_reference_bytes": len(refs),
                        "serena_definition_bytes": len(definition_text.encode()),
                        "serena_reference_bytes": len(reference_text.encode()),
                        "serena_envelope_bytes": sum(len(r.model_dump_json().encode()) for r in (definition, reference_result)),
                        "serena_definition_seconds": definition_seconds,
                        "serena_reference_seconds": reference_seconds,
                        "tool_error": bool(definition.is_error or reference_result.is_error),
                        "references_nonempty": reference_text not in ("{}", "[]", ""),
                        "reference_query_file": reference_path,
                        "reference_review": "Manual review required: text matches and LSP references have different scope"})
    (OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if all(c["body_matches_explicit_source_range"] and c["references_nonempty"]
                    and not c["tool_error"] for c in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
