"""Side-effect levels of every scripting operation, and which the agent's tools may use (docs/design/agent-harness.md).

Levels are STK's own, never taken from a model or another service:

- ``read``: reads the project, its runs or this computer's settings; bounded computation in this process.
- ``record``: appends an immutable record (a context, a discussion message, a request) without changing the revision.
- ``model``: sends one request through the model gateway (its checks apply).
- ``draft``: saves a draft that a person reviews; never applies it.
- ``prepare_run``: freezes a run plan (no submission). No agent tool in v1 (owner decision 3).
- ``submit_run``: starts, submits or cancels computation, locally or on a Runtime. Never for the agent.
- ``project_edit``: changes the project's revision, labels, archive or settings, or files on this computer. Never.
- ``external_network``: connects to other computers or services (Runtime, hub, transfers). Never in v1.

The tests check that every operation in the bridge's script catalog is classified here, and that tools use only
operations at the first four levels.
"""

AGENT_LEVELS = ("read", "record", "model", "draft")
LEVELS = (*AGENT_LEVELS, "prepare_run", "submit_run", "project_edit", "external_network")

# operation -> (level, why the agent does not use it, or "" when a tool uses it)
OPERATIONS = {
    "project.create": ("project_edit", "creates a project on disk"),
    "project.open": ("read", "the agent works in the project its session belongs to"),
    "project.list": ("read", "the agent works in the project its session belongs to"),
    "project.recent": ("read", "the agent works in the project its session belongs to"),
    "project.forget": ("project_edit", "changes this computer's list of recent projects"),
    "project.close": ("project_edit", "ends the project opening"),
    "project.snapshot": ("read", "reads every value of every table; project_outline reads the structure only"),
    "project.apply": ("project_edit", "changes the project: only through drafts a person applies"),
    "project.preview": ("read", "not needed: proposals go through requests and drafts"),
    "project.sweep.plan": ("read", "not needed: sweeps are proposed by a request and saved as a draft"),
    "project.history": ("read", "not needed in v1"),
    "project.backup": ("project_edit", "writes a backup file on this computer"),
    "project.upgrade": ("project_edit", "changes the project's format"),
    "project.undo": ("project_edit", "changes the project"),
    "project.redo": ("project_edit", "changes the project"),
    "project.drafts.save": ("draft", "drafts come from a request's proposal (propose_sweep)"),
    "project.drafts.get": ("read", ""),
    "project.drafts.list": ("read", "not needed: draft_status reads one draft"),
    "project.drafts.apply": ("project_edit", "a person applies drafts"),
    "project.drafts.discard": ("project_edit", "a person discards drafts"),
    "project.contexts.capture": ("record", ""),
    "project.contexts.get": ("read", ""),
    "project.contexts.list": ("read", "not needed in v1"),
    "project.discussion.add": ("record", ""),
    "project.discussion.get": ("read", "not needed in v1"),
    "project.discussion.list": ("read", "not needed in v1"),
    "project.discussion.link_draft": ("record", "not needed: proposals link their drafts themselves"),
    "project.discussion.proposals": ("read", "not needed in v1"),
    "project.requests.create": ("record", ""),
    "project.requests.get": ("read", ""),
    "project.requests.list": ("read", "not needed in v1"),
    "project.requests.cancel": ("record", "the session cancels its own requests"),
    "project.requests.provider": ("read", "not needed: the model choice reads the endpoints"),
    "project.requests.start": ("model", ""),
    "project.requests.recover": ("record", "recovery is explicit, by a person or a script"),
    "project.requests.progress": ("read", "not needed: tools wait for the final record"),
    "project.requests.propose_edits": ("draft", ""),
    "project.requests.edit_proposal": ("read", "not needed in v1"),
    "project.requests.usage": ("read", "not needed: the session sums its own use"),
    "project.csv.import": ("project_edit", "changes the project"),
    "project.csv.export": ("project_edit", "writes a file on this computer"),
    "project.files.list": ("read", "not needed in v1"),
    "project.files.index": ("project_edit", "changes the project"),
    "project.files.refresh": ("project_edit", "changes the project"),
    "project.files.resolve": ("read", "not needed in v1"),
    "project.analyses.create": ("project_edit", "changes the project"),
    "project.analyses.update": ("project_edit", "changes the project"),
    "project.analyses.get": ("read", "not needed in v1"),
    "project.analyses.list": ("read", "not needed in v1"),
    "project.workflows.create": ("project_edit", "changes the project"),
    "project.workflows.update": ("project_edit", "changes the project"),
    "project.workflows.get": ("read", "not needed: project_outline lists workflows"),
    "project.workflows.list": ("read", "not needed: project_outline lists workflows"),
    "project.workflows.validate": ("read", "not needed in v1"),
    "project.workflows.choices": ("read", "not needed in v1"),
    "project.workflow_runs.prepare": ("prepare_run", "the AI never prepares runs in v1 (owner decision 3)"),
    "project.workflow_runs.get": ("read", ""),
    "project.workflow_runs.list": ("read", ""),
    "project.workflow_runs.start": ("submit_run", "a person starts runs"),
    "project.workflow_runs.cancel": ("submit_run", "a person cancels runs"),
    "project.workflow_runs.recover": ("submit_run", "recovery is explicit, by a person"),
    "project.workflow_runs.stale": ("read", "not needed in v1"),
    "project.attention.list": ("read", "not needed in v1"),
    "project.attention.viewed": ("project_edit", "records a person's view on this computer"),
    "project.search": ("read", "not needed in v1"),
    "project.archive.set": ("project_edit", "a person archives"),
    "project.archive.list": ("read", "not needed in v1"),
    "project.labels.set": ("project_edit", "labelling data public lets it leave this computer: only a person decides"),
    "project.labels.list": ("read", "not needed: project_outline shows each table's label"),
    "project.analysis_runs.prepare": ("prepare_run", "the AI never prepares runs in v1"),
    "project.analysis_runs.get": ("read", "not needed in v1"),
    "project.analysis_runs.list": ("read", "not needed in v1"),
    "project.analysis_runs.start": ("submit_run", "computation is started by a person"),
    "project.analysis_runs.cancel": ("submit_run", "a person cancels runs"),
    "project.analysis_runs.recover": ("submit_run", "recovery is explicit, by a person"),
    "project.analysis_runs.result": ("read", "not needed in v1"),
    "project.snapshots.list": ("read", "not needed in v1"),
    "project.snapshots.capture": ("project_edit", "advances the revision"),
    "project.snapshots.get": ("read", "not needed in v1"),
    "project.snapshots.verify": ("read", "not needed in v1"),
    "project.snapshots.resolve": ("read", "not needed in v1"),
    "project.runs.prepare": ("project_edit", "advances the revision"),
    "project.runs.list": ("read", "not needed in v1"),
    "project.runs.get": ("read", "not needed in v1"),
    "project.runs.submit": ("submit_run", "a person submits"),
    "project.runs.refresh": ("external_network", "asks a Runtime"),
    "project.runs.cancel": ("submit_run", "a person cancels runs"),
    "graph.catalog": ("read", "not needed in v1"),
    "graph.presets": ("read", "not needed in v1"),
    "graph.validate": ("read", "not needed in v1"),
    "graph.evaluate": ("submit_run", "computation is started by a person"),
    "graph.cancel": ("submit_run", "a person cancels evaluations"),
    "blob.ensure": ("project_edit", "writes the cache on this computer"),
    "probe": ("read", "not needed in v1"),
    "colormaps.list": ("read", "not needed in v1"),
    "skills.list": ("read", "not needed: the session's skills are frozen in its header"),
    "skills.get": ("read", "not needed: the session's skills are frozen in its header"),
    "models.list": ("read", "not needed: the session's route is frozen in its header"),
    "models.local.list": ("read", "not needed in v1"),
    "models.route": ("read", "not needed: tools choose models through the gateway"),
    "connections.list": ("read", "not needed in v1"),
    "connections.check": ("external_network", "connects to a Runtime"),
    "connections.ssh": ("external_network", "connects to another computer"),
    "hub.devices": ("external_network", "asks the control service"),
    "hub.templates": ("external_network", "asks the control service"),
    "hub.actions": ("external_network", "asks the control service"),
    "hub.action": ("external_network", "acts on another computer"),
    "workspace.list": ("external_network", "asks a Runtime"),
    "workspace.create": ("external_network", "creates a workspace on a Runtime"),
    "workspace.files": ("external_network", "asks a Runtime"),
    "upload.start": ("external_network", "uploads to a Runtime"),
    "download.start": ("external_network", "downloads from a Runtime"),
    "transfer.list": ("read", "not needed in v1"),
    "transfer.get": ("read", "not needed in v1"),
    "transfer.resume": ("external_network", "resumes a transfer"),
    "transfer.cancel": ("external_network", "cancels a transfer"),
    "task.submit": ("submit_run", "submits computation"),
    "task.list": ("external_network", "asks a Runtime"),
    "task.get": ("external_network", "asks a Runtime"),
    "task.cancel": ("submit_run", "cancels computation"),
    "task.artifacts": ("external_network", "asks a Runtime"),
    "task.logs": ("external_network", "asks a Runtime"),
    # The agent's own methods: scripts may drive sessions; the agent cannot call itself.
    "project.agent.tools": ("read", "the agent's own interface"),
    "project.agent.route": ("read", "the agent's own interface"),
    "project.agent.create": ("record", "the agent's own interface"),
    "project.agent.say": ("record", "the agent's own interface"),
    "project.agent.start": ("model", "the agent's own interface"),
    "project.agent.cancel": ("record", "the agent's own interface"),
    "project.agent.recover": ("record", "the agent's own interface"),
    "project.agent.get": ("read", "the agent's own interface"),
    "project.agent.list": ("read", "the agent's own interface"),
    "project.agent.objects": ("read", "the agent's own interface"),
    "project.agent.verify": ("read", "the agent's own interface"),
    "project.agent.export": ("read", "the agent's own interface"),
    "materials.datasets.synthetic": ("project_edit", "writes files to a folder on this computer"),
    "materials.datasets.validate": ("read", "not in v1: materials models are a person's work in S3"),
    "materials.train": ("submit_run", "training uses this computer for minutes; a person starts it"),
    "materials.jobs.get": ("read", "not in v1: materials models are a person's work in S3"),
    "materials.jobs.cancel": ("submit_run", "a person cancels training"),
    "materials.models.list": ("read", "not in v1: materials models are a person's work in S3"),
    "materials.models.activate": ("project_edit", "a person chooses which model version is used"),
    "materials.predict": ("read", "not in v1: a prediction tool comes after S3a"),
}

# Desktop-only methods that are deliberately not in the script catalog.
DESKTOP_ONLY = {"project.agent.decide": ("project_edit", "a person approves a draft from the session card")}

# The operations each tool's implementation performs (by their store equivalents); all must be at agent levels.
TOOL_USES = {
    "project_outline": [],  # its own structure read (no values): see suan/agent/tools.py
    "capture_rows": ["project.contexts.capture"],
    "table_statistics": ["project.contexts.get"],
    "propose_sweep": ["project.discussion.add", "project.requests.create", "project.requests.start", "project.requests.get",
                      "project.requests.propose_edits"],
    "ask_about_context": ["project.discussion.add", "project.requests.create", "project.requests.start",
                          "project.requests.get"],
    "draft_status": ["project.drafts.get"],
    "find_runs": ["project.workflow_runs.list", "project.workflow_runs.get"],
    "capture_run_results": ["project.workflow_runs.get", "project.contexts.capture"],
}


def level(operation):
    found = OPERATIONS.get(operation) or DESKTOP_ONLY.get(operation)
    return found[0] if found else None


def tool_level(tool):
    """The highest level among the operations a tool performs."""
    levels = [level(operation) for operation in TOOL_USES[tool]] or ["read"]
    return max(levels, key=AGENT_LEVELS.index)


__all__ = ["AGENT_LEVELS", "DESKTOP_ONLY", "LEVELS", "OPERATIONS", "TOOL_USES", "level", "tool_level"]
