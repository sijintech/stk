"""Private subprocess entry point for desktop graph evaluation (not a bridge protocol endpoint)."""
import argparse
import os
from pathlib import Path
import queue
import threading

from .protocol import BridgeError, MAX_LINE_BYTES, decode_line, encode_message


def evaluate(params, cache_dir, progress, cancel):
    from suan.graph.catalog import default_registry
    from suan.graph.registry import GraphError
    from suan.graph.resolve import BindingResolver, LocalDirResolver, RuntimeResolver
    from suan.graph.service import DirectoryBlobSink, evaluate_request
    from suan.runtime.client import RuntimeClient
    from .graphs import _graph_error

    resolvers = []
    try:
        if params.get("local_bindings"):
            resolvers.append(LocalDirResolver(params["local_bindings"]))
        if params.get("runtime"):
            runtime = params["runtime"]
            client = RuntimeClient(runtime["url"], runtime["token"], timeout=runtime["timeout"])
            resolvers.append(RuntimeResolver(client, cache_dir / "graph" / "downloads"))
        return evaluate_request(params["request"], resolver=BindingResolver(*resolvers) if resolvers else None,
                                cache_dir=cache_dir / "graph" / "cache",
                                blob_sink=DirectoryBlobSink(cache_dir / "blobs"),
                                registry=default_registry(), on_event=progress, cancel=cancel)
    except GraphError as exc:
        raise _graph_error(exc) from None


def main():
    from .__main__ import _protocol_stdin, _protocol_stdout
    from .graphs import _plain_event
    from suan.graph.registry import CancelToken

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True)
    args = parser.parse_args()
    writer, reader = _protocol_stdout(), _protocol_stdin()
    inbox = queue.Queue(maxsize=1)
    active_lock = threading.Lock()
    active = {}

    def read_requests():
        try:
            while True:
                line = reader.readline(MAX_LINE_BYTES + 1)
                if not line or len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
                    break
                message = decode_line(line)
                with active_lock:
                    if "cancel" in message:
                        if active.get("id") == message["cancel"]:
                            active["token"].cancel("Cancelled by the desktop app")
                        continue
                    token = CancelToken()
                    active.update(id=message["id"], token=token)
                inbox.put((message, token))
        finally:
            # Parent EOF also ends a busy worker, instead of leaving an orphan evaluation behind.
            os._exit(0)

    threading.Thread(target=read_requests, daemon=True, name="stk-graph-parent").start()

    def send(message):
        line = encode_message(message)
        if len(line) > MAX_LINE_BYTES:
            if "event" in message:
                return
            line = encode_message({"id": message["id"], "error": BridgeError(
                "result_too_large", "The graph result exceeds the bridge message limit").to_json()})
        writer.write(line)
        writer.flush()

    while True:
        message, token = inbox.get()
        identity = message["id"]
        try:
            result = evaluate(message["params"], Path(args.cache_dir),
                              lambda event: send({"id": identity, "event": _plain_event(event)}), token)
        except BridgeError as exc:
            send({"id": identity, "error": exc.to_json()})
        except Exception as exc:
            send({"id": identity, "error": BridgeError(
                "internal_error", f"{type(exc).__name__}: {exc}").to_json()})
        else:
            send({"id": identity, "result": result})
        finally:
            with active_lock:
                if active.get("token") is token:
                    active.clear()


if __name__ == "__main__":
    main()
