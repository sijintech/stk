"""Test-only real bridge for the desktop's agent tests: a loopback endpoint ("Laptop") whose model is scripted, so the
agent plans and answers its own sweep request without any model. Production never imports it.

The planner reads the conversation it is sent: after the person's message it outlines the project, then captures the
first table's rows, then proposes a sweep of three values of the first numeric field over the first row, then ends
its turn. Holding: while the file ``hold`` exists in the control folder, every planner turn waits (at most 30 s), so
a test can see a session running.
"""
import json
from pathlib import Path
import sys
import time

from suan.agent import wire
from suan.desktop_bridge import server
from suan.desktop_bridge.__main__ import main

control = Path(sys.argv.pop(1))
ADAPTER = "openai-compatible/1:laptop"


def call(name, arguments):
    return wire.ModelTurn(None, {"id": None, "name": name, "arguments": arguments, "raw_arguments": json.dumps(arguments)},
                          "tool_calls", {"input_tokens": 120, "output_tokens": 30})


class ScriptedModel:
    def prepare_turn(self, value):
        model = self

        class Prepared:
            def send(self, frozen, cancel):
                deadline = time.monotonic() + 30
                while (control / "hold").exists() and time.monotonic() < deadline and not cancel.is_set():
                    time.sleep(0.05)
                return model.plan(frozen)
        return Prepared()

    @staticmethod
    def plan(frozen):
        last = frozen["messages"][-1]
        if last["role"] != "tool":
            return call("project_outline", {})
        result = json.loads(last["content"])
        data = result.get("data", {})
        if result["tool"] == "project_outline":
            return call("capture_rows", {"table_id": data["tables"][0]["id"]})
        if result["tool"] == "capture_rows" and result["status"] == "ok":
            return call("propose_sweep", {"context_id": data["context_id"], "instruction": "Three values, from the first row."})
        return wire.ModelTurn("I saved a draft. Review and apply it, then run the new rows.", None, "stop",
                              {"input_tokens": 80, "output_tokens": 20})

    @staticmethod
    def send(frozen_input, cancel):
        """The session's own sweep request: three values of the first numeric field, based on the first row."""
        context = frozen_input["context"]
        value = context["content"]["value"]
        field = next(item for item in value["fields"] if item["type"] in ("number", "integer"))
        return json.dumps({"format": "stk.parameter-sweep/1", "context_id": context["id"],
                           "base_revision": context["source_revision"], "summary": "Three values.",
                           "base_record_id": value["records"][0]["id"],
                           "axes": [{"field_id": field["id"], "start": 300, "stop": 400, "count": 3}], "mode": "product"})


original_init = server.Bridge.__init__


def scripted_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    models = self.projects.models
    if models.endpoints.get("laptop") is None:
        models.endpoints.add("laptop", "Laptop", "http://127.0.0.1:9/v1", ["qwen"])
    models[ADAPTER] = ScriptedModel()


server.Bridge.__init__ = scripted_init
main()
