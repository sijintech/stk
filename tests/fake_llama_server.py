"""A stand-in for llama.cpp's llama-server in tests: /health and OpenAI-compatible chat completions on loopback.

Accepts the arguments STK passes (-m, --host, --port, --alias, ...) and records them in ``<model>.args.json``.
``--fail`` in the model file's name makes it exit at once (a server that cannot start).
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import socketserver
import sys

args = sys.argv[1:]
value = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i].startswith("-")}
model = Path(value["-m"])
model.with_name(model.name + ".args.json").write_text(json.dumps(args))
model.with_name(model.name + ".env.json").write_text(json.dumps(dict(os.environ)))
if "fail" in model.name:
    sys.exit(3)
if "die" in model.name:  # healthy at first, then exits by itself
    import threading
    threading.Timer(1.5, os._exit, (4,)).start()
alias = value.get("--alias", "model")
KEY = os.environ.get("LLAMA_API_KEY", "")
REPLY = "Domain walls move under the applied field."


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, status, data, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, b'{"status":"ok"}', "application/json")
        else:
            self._send(404, b"{}", "application/json")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if KEY and self.headers.get("Authorization") != f"Bearer {KEY}":  # as llama-server with LLAMA_API_KEY
            self._send(401, b'{"error":{"code":401,"message":"Invalid API Key"}}', "application/json")
            return
        if body.get("stream"):
            chunks = [{"role": "assistant", "content": None}, {"content": REPLY}]
            events = [{"object": "chat.completion.chunk", "model": alias, "choices": [{"index": 0, "delta": d, "finish_reason": None}]} for d in chunks]
            events.append({"object": "chat.completion.chunk", "model": alias, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            data = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n\n"
            self._send(200, data, "text/event-stream")
        else:
            data = json.dumps({"object": "chat.completion", "model": alias, "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": REPLY}}]}).encode()
            self._send(200, data, "application/json")


class Server(HTTPServer):
    def server_bind(self):  # without HTTPServer's reverse DNS lookup of the host, which can stall on macOS
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


Server((value.get("--host", "127.0.0.1"), int(value["--port"])), Handler).serve_forever()
