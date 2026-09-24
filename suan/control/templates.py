"""Built-in and operator-registered exact command templates; clients cannot pass parameters."""
import copy
import json
from pathlib import Path
import re

from suan.runtime.models import TaskSpec
from .policy import DEMO_TEMPLATE

TEMPLATE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
TEMPLATE_KEYS = frozenset({"argv", "outputs", "resources", "backend", "inputs"})
# What suan.mupro.muferro_spec builds for the SDK example: one rank with one thread, so the
# worker also records and pins the MPI thread settings.
MUFERRO_EXAMPLE_TEMPLATE = {"argv": ["{python}", "-m", "suan.mupro", "run", "--ranks", "{ranks}", "--threads-per-rank",
                                     "{threads_per_rank}", "--example"], "inputs": [], "outputs": ["stk-mupro.json"],
                            "resources": {"ranks": 1, "threads_per_rank": 1, "walltime_seconds": 600, "memory_mb": 4096}}
BUILTIN_TEMPLATES = {"demo-field": DEMO_TEMPLATE, "muferro-example": MUFERRO_EXAMPLE_TEMPLATE}


def validate_template(identity, template):
    if not TEMPLATE_ID.fullmatch(identity):
        raise ValueError(f"Invalid template ID {identity!r}: use 1-64 of a-z, 0-9, '.', '_' or '-', starting with a-z or 0-9")
    if not isinstance(template, dict) or "argv" not in template:
        raise ValueError(f"Template {identity} must be an object with argv")
    if "env" in template:
        raise ValueError(f"Template {identity} must not set env; environment changes always require review")
    if set(template) - TEMPLATE_KEYS:
        raise ValueError(f"Template {identity} allows only " + ", ".join(sorted(TEMPLATE_KEYS)))
    try:
        spec = TaskSpec(**template, workspace_id="0"*32, name=identity)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid template {identity}: {exc}") from exc
    # Clusters bill core-hours, and a partition's default limit may be unlimited.
    if spec.backend != "local" and "walltime_seconds" not in spec.resources:
        raise ValueError(f"Cluster template {identity} must set resources.walltime_seconds")


def unique_keys(pairs):
    # json.loads would otherwise keep only the last of two repeated template IDs or template keys.
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f"Duplicate key in template file: {key}")
        data[key] = value
    return data


def load_templates(names=(), files=()):
    templates = {}
    for name in dict.fromkeys(names):
        if name not in BUILTIN_TEMPLATES:
            raise ValueError(f"Unknown built-in template: {name}")
        templates[name] = copy.deepcopy(BUILTIN_TEMPLATES[name])
    for file in files:
        data = json.loads(Path(file).read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
        if not isinstance(data, dict):
            raise ValueError(f"{file} must hold a JSON object mapping template IDs to templates")
        for identity, template in data.items():
            validate_template(identity, template)
            if identity in templates:
                raise ValueError(f"Duplicate template ID: {identity}")
            templates[identity] = template
    return templates
