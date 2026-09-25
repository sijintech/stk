"""Control-service approval policy; client-safe, needs no fastapi."""

import pytest

from suan.control.policy import DEMO_TEMPLATE, validate_action
from suan.control.templates import validate_template

WS = "a" * 32
EXAMPLE = {"argv": ["{python}", "-m", "suan.mupro", "run", "--example"], "inputs": [],
           "outputs": ["stk-mupro.json"], "resources": {"walltime_seconds": 600, "memory_mb": 4096}}
TEMPLATES = {"demo-field": DEMO_TEMPLATE, "example": EXAMPLE,
             "mpi-8": {**EXAMPLE, "resources": {"ranks": 2, "threads_per_rank": 4}},
             "mpi-9": {**EXAMPLE, "resources": {"ranks": 3, "threads_per_rank": 3}}}
REVIEW = "新命令或模板变更"
LIMIT = "资源请求超过"


def submit(spec, template=None):
    payload = {"spec": {"workspace_id": WS, **spec}}
    if template:
        payload["template"] = template
    return validate_action({"id": "b" * 32, "node_id": "c" * 32, "kind": "task.submit", "payload": payload}, TEMPLATES)


def test_exact_template_request_auto_queues():
    assert submit(EXAMPLE, "example") == ""
    # The shape prepare_action builds for a template-only request.
    assert submit({**EXAMPLE, "name": "example"}, "example") == ""


@pytest.mark.parametrize("change", [
    {"backend": "slurm", "resources": {**EXAMPLE["resources"], "queue": "q"}},
    {"inputs": ["input.toml"]},
    {"inputs": None},
    {"resources": {"walltime_seconds": 600}},
    {"env": {"MUPROROOT": "/elsewhere"}},
    {"argv": EXAMPLE["argv"] + ["--ranks", "2"]},
    {"outputs": []},
])
def test_any_template_change_goes_to_review(change):
    assert REVIEW in submit({**EXAMPLE, **change}, "example")


def test_mpi_cores_count_against_the_automatic_limit():
    assert submit(TEMPLATES["mpi-8"], "mpi-8") == ""
    assert LIMIT in submit(TEMPLATES["mpi-9"], "mpi-9")
    assert LIMIT in submit({"argv": ["mpiexec", "-n", "{ranks}", "muFerro"], "backend": "slurm",
                            "resources": {"ranks": 1024}})
    assert LIMIT in submit({"argv": ["x"], "resources": {"cpus": 9}})


def test_web_demo_request_still_auto_queues():
    # web/src/main.tsx sends the template plus a spec without backend/resources/inputs.
    spec = {"name": "解析场验证", "argv": ["@python", "-m", "suan.control.demo_job"],
            "outputs": ["scalar-0.vti", "scalar-1.vti", "vector.vti"]}
    assert submit(spec, "demo-field") == ""
    assert REVIEW in submit(spec) and REVIEW in submit(spec, "unknown")


def test_cluster_template_without_walltime_is_refused_and_reviewed():
    # sbatch gets no --time, and a partition's default limit may be unlimited (BSCC: infinite).
    unbounded = {**EXAMPLE, "backend": "slurm", "resources": {"ranks": 8, "queue": "amd_256"}}
    with pytest.raises(ValueError, match="must set resources.walltime_seconds"):
        validate_template("muferro-slurm-8", unbounded)
    request = {"id": "b" * 32, "node_id": "c" * 32, "kind": "task.submit",
               "payload": {"template": "muferro-slurm-8", "spec": {"workspace_id": WS, **unbounded}}}
    assert LIMIT in validate_action(request, {"muferro-slurm-8": unbounded})
    bounded = {**unbounded, "resources": {**unbounded["resources"], "walltime_seconds": 1800}}
    validate_template("muferro-slurm-8", bounded)
    request["payload"]["spec"] = {"workspace_id": WS, **bounded}
    assert validate_action(request, {"muferro-slurm-8": bounded}) == ""
