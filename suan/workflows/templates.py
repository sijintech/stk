"""Explicitly registered, versioned workflow templates. Project data never imports code."""
from . import muferro
from suan.runtime.models import TaskSpec
from suan.mupro.spec import muferro_spec


class MuFerroTemplate:
    id = "muferro/1"
    table_id = muferro.TABLE_ID
    name = "MuFerro"

    def describe(self, model, record_id, connection, options):
        values, _, label = muferro.describe_case(model, record_id, connection, options)
        return {"record_id": record_id, "label": label, "values": values}

    def prepare(self, stk, project, record_id, connection, options, revision):
        return stk.muferro.prepare(record_id, connection, expected_revision=revision, project=project, **options)

    def collect(self, stk, project, run_id):
        return stk.muferro.collect(run_id, project=project)

    def validate_run(self, plan, entry, intent):
        parameters = plan["parameters"]
        frozen = {"project": {"id": plan["project_id"]}, "tables": [{"id": self.table_id,
            "fields": parameters["fields"], "records": [{"id": parameters["record_id"],
            "values": parameters["values"], "definitions": parameters["definitions"]}]}]}
        described = self.describe(frozen, entry["record_id"], intent["connection"], intent["options"])
        expected = TaskSpec(**muferro_spec("0" * 32, case_dir="case", name="MuFerro", **intent["options"])).to_dict()
        ignored = {"workspace_id", "inputs", "input_hashes", "outputs"}
        if (described != entry or
                {k: v for k, v in expected.items() if k not in ignored} !=
                {k: v for k, v in plan["spec"].items() if k not in ignored}):
            raise ValueError("Saved run parameters or command do not match the batch template")


TEMPLATES = {MuFerroTemplate.id: MuFerroTemplate()}


def template(identity):
    if identity not in TEMPLATES:
        raise ValueError("Unknown workflow template version")
    return TEMPLATES[identity]
