"""Headless evaluator for stk.graph/1 (docs/specs/stk-graph-v1.md §5).

``evaluate(graph, *, registry, resolver, ...)``:

1. validates the graph (``check_graph`` -> :class:`GraphValidationError`);
2. takes the effective graph parameters (defaults updated by ``parameters``)
   and the ancestors of the requested outputs in topological order;
3. computes every needed node's keys in that order: ``$param`` substitution,
   :meth:`NodeType.normalize_params`, the data/client split, and for source
   nodes ``fingerprint(ctx, inputs, params)`` (the file content becomes part of
   the data key; a fingerprinted source node is keyed by the content it
   resolved, without its selector params and upstream keys, so step aliases
   share one entry and a growing frame listing does not invalidate a frame);
4. pulls values lazily from the requested outputs: a node whose result is
   cached is loaded without touching its ancestors; otherwise its inputs are
   pulled first and ``impl`` runs (then ``finalize`` for representation nodes).

Caching (``suan.graph.cache``): source/data/analysis nodes and representation
geometry are keyed by the data key, so a client-stage change (colormap,
opacity, camera, image size) never re-runs them; view/output/plot nodes are
keyed by the full key; ``finalize`` output is memory-only. Choices reported
with ``ctx.report_choices`` and warnings are stored with the cache entry and
replayed on hits; choices reported during this evaluation (e.g. by a
fingerprint on a live run) win over replayed ones.

Contract for node implementations: values passed between nodes are shared
with the cache and read-only (NumPy arrays are marked non-writeable; datasets
are passed as shallow copies, so adding fields is fine, writing into input
arrays is not). The evaluator re-checks dataset kinds at run time
(``kind_mismatch``) and the kinds of dataset outputs (``bad_outputs``).

Failures: cancellation (:class:`Cancelled`) and budgets (:class:`BudgetExceeded`)
stop the evaluation at once. A failing node does not stop independent
outputs; after all requested outputs were tried, :class:`EvaluationFailed` is
raised with per-node ``errors`` and the ``partial`` result. Every such
exception carries ``partial`` (an :class:`EvaluationResult`) and ``node``.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import time
from types import MappingProxyType

from .cache import (GraphCache, data_key as make_data_key, estimate_nbytes, freeze, full_key as make_full_key,
                    plain_json, sub_key)
from .registry import (Budget, BudgetExceeded, CancelToken, Cancelled, EvaluationResult, GraphError,
                       NodeExecutionError, is_subkind)
from .schema import (GraphIssue, check_graph, graph_hash, parameter_values, parse_port_ref, substitute_params,
                     topological_order)

__all__ = ["EvaluationFailed", "evaluate"]

_DATASET_PORTS = ("dataset", "table")
# Stages whose values embed node ids; their keys include the ids (spec §5).
ID_STAGES = frozenset({"representation", "view", "output"})


class EvaluationFailed(GraphError):
    """One or more nodes failed.

    ``errors`` lists the failing nodes (issue dicts with ``code``, ``message``,
    ``node``, ``hint``); ``skipped`` the nodes not evaluated because an upstream
    node failed; ``partial`` is the :class:`EvaluationResult` with every output
    that could still be computed.
    """

    def __init__(self, errors, partial, skipped=()):
        first = errors[0]
        more = f" (and {len(errors) - 1} more)" if len(errors) > 1 else ""
        super().__init__(first["code"], f"Node '{first['node']}' failed: {first['message']}{more}",
                         node=first["node"], hint=first.get("hint"))
        self.errors = errors
        self.partial = partial
        self.skipped = sorted(skipped)


class _Skipped(Exception):
    """Internal: a node cannot be evaluated because it (or an upstream node) failed."""


@dataclass
class _Keys:
    data: str
    full: str
    impl: str           # key of the impl result (data or full key)
    final: str | None   # key of the finalize output (representation nodes with finalize)
    params: dict        # normalized params
    data_params: dict
    client_params: dict


def evaluate(graph, *, registry, resolver, outputs=None, parameters=None, cache=None, budget=None, cancel=None,
             on_event=None):
    """Evaluate ``outputs`` (graph output names; default all) of an stk.graph/1 document.

    ``resolver`` maps binding names to file sources (a ``Resolver`` with
    ``resolve(name)``, or a mapping); ``cache`` is a :class:`GraphCache` (``None``
    = a private memory-only cache); ``budget``/``cancel`` limit the run;
    ``on_event`` receives ``{"type": "node.started" | "node.cached" |
    "node.finished" | "node.failed" | "progress" | "warning", "node": id, ...}``.
    Returns an :class:`EvaluationResult` (in-memory values; ``suan.graph.service``
    serializes them).
    """
    return _Evaluation(graph, registry=registry, resolver=resolver, outputs=outputs, parameters=parameters,
                       cache=cache, budget=budget, cancel=cancel, on_event=on_event).run()


class _Context:
    """The :class:`suan.graph.registry.NodeContext` given to impl/finalize/fingerprint/cached calls."""

    def __init__(self, evaluation, node_id, node_type, keys=None, params=None):
        self._evaluation = evaluation
        self._keys = keys
        self._params = params if params is not None else (keys.params if keys is not None else {})
        self.node_id = node_id
        self.node_type = node_type
        self.budget = evaluation.budget
        self.cancel = evaluation.cancel
        self.parameters = MappingProxyType(dict(evaluation.parameter_values))
        self.notes = {"choices": {}, "warnings": []}

    def __repr__(self):
        return f"NodeContext(node_id={self.node_id!r}, type={self.node_type.id!r})"

    @property
    def data_key(self):
        if self._keys is None:
            raise GraphError("unsupported", "data_key is not available inside fingerprint()", node=self.node_id)
        return self._keys.data

    @property
    def ancestors(self):
        """Ids of the nodes upstream of this one in the graph being evaluated (a frozenset)."""
        return self._evaluation.ancestors(self.node_id)

    @property
    def cache_dir(self):
        if self._keys is None:
            return None
        return self._evaluation.cache.scratch_dir(self._keys.data)

    def resolve(self, binding):
        return self._evaluation.resolve(binding, self.node_id)

    def check(self):
        self._evaluation.check()

    def progress(self, fraction=None, message=""):
        if fraction is not None:
            fraction = min(1.0, max(0.0, float(fraction)))
        self._evaluation.emit({"type": "progress", "node": self.node_id, "fraction": fraction,
                               "message": str(message)})

    def warn(self, message, *, code="node_warning", **details):
        issue = GraphIssue(code, str(message), "", self.node_id, None, "warning").to_dict()
        if details:
            try:
                issue["details"] = plain_json(details)
            except TypeError:
                issue["details"] = {key: repr(value) for key, value in details.items()}
        self.notes["warnings"].append(issue)
        self._evaluation.add_warning(issue)

    def report_choices(self, param, choices, *, value=None):
        raw = (self._evaluation.nodes[self.node_id].get("params") or {}).get(param)
        name = raw["$param"] if isinstance(raw, dict) and set(raw) == {"$param"} else f"{self.node_id}.{param}"
        if value is None:
            value = self._params.get(param)
        entry = {"value": plain_json(value), "choices": plain_json(list(choices))}
        self.notes["choices"][name] = entry
        self._evaluation.add_choices(name, entry)

    def cached(self, name, compute, *, disk=False):
        key = sub_key(self.data_key, str(name))
        disk = bool(disk) and self.node_type.deterministic and self.node_type.cache != "none"
        hit = self._evaluation.cache.get(key, disk=disk)
        if hit is not None:
            return hit.value["value"]
        value = freeze(compute())
        self._evaluation.cache.put(key, {"value": value}, disk=disk, label=f"{self.node_type.id}#{name}")
        return value


class _Evaluation:
    def __init__(self, graph, *, registry, resolver, outputs, parameters, cache, budget, cancel, on_event):
        check_graph(graph, registry, parameters=parameters)
        self.graph = graph
        self.registry = registry
        self.resolver = resolver
        self.requested = list(graph["outputs"]) if outputs is None else list(outputs)
        self.nodes = {node["id"]: node for node in graph["nodes"]}
        self.types = {node_id: registry[node["type"]] for node_id, node in self.nodes.items()}
        self.parameter_values = parameter_values(graph, parameters)
        self.cache = cache if cache is not None else GraphCache()
        self.budget = budget if budget is not None else Budget()
        self.cancel = cancel if cancel is not None else CancelToken()
        self.on_event = on_event
        self.started = time.monotonic()
        self.rss0 = _rss() if self.budget.max_memory_mb is not None else None
        self.sources = {}
        self.keys = {}
        self.links = {node_id: self._node_links(node) for node_id, node in self.nodes.items()}
        self._ancestors = {}
        self.done = {}
        self.failed = {}     # node id -> issue dict (root causes)
        self.skipped = set()  # nodes not evaluated because an upstream node failed
        self.replayed = set()  # cache keys whose notes (choices, warnings) were replayed
        self.fresh_choices = set()  # choice names reported by a node during this evaluation
        self.result = EvaluationResult(graph_hash=graph_hash(graph))
        for name, value in self.parameter_values.items():
            self.result.parameters[name] = {"value": _plain(value)}
        self._event_error = False

    # -- helpers used by the context ---------------------------------------------

    def emit(self, event):
        if self.on_event is None:
            return
        try:
            self.on_event(event)
        except Exception as exc:  # a broken listener must not break the evaluation
            if not self._event_error:
                self._event_error = True
                self.result.warnings.append(GraphIssue("event_callback_failed", f"on_event raised {exc!r}",
                                                       severity="warning").to_dict())

    def add_warning(self, issue):
        if issue not in self.result.warnings:
            self.result.warnings.append(issue)
        self.emit({"type": "warning", "node": issue.get("node"), "code": issue["code"], "message": issue["message"]})

    def add_choices(self, name, entry, *, replayed=False):
        if replayed and name in self.fresh_choices:
            return  # a cached note never overrides what a node reported now (live runs grow)
        if not replayed:
            self.fresh_choices.add(name)
        self.result.parameters[name] = dict(entry)

    def check(self):
        self.cancel.raise_if_cancelled()
        limit = self.budget.max_seconds
        if limit is not None and time.monotonic() - self.started > limit:
            raise BudgetExceeded(f"The evaluation exceeded its time budget of {limit:g} s")
        if self.rss0 is not None:
            grown = (_rss() - self.rss0) / 2**20
            if grown > self.budget.max_memory_mb:
                raise BudgetExceeded(f"The evaluation grew memory by {grown:.0f} MiB; the budget is "
                                     f"{self.budget.max_memory_mb} MiB")

    def resolve(self, binding, node_id):
        if binding in self.sources:
            return self.sources[binding]
        hint = (f"Bind it, e.g. `suan graph run ... --bind {binding}=DIR` or request bindings "
                f"{{\"{binding}\": {{\"task_id\": ...}}}}")
        if self.resolver is None:
            raise GraphError("unknown_binding", f"Binding '{binding}' is not bound (no resolver)", node=node_id,
                             hint=hint)
        try:
            source = self.resolver[binding] if isinstance(self.resolver, Mapping) else self.resolver.resolve(binding)
        except KeyError:
            raise GraphError("unknown_binding", f"Binding '{binding}' is not bound", node=node_id, hint=hint) from None
        with_check = getattr(source, "with_check", None)
        if callable(with_check):  # e.g. Runtime downloads check cancellation and the budget between chunks
            source = with_check(self.check)
        self.sources[binding] = source
        return source

    # -- main loop -----------------------------------------------------------------

    def run(self):
        order = topological_order(self.graph, self.requested)
        self.order = order
        try:
            for node_id in order:
                if any(up in self.failed or up in self.skipped for up in self._upstream(node_id)):
                    self.skipped.add(node_id)
                    continue
                try:
                    self._prepare(node_id)
                except (Cancelled, BudgetExceeded) as exc:
                    _attribute(exc, node_id)
                    raise
                except _Skipped:
                    self.skipped.add(node_id)
                except Exception as exc:
                    self._fail(node_id, exc)
            for name in self.requested:
                node_id, port = parse_port_ref(self.graph["outputs"][name])
                try:
                    value = self._materialize(node_id)[port]
                except _Skipped:
                    continue
                self.result.outputs[name] = value
                self.result.output_types[name] = self.types[node_id].output(port).type
            limit = self.budget.max_output_bytes
            if limit is not None:
                size = sum(estimate_nbytes(value) for value in self.result.outputs.values())
                if size > limit:
                    raise BudgetExceeded(f"The outputs hold about {size} bytes; the budget is {limit} bytes")
        except (Cancelled, BudgetExceeded) as exc:
            exc.partial = self.result
            self.emit({"type": "node.failed", "node": exc.node, "code": exc.code, "message": exc.message})
            raise
        if self.failed:
            errors = list(self.failed.values())
            raise EvaluationFailed(errors, self.result, self._failed_descendants())
        return self.result

    def _node_links(self, node):
        links = {}
        for port, entry in (node.get("inputs") or {}).items():
            items = entry if isinstance(entry, list) else [entry]
            links[port] = [parse_port_ref(item["from"]) for item in items]
        return links

    def ancestors(self, node_id):
        """Every node upstream of ``node_id`` (transitively) in this graph."""
        memo = self._ancestors
        if node_id not in memo:
            found, stack = set(), list(self._upstream(node_id))
            while stack:
                current = stack.pop()
                if current not in found:
                    found.add(current)
                    stack.extend(memo[current] if current in memo else self._upstream(current))
            memo[node_id] = frozenset(found)
        return memo[node_id]

    def _upstream(self, node_id):
        seen, result = set(), []
        for pairs in self.links[node_id].values():
            for source, _ in pairs:
                if source not in seen:
                    seen.add(source)
                    result.append(source)
        return result

    def _failed_descendants(self):
        """Needed nodes that were not evaluated because an upstream node failed."""
        blocked = set(self.failed)
        for node_id in self.order:
            if node_id not in blocked and any(up in blocked for up in self._upstream(node_id)):
                blocked.add(node_id)
        return {node_id for node_id in blocked if node_id not in self.failed and node_id not in self.done}

    def _fail(self, node_id, exc):
        error = _node_error(node_id, exc)
        issue = error.to_issue().to_dict()
        issue["node"] = error.node or node_id
        self.failed.setdefault(node_id, issue)
        self.emit({"type": "node.failed", "node": node_id, "code": issue["code"], "message": issue["message"]})

    # -- keys ----------------------------------------------------------------------

    def _prepare(self, node_id):
        self.check()
        node, node_type = self.nodes[node_id], self.types[node_id]
        params = node_type.normalize_params(substitute_params(node.get("params") or {}, self.parameter_values))
        if params.get("profile") == "auto" and "profile" in node_type.params and self.budget.profile:
            # "auto" means the request profile; the key names the effective profile (spec §5).
            params = {**params, "profile": self.budget.profile}
        data_params, client_params = node_type.split_params(params)
        data_inputs, full_inputs = {}, {}
        for port, pairs in self.links[node_id].items():
            data_inputs[port] = [f"{self.keys[up].data}:{up_port}" for up, up_port in pairs]
            full_inputs[port] = [f"{self.keys[up].full}:{up_port}" for up, up_port in pairs]
        source = None
        key_params = data_params
        if node_type.fingerprint is not None and node_type.cache != "none":
            inputs = self._inputs(node_id)
            context = _Context(self, node_id, node_type, None, params)  # data_key is not known yet
            fingerprint = node_type.fingerprint(context, inputs, params)
            try:
                source = plain_json(fingerprint)
            except TypeError as exc:
                raise NodeExecutionError(f"fingerprint() returned a value that is not plain JSON: {exc}",
                                         node=node_id) from None
            if node_type.stage == "source":
                # Keyed by the resolved content: selectors (step/policy) and the upstream keys (the growing
                # frame listing of a live run) are left out, so aliases share an entry (spec §5).
                key_params = {name: value for name, value in data_params.items() if name not in node_type.selectors}
                data_inputs, full_inputs = {}, {}
        ids = None
        if node_type.stage in ID_STAGES:
            # Their values carry node ids (layer ids and pick targets, the scene title, export names), and
            # every other key is content-only: a graph naming its nodes differently must not get these
            # values from the cache of another graph (spec §5).
            ids = {"node": node_id}
            if node_type.stage == "representation":
                ids["upstream"] = sorted(self.ancestors(node_id))
        data = make_data_key(node_type.id, node_type.impl_version, key_params, data_inputs, source, ids)
        full = make_full_key(data, client_params, full_inputs)
        impl = data if node_type.keyed_by_data else full
        final = None
        if node_type.stage == "representation" and node_type.finalize is not None:
            final = sub_key(full, "finalize")
        self.keys[node_id] = _Keys(data, full, impl, final, params, data_params, client_params)
        self.result.keys[node_id] = {"data": data, "full": full}
        if node_type.cache != "none" and node_type.impl is not None:
            # Choices and warnings belong to the key: replay them even if the value is never loaded
            # (a cached downstream output makes this node's value unnecessary).
            self._replay(self.cache.notes(impl, disk=self._disk(node_type)), impl)
            if final is not None:
                self._replay(self.cache.notes(final, disk=False), final)

    # -- values --------------------------------------------------------------------

    def _available(self, node_id):
        node_type, keys = self.types[node_id], self.keys[node_id]
        if node_type.cache == "none" or node_type.impl is None:
            return False
        if keys.final is not None and self.cache.contains(keys.final, disk=False):
            return True
        return self.cache.contains(keys.impl, disk=self._disk(node_type)) is not None

    def _disk(self, node_type):
        return node_type.cache == "disk" and node_type.deterministic

    def _materialize(self, target):
        if target in self.done:
            return self.done[target]
        if target in self.failed or target in self.skipped or target not in self.keys:
            raise _Skipped(target)
        plan, planned = [], set()
        stack = [(target, False)]
        while stack:
            node_id, expanded = stack.pop()
            if node_id in planned or node_id in self.done:
                continue
            if node_id in self.failed or node_id in self.skipped or node_id not in self.keys:
                self._skip_downstream(target)
                raise _Skipped(node_id)
            if expanded or self._available(node_id):
                planned.add(node_id)
                plan.append(node_id)
                continue
            stack.append((node_id, True))
            for up in reversed(self._upstream(node_id)):
                stack.append((up, False))
        for node_id in plan:
            if node_id in self.done:
                continue
            try:
                self.done[node_id] = self._compute(node_id)
            except (Cancelled, BudgetExceeded) as exc:
                _attribute(exc, node_id)
                raise
            except _Skipped:
                self._skip_downstream(target)
                raise
            except Exception as exc:
                self._fail(node_id, exc)
                self._skip_downstream(target)
                raise _Skipped(node_id) from None
        return self.done[target]

    def _skip_downstream(self, target):
        if target not in self.failed:
            self.skipped.add(target)

    def _inputs(self, node_id):
        node_type = self.types[node_id]
        inputs = {}
        for port in node_type.inputs:
            pairs = self.links[node_id].get(port.name)
            if not pairs:
                continue
            values = []
            for up, up_port in pairs:
                value = self._materialize(up)[up_port]
                _check_input_kind(node_id, port, value, up)
                values.append(value.copy() if _is_dataset(value) else value)
            inputs[port.name] = values if port.multi else values[0]
        return inputs

    def _compute(self, node_id):
        self.check()
        node_type, keys = self.types[node_id], self.keys[node_id]
        start = time.monotonic()
        position = {"index": self.order.index(node_id) + 1, "total": len(self.order)}
        if node_type.impl is None:
            raise GraphError("unsupported", f"'{node_type.id}' is declared but no implementation is installed",
                             node=node_id, hint="Install the package that implements this node type")
        cacheable = node_type.cache != "none"
        disk = self._disk(node_type)
        if keys.final is not None and cacheable:
            hit = self.cache.get(keys.final, disk=False)
            if hit is not None:
                return self._hit(node_id, hit, start, position, keys.final)
        hit = self.cache.get(keys.impl, disk=disk) if cacheable else None
        if hit is not None:
            outputs = hit.value
            self._replay(hit.notes, keys.impl)
            cached_tier = hit.tier
        else:
            inputs = self._inputs(node_id)
            self.check()
            self.emit({"type": "node.started", "node": node_id, "node_type": node_type.id, **position})
            context = _Context(self, node_id, node_type, keys)
            params = keys.data_params if node_type.stage == "representation" else keys.params
            outputs = node_type.wrap_outputs(node_type.impl(context, inputs, params))
            _check_outputs(node_id, node_type, outputs)
            freeze(outputs)
            if cacheable:
                self.cache.put(keys.impl, outputs, notes=context.notes, disk=disk, label=node_type.id)
            self.result.evaluated.append(node_id)
            self.result.cache["misses"] += 1
            cached_tier = None
        if keys.final is not None:
            context = _Context(self, node_id, node_type, keys)
            final = node_type.finalize(context, dict(outputs), dict(keys.client_params))
            if not isinstance(final, Mapping) or set(final) != set(outputs):
                raise GraphError("bad_outputs", f"finalize() of '{node_type.id}' must return the ports "
                                 f"{', '.join(outputs)}", node=node_id)
            outputs = freeze(dict(final))
            if cacheable:
                self.cache.put(keys.final, outputs, notes=context.notes, disk=False)
        elapsed = time.monotonic() - start
        self.result.timings[node_id] = elapsed
        if cached_tier is not None:
            self.result.cache["hits"] += 1
            self.emit({"type": "node.cached", "node": node_id, "tier": cached_tier, "key": keys.impl,
                       "finalized": keys.final is not None, **position})
        else:
            self.emit({"type": "node.finished", "node": node_id, "seconds": elapsed, "key": keys.impl, **position})
        return outputs

    def _hit(self, node_id, hit, start, position, key):
        self._replay(hit.notes, key)
        self.result.cache["hits"] += 1
        self.result.timings[node_id] = time.monotonic() - start
        self.emit({"type": "node.cached", "node": node_id, "tier": hit.tier, "key": key, **position})
        return hit.value

    def _replay(self, notes, key):
        if not isinstance(notes, Mapping) or key in self.replayed:
            return
        self.replayed.add(key)
        for name, entry in (notes.get("choices") or {}).items():
            self.add_choices(name, entry, replayed=True)
        for issue in notes.get("warnings") or ():
            self.add_warning(issue)


# ---------------------------------------------------------------------------
# Checks and error mapping


def _is_dataset(value):
    return hasattr(value, "kinds") and hasattr(value, "fields") and hasattr(value, "copy")


def _kinds_of(value):
    try:
        return frozenset(value.kinds())
    except Exception:
        return frozenset()


def _check_input_kind(node_id, port, value, upstream):
    types = port.types
    if not any(t in _DATASET_PORTS for t in types):
        return
    if not _is_dataset(value):
        if all(t in _DATASET_PORTS for t in types):
            raise GraphError("kind_mismatch", f"Input '{port.name}' expects a dataset; '{upstream}' produced "
                             f"{type(value).__name__}", node=node_id)
        return
    accepts = port.accepts
    if accepts is None and "table" in types and "dataset" not in types:
        accepts = ("table",)
    if accepts:
        kinds = _kinds_of(value)
        if not any(is_subkind(kind, accepted) for kind in kinds for accepted in accepts):
            raise GraphError("kind_mismatch", f"Input '{port.name}' accepts {', '.join(accepts)}; '{upstream}' "
                             f"produced a {', '.join(sorted(kinds)) or 'dataset of unknown kind'}", node=node_id,
                             hint="Insert a node that converts the data (e.g. a classifier for 'labels')")


def _check_outputs(node_id, node_type, outputs):
    for port in node_type.outputs:
        if port.type not in _DATASET_PORTS:
            continue
        value = outputs[port.name]
        if not _is_dataset(value):
            raise GraphError("bad_outputs", f"'{node_type.id}' output '{port.name}' must be a dataset, got "
                             f"{type(value).__name__}", node=node_id)
        declared = port.kinds if not port.kind_from else None
        if declared:
            kinds = _kinds_of(value)
            if not any(is_subkind(kind, allowed) for kind in kinds for allowed in declared):
                raise GraphError("bad_outputs", f"'{node_type.id}' output '{port.name}' must be "
                                 f"{' or '.join(declared)}, got {', '.join(sorted(kinds)) or 'unknown'}", node=node_id)


def _attribute(exc, node_id):
    if getattr(exc, "node", None) is None:
        exc.node = node_id


def _node_error(node_id, exc):
    if isinstance(exc, GraphError):
        if exc.node is None:
            exc.node = node_id
        return exc
    if isinstance(exc, FileNotFoundError):
        return GraphError("missing_file", str(exc) or "File not found", node=node_id)
    code = getattr(exc, "code", None)
    if type(exc).__name__ == "ConnectorError" and isinstance(code, str):
        return GraphError("missing_file" if code == "not_found" else code, str(exc), node=node_id)
    if isinstance(exc, NotImplementedError):
        return GraphError("unsupported", str(exc) or "Not implemented", node=node_id)
    if isinstance(exc, MemoryError):
        return BudgetExceeded("The node ran out of memory", node=node_id)
    return NodeExecutionError(f"{type(exc).__name__}: {exc}", node=node_id)


def _plain(value):
    try:
        return plain_json(value)
    except TypeError:
        return repr(value)


def _rss():
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except Exception:  # pragma: no cover - psutil is a base dependency
        return 0
