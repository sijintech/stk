"""Private persistent Python console worker; arbitrary trusted user code, not a sandbox."""
import ast
import io
import os
import queue
import sys
import threading
import traceback

from suan.scripting import API, ScriptError
from .protocol import MAX_LINE_BYTES, decode_line, encode_message


def main():
    from .__main__ import _protocol_stdin, _protocol_stdout

    writer, reader = _protocol_stdout(), _protocol_stdin()
    write_lock = threading.Lock()
    pending_lock = threading.Lock()
    pending = {}
    inbox = queue.Queue(maxsize=1)
    execution_thread = threading.get_ident()
    active = {"id": None}
    sequence = 0

    def send(message):
        line = encode_message(message)
        if len(line) > MAX_LINE_BYTES:
            raise ValueError("Script operation exceeds the bridge message limit")
        with write_lock:
            writer.write(line)
            writer.flush()

    def read_requests():
        try:
            while True:
                line = reader.readline(MAX_LINE_BYTES + 1)
                if not line or len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
                    break
                message = decode_line(line)
                if "reply" in message:
                    with pending_lock:
                        response = pending.get(message["reply"])
                    if response is not None:
                        response.put(message)
                else:
                    inbox.put(message)
        finally:
            # EOF must also stop a script stuck in Python/native code and its subprocesses.
            try:
                import psutil
                for child in psutil.Process().children(recursive=True):
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            finally:
                os._exit(0)

    def call(operation, params):
        nonlocal sequence
        if threading.get_ident() != execution_thread or active["id"] is None:
            raise RuntimeError("STK operations must run on the console execution thread")
        sequence += 1
        identity, response = sequence, queue.Queue(maxsize=1)
        with pending_lock:
            pending[identity] = response
        try:
            send({"id": active["id"], "call": identity, "operation": operation, "params": params})
            result = response.get()
            if "error" in result:
                raise ScriptError(result["error"])
            return result["result"]
        finally:
            with pending_lock:
                pending.pop(identity, None)

    class Output(io.TextIOBase):
        @property
        def encoding(self):
            return "utf-8"

        def writable(self):
            return True

        def write(self, value):
            if not isinstance(value, str):
                raise TypeError("Console output must be text")
            # All Python threads can print; only the execution thread may invoke operations.
            for offset in range(0, len(value), 4096):
                send({"output": value[offset:offset + 4096]})
            return len(value)

        def flush(self):
            pass

    output = Output()
    sys.stdout = sys.stderr = output
    api = API(call)
    namespace = {"__name__": "__console__", "stk": api}
    threading.Thread(target=read_requests, daemon=True, name="stk-script-parent").start()
    while True:
        message = inbox.get()
        identity = message["id"]
        active["id"] = identity
        api._project_handle = message.get("project_handle")
        namespace["stk"] = api
        filename = message["filename"]
        if filename != "<console>":
            namespace["__file__"] = filename
        else:
            namespace.pop("__file__", None)
        # Restore capture if a previous script replaced sys.stdout/stderr.
        sys.stdout = sys.stderr = output
        succeeded = False
        try:
            tree = ast.parse(message["source"], filename=filename, mode="exec")
            last = tree.body.pop() if filename == "<console>" and tree.body and isinstance(tree.body[-1], ast.Expr) else None
            exec(compile(tree, filename, "exec"), namespace)
            if last is not None:
                value = eval(compile(ast.Expression(last.value), filename, "eval"), namespace)
                namespace["_"] = value
                if value is not None:
                    output.write(repr(value) + "\n")
            succeeded = True
        except BaseException:
            traceback.print_exc(file=output)
        finally:
            active["id"] = None
            send({"id": identity, "finished": succeeded})


if __name__ == "__main__":
    main()
