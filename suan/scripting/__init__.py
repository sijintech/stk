"""Python operation facade injected as ``stk`` in the desktop's isolated console.

The facade uses the same project commands and revision checks as the native table editor.
It holds IDs, never C++ window pointers. See ``docs/scripting.md`` for the supported coverage.
"""
from pathlib import Path
from uuid import uuid4

from .runtime import Connections, Runtime, Transfers
from .viewer import Viewer
from .graph import Graph
from .skills import Skills



def _listing(handle, offset, limit, archived):
    """List parameters; ``archived`` is sent only when filtering, so older services see the same request."""
    params = {"handle": handle, "offset": offset, "limit": limit}
    if archived is not None:
        params["archived"] = bool(archived)
    return params

class ScriptError(RuntimeError):
    """An operation failed; ``code`` and ``data`` retain its structured bridge error."""

    def __init__(self, error):
        super().__init__(f"{error['code']}: {error['message']}")
        self.code = error["code"]
        self.data = error.get("data")
        self.retryable = error.get("retryable", False)


class Project:
    def __init__(self, call, handle):
        self._call = call
        self.handle = handle

    def snapshot(self):
        return self._call("project.snapshot", {"handle": self.handle})["snapshot"]

    def selection(self):
        """Read shared table/record UUIDs and the desktop's observed revision.

        This handle must still identify the visible project. The result describes
        shared selection, not a particular editor's filtered rows or active column.
        """
        return self._call("ui.project.selection", {"handle": self.handle})

    def select(self, table_id, record_id, *, expected_revision):
        """Select one explicit existing row without editing data or moving focus.

        Both IDs must belong to the visible project at the supplied revision. This
        never opens a project, replaces a review, or supplies a view-specific filter.
        """
        return self._call("ui.project.select", {"handle": self.handle, "expected_revision": expected_revision,
                                               "table_id": table_id, "record_id": record_id})

    def apply(self, commands, *, expected_revision):
        """One atomic edit, with an explicit base revision; never retried automatically."""
        return self._call("project.apply", {"handle": self.handle, "commands": commands,
                                            "expected_revision": expected_revision})

    def sweep(self, table_id, axes, *, expected_revision, base_record_id=None, mode="product", dry_run=False):
        """Add one row per combination of axis values (see ``suan.project.sweep``) in one revision.

        ``axes`` are ``{"field_id", "values": [...]}`` or ranges ``{"field_id", "start", "stop", "count"|"step"}``.
        With ``base_record_id`` every other cell of that row is copied. ``dry_run`` only returns the plan.
        """
        params = {"handle": self.handle, "table_id": table_id, "axes": axes, "mode": mode}
        if base_record_id is not None:
            params["base_record_id"] = base_record_id
        planned = self._call("project.sweep.plan", params)
        if planned["revision"] != expected_revision:
            raise ScriptError({"code": "conflict", "message": f"Expected revision {expected_revision}, "
                               f"current revision is {planned['revision']}"})
        if dry_run:
            return planned["plan"]
        result = self.apply(planned["plan"]["commands"], expected_revision=expected_revision)
        return {**result, "rows": planned["plan"]["rows"], "record_ids": planned["plan"]["record_ids"]}

    def preview(self, commands, *, expected_revision):
        """Evaluate a hypothetical edit without saving; apply its normalized commands explicitly."""
        return self._call("project.preview", {"handle": self.handle, "commands": commands,
                                              "expected_revision": expected_revision})

    def review(self, commands, *, expected_revision):
        """Ask the visible desktop to preview this edit for explicit user application.

        Returns acceptance, not preview completion or a saved edit. The desktop must already
        show this project at the supplied revision and have no pending review draft.
        """
        return self._call("ui.project.review", {"handle": self.handle, "commands": commands,
                                               "expected_revision": expected_revision})

    def history(self):
        return self._call("project.history", {"handle": self.handle})["history"]

    def backup(self):
        """Consistent database backup; does not include external assets or execute code."""
        return self._call("project.backup", {"handle": self.handle})

    def upgrade(self, *, expected_revision):
        """Explicit format upgrade after creating a verified pre-migration database backup."""
        return self._call("project.upgrade", {"handle": self.handle, "expected_revision": expected_revision})

    def close(self):
        return self._call("project.close", {"handle": self.handle})["closed"]

    def undo(self, *, expected_revision):
        """Undo the latest active edit batch as a new revision; not an external side-effect rollback."""
        return self._call("project.undo", {"handle": self.handle, "expected_revision": expected_revision})

    def redo(self, *, expected_revision):
        """Reapply the next undone batch; new edits discard the redo stack."""
        return self._call("project.redo", {"handle": self.handle, "expected_revision": expected_revision})

    @property
    def csv(self):
        return ProjectCSV(self._call, self.handle)

    @property
    def files(self):
        return ProjectFiles(self._call, self.handle)

    @property
    def analyses(self):
        return ProjectAnalyses(self._call, self.handle)

    @property
    def analysis_runs(self):
        return ProjectAnalysisRuns(self._call, self.handle)

    @property
    def workflows(self):
        return ProjectWorkflows(self._call, self.handle)

    @property
    def workflow_runs(self):
        return ProjectWorkflowRuns(self._call, self.handle)

    def attention(self):
        """Failures, items to review, running work and finished items, with this person's viewed marks.
        Read-only: {revision, items: [{key, kind, id, group, severity, name, status, at, target, viewed, ...}], counts}."""
        return self._call("project.attention.list", {"handle": self.handle})

    def search(self, query, *, limit=100):
        """Tables, fields, text cells, workflows, analyses, files, drafts and messages matching `query`
        (case-insensitive); reads only: {revision, query, results: [{kind, id, name, target, ...}], counts, truncated}."""
        return self._call("project.search", {"handle": self.handle, "query": query, "limit": limit})

    def archive(self, kind, ids, *, note=None, include_runs=False):
        """Archive objects of one kind (format 11): hidden from default lists and frozen (cannot be changed,
        can still be used as they are); nothing is deleted. ``include_runs`` also archives a workflow's runs that are not running."""
        return self._archive(kind, ids, True, note, include_runs)

    def unarchive(self, kind, ids, *, include_runs=False):
        """Restore archived objects of one kind."""
        return self._archive(kind, ids, False, None, include_runs)

    def _archive(self, kind, ids, archived, note, include_runs):
        params = {"handle": self.handle, "items": [{"kind": kind, "id": identity} for identity in ids], "archived": archived}
        if note is not None:
            params["note"] = note
        if include_runs:
            params["include_runs"] = True
        return self._call("project.archive.set", params)

    def archived(self, kind=None):
        """Currently archived objects ({kind, id, archived_at, note}) and counts per kind."""
        params = {"handle": self.handle}
        if kind is not None:
            params["kind"] = kind
        return self._call("project.archive.list", params)

    def mark_public(self, kind, ids, *, note=None):
        """Label data public (format 12): only public data may be sent to external model endpoints.
        ``kind`` is "table" or "file"; labelling is recorded but is not a project edit."""
        params = {"handle": self.handle, "items": [{"kind": kind, "id": identity} for identity in ids], "label": "public"}
        if note is not None:
            params["note"] = note
        return self._call("project.labels.set", params)

    def mark_structure_public(self, table_ids, *, note=None):
        """Label tables structure-public (format 13): their names, fields, units and row counts may go to external
        models, their values stay private."""
        params = {"handle": self.handle, "items": [{"kind": "table", "id": identity} for identity in table_ids],
                  "label": "structure"}
        if note is not None:
            params["note"] = note
        return self._call("project.labels.set", params)

    def mark_private(self, kind, ids):
        """Label data private again (the default): it is no longer sent to external model endpoints."""
        return self._call("project.labels.set", {"handle": self.handle, "label": "private",
                                                  "items": [{"kind": kind, "id": identity} for identity in ids]})

    def route_model(self, context_id, prompt_version="stk.text/1"):
        """The automatic model choice for a question on a saved context: {task, public, candidates, excluded, choice}.
        Simple questions take the nearest and smallest model, parameter proposals the strongest; private data only goes
        to models on this computer or the organization's network. Reads only; nothing is started or sent."""
        return self._call("models.route", {"handle": self.handle, "context_id": context_id, "prompt_version": prompt_version})

    def labels(self, kind=None, *, include_structure=False):
        """Data currently labelled public ({kind, id, label, labelled_at, note}); with ``include_structure``, also tables
        whose structure only is public (label ``structure``)."""
        params = {"handle": self.handle}
        if kind is not None:
            params["kind"] = kind
        if include_structure:
            params["include_structure"] = True
        return self._call("project.labels.list", params)

    def mark_viewed(self, keys):
        """Mark attention items as viewed (kept for this person only, outside the project)."""
        return self._call("project.attention.viewed", {"handle": self.handle, "keys": list(keys)})

    @property
    def runs(self):
        return ProjectRuns(self._call, self.handle)

    @property
    def snapshots(self):
        return ProjectSnapshots(self._call, self.handle)

    @property
    def drafts(self):
        return ProjectDrafts(self._call, self.handle)

    @property
    def contexts(self):
        return ProjectContexts(self._call, self.handle)

    @property
    def discussion(self):
        return ProjectDiscussion(self._call, self.handle)

    @property
    def requests(self):
        return ProjectRequests(self._call, self.handle)

    @property
    def agent(self):
        return ProjectAgent(self._call, self.handle)


class ProjectAgent:
    """Agent sessions (format 13, docs/design/agent-harness.md): the agent plans with a model on this computer or the
    organization's network and calls bounded tools; at most it saves drafts a person applies. It never prepares or starts
    runs, labels data or changes settings."""

    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def tools(self):
        return self._call("project.agent.tools", {"handle": self.handle})

    def route(self):
        return self._call("project.agent.route", {"handle": self.handle})

    def create(self, text, *, session_id=None, turn_id=None, configuration=None):
        params = {"handle": self.handle, "session_id": session_id or str(uuid4()), "turn_id": turn_id or str(uuid4()),
                  "text": text}
        if configuration is not None:
            params["configuration"] = configuration
        return self._call("project.agent.create", params)

    def say(self, session_id, text, *, turn_id=None):
        return self._call("project.agent.say", {"handle": self.handle, "session_id": session_id,
                                                "turn_id": turn_id or str(uuid4()), "text": text})

    def start(self, session_id):
        return self._call("project.agent.start", {"handle": self.handle, "session_id": session_id})

    def get(self, session_id, *, offset=None, limit=None):
        """A session with a page of its events: ``limit`` from ``offset``; without either, the newest 1000."""
        params = {"handle": self.handle, "session_id": session_id}
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        return self._call("project.agent.get", params)

    def list(self, *, offset=0, limit=50):
        return self._call("project.agent.list", {"handle": self.handle, "offset": offset, "limit": limit})

    def cancel(self, session_id):
        return self._call("project.agent.cancel", {"handle": self.handle, "session_id": session_id})

    def recover(self, session_id):
        return self._call("project.agent.recover", {"handle": self.handle, "session_id": session_id})

    def verify(self, session_id):
        return self._call("project.agent.verify", {"handle": self.handle, "session_id": session_id})

    def export(self, session_id):
        return self._call("project.agent.export", {"handle": self.handle, "session_id": session_id})

    def ask(self, text, *, session_id=None, wait=True, poll=0.2, timeout=1800):
        """Start a session with ``text`` (or continue ``session_id``) and, with ``wait``, return it once the agent has
        answered (state idle, awaiting or ended)."""
        import time
        if session_id is None:
            session = self.create(text)
            session_id = session["session"]["id"]
        else:
            self.say(session_id, text)
        view = self.start(session_id)
        deadline = time.monotonic() + timeout
        while wait and (view["state"] == "ready" or view.get("running")) and time.monotonic() < deadline:
            time.sleep(poll)
            view = self.get(session_id)
        return view


class ProjectRequests:
    """Saved request intent and observations. Creating or reading never sends to a model."""

    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def create(self, message_id, *, request_id, configuration, prompt_version="stk.text/1"):
        params = {"handle": self.handle, "message_id": message_id,
                  "request_id": request_id, "configuration": configuration}
        # Preserve the existing text-only wire shape for bridges predating structured requests.
        if prompt_version != "stk.text/1":
            params["prompt_version"] = prompt_version
        return self._call("project.requests.create", params)["request"]

    def get(self, request_id):
        return self._call("project.requests.get", {"handle": self.handle, "request_id": request_id})["request"]

    def progress(self, request_id):
        """Read saved state and bounded, unsaved stream text; never send or recover."""
        return self._call("project.requests.progress", {"handle": self.handle, "request_id": request_id})

    def propose_edits(self, request_id, *, expected_revision):
        """Explicitly save a completed parameter reply as a review draft; never apply or send."""
        return self._call("project.requests.propose_edits", {"handle": self.handle,
            "request_id": request_id, "expected_revision": expected_revision})

    def edit_proposal(self, request_id):
        """Read the request's saved draft and provenance, or two nulls; never create or rebase."""
        return self._call("project.requests.edit_proposal", {"handle": self.handle, "request_id": request_id})

    def usage(self):
        """Provider-reported token counts of completed requests, in total and per model; reads only.
        The provider's console is authoritative; failed or uncertain requests are not counted."""
        return self._call("project.requests.usage", {"handle": self.handle})

    def list(self, *, offset=0, limit=100, archived=None):
        """archived: True lists only archived objects, False only the others (format 11); None lists all."""
        return self._call("project.requests.list", _listing(self.handle, offset, limit, archived))

    def cancel(self, request_id):
        """Record cancellation intent; this alone cannot prove a running remote call stopped."""
        return self._call("project.requests.cancel", {"handle": self.handle, "request_id": request_id})["request"]

    def provider(self):
        """Read local provider configuration status without sending or exposing credentials."""
        return self._call("project.requests.provider", {"handle": self.handle})["provider"]

    def start(self, request_id):
        """Explicitly send a pending request once; inspect its saved state after lost replies."""
        return self._call("project.requests.start", {"handle": self.handle, "request_id": request_id})["request"]

    def recover(self, request_id):
        """Check a lost local executor; never retry or query the remote model."""
        return self._call("project.requests.recover", {"handle": self.handle, "request_id": request_id})["request"]


class ProjectContexts:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def capture(self, table_id, record_ids, field_ids, *, expected_revision, title, context_id):
        """Freeze explicit selected cells and their provenance; never expand the selection implicitly."""
        return self._call("project.contexts.capture", {"handle": self.handle, "table_id": table_id,
            "record_ids": record_ids, "field_ids": field_ids, "expected_revision": expected_revision,
            "title": title, "context_id": context_id})["context"]

    def get(self, context_id):
        return self._call("project.contexts.get", {"handle": self.handle, "context_id": context_id})["context"]

    def list(self, *, offset=0, limit=100, archived=None):
        """archived: True lists only archived objects, False only the others (format 11); None lists all."""
        return self._call("project.contexts.list", _listing(self.handle, offset, limit, archived))


class ProjectDiscussion:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def add(self, text, *, message_id, context_id, role="user"):
        """Save plain text bound to a captured context; neither role nor text executes operations."""
        return self._call("project.discussion.add", {"handle": self.handle, "text": text,
            "message_id": message_id, "context_id": context_id, "role": role})["message"]

    def get(self, message_id):
        return self._call("project.discussion.get", {"handle": self.handle, "message_id": message_id})["message"]

    def list(self, *, offset=0, limit=100):
        return self._call("project.discussion.list", {"handle": self.handle, "offset": offset, "limit": limit})

    def link_draft(self, message_id, draft_id, *, proposal_id):
        """Record matching-context provenance for a saved draft; never apply or approve it."""
        return self._call("project.discussion.link_draft", {"handle": self.handle, "message_id": message_id,
            "draft_id": draft_id, "proposal_id": proposal_id})["proposal"]

    def proposals(self, *, offset=0, limit=100, draft_id=None):
        params = {"handle": self.handle, "offset": offset, "limit": limit}
        if draft_id is not None:
            params["draft_id"] = draft_id
        return self._call("project.discussion.proposals", params)


class ProjectDrafts:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def save(self, commands, *, expected_revision, title, draft_id):
        """Save a validated proposal without applying it; retain the UUID to recover a lost response."""
        return self._call("project.drafts.save", {"handle": self.handle, "commands": commands,
            "expected_revision": expected_revision, "title": title, "draft_id": draft_id})["draft"]

    def get(self, draft_id):
        return self._call("project.drafts.get", {"handle": self.handle, "draft_id": draft_id})["draft"]

    def list(self, *, offset=0, limit=100, archived=None):
        """archived: True lists only archived objects, False only the others (format 11); None lists all."""
        return self._call("project.drafts.list", _listing(self.handle, offset, limit, archived))

    def apply(self, draft_id, *, expected_revision):
        """Explicitly apply once at the saved revision; later retries return the durable receipt."""
        return self._call("project.drafts.apply", {"handle": self.handle, "draft_id": draft_id,
                                                  "expected_revision": expected_revision})

    def discard(self, draft_id):
        """Close a pending saved draft without changing project tables or undo history."""
        return self._call("project.drafts.discard", {"handle": self.handle, "draft_id": draft_id})["draft"]


class ProjectCSV:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def import_file(self, source, *, name, expected_revision, types=None, units=None, delimiter=","):
        params = {"handle": self.handle, "source": str(Path(source).expanduser().absolute()),
                  "name": name, "expected_revision": expected_revision, "delimiter": delimiter}
        if types is not None:
            params["types"] = types
        if units is not None:
            params["units"] = units
        return self._call("project.csv.import", params)

    def export_file(self, table_id, destination, *, expected_revision, delimiter=","):
        return self._call("project.csv.export", {"handle": self.handle, "table_id": table_id,
            "destination": str(Path(destination).expanduser().absolute()),
            "expected_revision": expected_revision, "delimiter": delimiter})


class ProjectRuns:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def prepare(self, entries, *, connection, expected_revision, node=None):
        """Freeze explicit per-row TaskSpecs; this does not upload files or start execution."""
        params = {"handle": self.handle, "entries": entries, "connection": connection,
                  "expected_revision": expected_revision}
        if node is not None:
            params["node"] = node
        return self._call("project.runs.prepare", params)

    def list(self, *, offset=0, limit=100, archived=None):
        """archived: True lists only archived objects, False only the others (format 11); None lists all."""
        return self._call("project.runs.list", _listing(self.handle, offset, limit, archived))

    def get(self, run_id):
        return self._call("project.runs.get", {"handle": self.handle, "run_id": run_id})["run"]

    def submit(self, run_id, *, allow_stale=False):
        """Explicit submission/recovery; repeat the same run ID after a lost response."""
        return self._call("project.runs.submit", {"handle": self.handle, "run_id": run_id,
                                                "allow_stale": allow_stale})["run"]

    def refresh(self, run_id):
        return self._call("project.runs.refresh", {"handle": self.handle, "run_id": run_id})["run"]

    def cancel(self, run_id):
        return self._call("project.runs.cancel", {"handle": self.handle, "run_id": run_id})["run"]


class ProjectSnapshots:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def list(self):
        return self._call("project.snapshots.list", {"handle": self.handle})

    def capture(self, record_ids, *, expected_revision, max_bytes=256 * 1024 * 1024):
        """Explicitly copy selected input bytes; immutable manifests are outside table undo."""
        return self._call("project.snapshots.capture", {"handle": self.handle, "record_ids": record_ids,
                         "expected_revision": expected_revision, "max_bytes": max_bytes})

    def get(self, snapshot_id):
        return self._call("project.snapshots.get", {"handle": self.handle, "snapshot_id": snapshot_id})["snapshot"]

    def verify(self, snapshot_id):
        return self._call("project.snapshots.verify", {"handle": self.handle, "snapshot_id": snapshot_id})

    def resolve(self, snapshot_id, record_id):
        """Verify frozen bytes and return their path, irrespective of later source/index edits."""
        return self._call("project.snapshots.resolve", {"handle": self.handle, "snapshot_id": snapshot_id,
                                                       "record_id": record_id})


class ProjectAnalyses:
    """Saved editable graph documents. Reading and writing never validates or executes nodes."""

    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def create(self, name, document, *, analysis_id, expected_revision):
        """Save one caller-owned UUID as an ordinary undoable project edit; never retry implicitly."""
        return self._call("project.analyses.create", {"handle": self.handle, "analysis_id": analysis_id,
            "name": name, "document": document, "expected_revision": expected_revision})

    def update(self, analysis_id, name, document, *, expected_revision):
        """Replace the complete document at an explicit project revision; preserve its record UUID."""
        return self._call("project.analyses.update", {"handle": self.handle, "analysis_id": analysis_id,
            "name": name, "document": document, "expected_revision": expected_revision})

    def get(self, analysis_id):
        """Return the observed revision and readable/invalid/unsupported document state."""
        return self._call("project.analyses.get", {"handle": self.handle, "analysis_id": analysis_id})

    def list(self, *, offset=0, limit=50, archived=None):
        """archived: True lists only archived objects, False only the others (format 11); None lists all."""
        return self._call("project.analyses.list", _listing(self.handle, offset, limit, archived))


class ProjectWorkflows:
    """Project workflows (experimental stk.workflow/1). Reading, writing and validating never run anything."""

    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def create(self, name, document, *, workflow_id, expected_revision):
        """Save one caller-owned UUID as an ordinary undoable project edit; never retry implicitly."""
        return self._call("project.workflows.create", {"handle": self.handle, "workflow_id": workflow_id,
            "name": name, "document": document, "expected_revision": expected_revision})

    def update(self, workflow_id, name, document, *, expected_revision):
        """Replace the complete document at an explicit project revision; preserve its record UUID."""
        return self._call("project.workflows.update", {"handle": self.handle, "workflow_id": workflow_id,
            "name": name, "document": document, "expected_revision": expected_revision})

    def get(self, workflow_id):
        """Return the observed revision and readable/invalid/unsupported document state."""
        return self._call("project.workflows.get", {"handle": self.handle, "workflow_id": workflow_id})

    def list(self, *, offset=0, limit=50, archived=None):
        """archived: True lists only archived objects, False only the others (format 11); None lists all."""
        return self._call("project.workflows.list", _listing(self.handle, offset, limit, archived))

    def validate(self, document):
        """Resolve references and typed links against the current project; reports issues, saves nothing."""
        return self._call("project.workflows.validate", {"handle": self.handle, "document": document})

    def choices(self):
        """Parameter tables, input snapshots, readable saved analyses and templates a step can reference."""
        return self._call("project.workflows.choices", {"handle": self.handle})


class ProjectWorkflowRuns:
    """Per-row workflow runs (format 10): freeze, then explicitly start; nothing runs implicitly."""

    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def prepare(self, workflow_id, rows, *, run_id, expected_revision, connection=None, options=None):
        """Freeze the workflow, these rows' values and the referenced analyses; executes nothing.
        MuFerro steps run on ``connection`` (a saved direct/SSH Runtime profile) with muferro_spec ``options``."""
        params = {"handle": self.handle, "workflow_id": workflow_id, "rows": rows, "run_id": run_id,
                  "expected_revision": expected_revision}
        if connection is not None:
            params["simulation"] = {"connection": connection, "options": dict(options or {})}
        return self._call("project.workflow_runs.prepare", params)["run"]

    def start(self, run_id):
        """Execute the run's unfinished tasks in the background (also retries failed or cancelled ones)."""
        return self._call("project.workflow_runs.start", {"handle": self.handle, "run_id": run_id})["run"]

    def get(self, run_id):
        return self._call("project.workflow_runs.get", {"handle": self.handle, "run_id": run_id})["run"]

    def list(self, *, offset=0, limit=50, workflow_id=None, archived=None):
        params = _listing(self.handle, offset, limit, archived)
        if workflow_id:
            params["workflow_id"] = workflow_id
        return self._call("project.workflow_runs.list", params)

    def cancel(self, run_id):
        return self._call("project.workflow_runs.cancel", {"handle": self.handle, "run_id": run_id})["run"]

    def recover(self, run_id, *, force=False):
        """After a service restart: mark attempts nobody executes as interrupted so the run can start again.
        Refused while the recorded service process still exists, unless ``force``."""
        params = {"handle": self.handle, "run_id": run_id}
        if force:
            params["force"] = True
        return self._call("project.workflow_runs.recover", params)["run"]

    def stale(self, run_id):
        """Rows whose results no longer match the current definitions, with reasons per step (read-only).
        Re-run them with a new ``prepare`` over ``stale(...)["stale_rows"]``; old runs never change."""
        return self._call("project.workflow_runs.stale", {"handle": self.handle, "run_id": run_id})


class ProjectAnalysisRuns:
    """Snapshot-bound local analysis runs, separate from Runtime simulation tasks.

    Preparation freezes a definition and file mapping. Only start dispatches work;
    reads, recovery and opening a project never restart an interrupted execution.
    """

    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def prepare(self, analysis_id, snapshot_id, bindings, *, run_id, expected_revision, parameter_overrides=None):
        """Freeze an explicit file-snapshot mapping at this revision, without executing nodes.
        ``parameter_overrides`` sets declared graph parameters for this run only (frozen with it)."""
        params = {"handle": self.handle, "analysis_id": analysis_id, "snapshot_id": snapshot_id,
                  "bindings": bindings, "run_id": run_id, "expected_revision": expected_revision}
        if parameter_overrides:
            params["parameter_overrides"] = parameter_overrides
        return self._call("project.analysis_runs.prepare", params)["run"]

    def get(self, run_id):
        return self._call("project.analysis_runs.get", {"handle": self.handle, "run_id": run_id})["run"]

    def list(self, *, offset=0, limit=50, archived=None):
        """archived: True lists only archived objects, False only the others (format 11); None lists all."""
        return self._call("project.analysis_runs.list", _listing(self.handle, offset, limit, archived))

    def start(self, run_id):
        """Explicitly claim prepared work once; terminal or unknown runs are never replayed."""
        return self._call("project.analysis_runs.start", {"handle": self.handle, "run_id": run_id})["run"]

    def cancel(self, run_id):
        """Record cancellation intent; an already confirmed result may win the race."""
        return self._call("project.analysis_runs.cancel", {"handle": self.handle, "run_id": run_id})["run"]

    def recover(self, run_id):
        """Mark interrupted work unknown only after checking no executor still owns it; never run it again."""
        return self._call("project.analysis_runs.recover", {"handle": self.handle, "run_id": run_id})["run"]

    def result(self, run_id):
        """Verify and read an archived graph result, including partial failures; never open a Viewer."""
        return self._call("project.analysis_runs.result", {"handle": self.handle, "run_id": run_id})


class ProjectFiles:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def list(self):
        return self._call("project.files.list", {"handle": self.handle})

    def index(self, paths, *, expected_revision):
        if isinstance(paths, (str, bytes)):
            raise TypeError("paths must be a sequence of paths, not a single string")
        return self._call("project.files.index", {"handle": self.handle, "paths": [str(path) for path in paths],
                                                   "expected_revision": expected_revision})

    def refresh(self, record_ids, *, expected_revision):
        return self._call("project.files.refresh", {"handle": self.handle, "record_ids": record_ids,
                                                     "expected_revision": expected_revision})

    def resolve(self, record_id, *, expected_revision):
        """Check and return the current local path; never launches an external application."""
        return self._call("project.files.resolve", {"handle": self.handle, "record_id": record_id,
                                                     "expected_revision": expected_revision})


class Projects:
    def __init__(self, call):
        self._call = call

    def open(self, directory, *, expected_id=None):
        params = {"directory": str(Path(directory).expanduser().resolve())}
        if expected_id is not None:
            params["expected_id"] = expected_id
        info = self._call("project.open", params)["project"]
        return Project(self._call, info["handle"])

    def create(self, directory, name):
        info = self._call("project.create", {"directory": str(Path(directory).resolve()), "name": name})["project"]
        return Project(self._call, info["handle"])

    def list(self):
        return self._call("project.list", {})["projects"]

    def recent(self):
        """Return saved metadata and a possible persistence warning; does not open projects."""
        return self._call("project.recent", {})

    def forget(self, directory):
        """Remove only a history entry; never closes or deletes the project."""
        return self._call("project.forget", {"directory": str(Path(directory).expanduser().absolute())})["removed"]


class Desktop:
    def __init__(self, call):
        self._call = call

    def layout(self):
        return self._call("ui.layout.get", {})["layout"]

    def apply_layout(self, layout):
        """Validate and replace the desktop layout on its UI thread; invalid input keeps it intact."""
        return self._call("ui.layout.apply", {"layout": layout})

    def editors(self):
        return self._call("ui.editors.list", {})["editors"]

    def activate_editor(self, editor_id, *, maximize=False):
        """Activate an editor in the first desktop window, preserving existing tabs and splits."""
        if type(maximize) is not bool:
            raise TypeError("maximize must be a boolean")
        return self._call("ui.editors.activate", {"editor_id": editor_id, "maximize": maximize})

    def restore_split_layout(self):
        """Restore the first window's split layout; return whether it was maximized."""
        return self._call("ui.layout.unmaximize", {})["restored"]

    def current_project(self):
        return self._call("ui.project.current", {})["project"]

    def open_project(self, directory):
        return self._call("ui.project.open", {"directory": str(Path(directory).resolve())})["project"]

    def close_project(self):
        return self._call("ui.project.close", {})


class Models:
    """The model endpoints of this computer and the network setting (read only: endpoints, keys and the network
    setting are changed by the person at this computer in the desktop, never by a script)."""

    def __init__(self, call):
        self._call = call

    def list(self):
        """{"endpoints": [...], "policy": {"network": ...}}; each endpoint has its location (local, internal,
        external), models, key presence (never the key) and whether the network setting allows it."""
        return self._call("models.list", {})


class API:
    def __init__(self, call):
        self._call = call
        self._project_handle = None
        self.projects = Projects(call)
        self.ui = Desktop(call)
        self.connections = Connections(call)
        self.transfers = Transfers(call)
        self.viewer = Viewer(call)
        self.graph = Graph(call)
        self.skills = Skills(call)
        self.models = Models(call)

    def runtime(self, connection, *, node=None):
        """Use a saved Runtime profile, optionally routed through a Hub execution node."""
        return Runtime(self._call, connection, node=node)

    @property
    def batches(self):
        """Save explicit case selections and prepare/submit/refresh/collect them independently."""
        from suan.workflows.batches import Batches
        return Batches(self)

    @property
    def muferro(self):
        """Import native cases, prepare immutable plans, collect results and open their 3D view."""
        from suan.workflows.muferro import MuFerro
        return MuFerro(self)

    @property
    def project(self):
        """Project selected when this execution started; close/switch never retargets a held handle."""
        if self._project_handle is None:
            raise ScriptError({"code": "not_found", "message": "No project was selected for this execution"})
        return Project(self._call, self._project_handle)

    def call(self, operation, **params):
        """Invoke an operation in ``operations()`` with named parameters."""
        return self._call(operation, params)

    def operations(self):
        return self._call("operations", {})

    def help(self):
        """Print the current operation catalog and supported usage examples as JSON."""
        import json
        catalog = dict(self.operations())
        if {"project.selection", "project.select"} <= set(catalog.get("ui_operations", [])):
            catalog["examples"] = {"project_selection": [
                "p = stk.project",
                "selected = p.selection()",
                "print(selected)",
                "# Supply explicit table/record UUIDs from the observed project revision:",
                "# p.select(table_id, record_id, expected_revision=selected['revision'])",
            ]}
        print(json.dumps(catalog, ensure_ascii=False, indent=2))


__all__ = ["API", "Connections", "Desktop", "Graph", "Project", "ProjectContexts", "ProjectCSV", "ProjectDiscussion", "ProjectDrafts", "ProjectFiles", "ProjectSnapshots", "ProjectRuns", "ProjectRequests", "Projects", "Runtime", "ScriptError", "Skills", "Transfers", "Viewer"]
