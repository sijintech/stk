# SPDX-License-Identifier: GPL-2.0-or-later
"""Portable HTTP protocol fixture for native run controls; never executes a solver.

Real Runtime execution is covered by tests/test_project_runs.py on Linux. This peer lets the
same native button/bridge/HTTP assertions run on Windows and macOS without a server install.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from socketserver import TCPServer
import threading
from uuid import uuid4


class Peer:
    def __init__(self):
        self.tasks = {}
        self.submit_count = self.cancel_count = 0
        peer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, result, status=200):
                data = json.dumps(result).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/v1/health":
                    self.reply({"features": ["input_checksums"]})
                elif self.path.startswith("/v1/tasks/"):
                    task = next((task for task in peer.tasks.values() if self.path == "/v1/tasks/" + task["id"]), None)
                    self.reply(task or {"error": "unknown task"}, 200 if task else 404)
                else:
                    self.reply({"error": "unknown path"}, 404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/v1/tasks":
                    peer.submit_count += 1
                    key = body["idempotency_key"]
                    if key not in peer.tasks:
                        peer.tasks[key] = {"id": uuid4().hex, "state": "queued", "spec": body["spec"]}
                    self.reply(peer.tasks[key])
                elif self.path.endswith("/cancel"):
                    task = next((task for task in peer.tasks.values() if self.path == "/v1/tasks/" + task["id"] + "/cancel"), None)
                    if task:
                        peer.cancel_count += 1
                        task["state"] = "cancelled"
                    self.reply(task or {"error": "unknown task"}, 200 if task else 404)
                else:
                    self.reply({"error": "unknown path"}, 404)

        class LoopbackServer(HTTPServer):
            def server_bind(self):
                # HTTPServer normally performs socket.getfqdn even for 127.0.0.1. This
                # protocol fixture has no hostname-dependent behavior and must not wait on
                # the runner's reverse DNS (notably slow/unavailable on some macOS hosts).
                TCPServer.server_bind(self)
                self.server_name = "localhost"
                self.server_port = self.server_address[1]

        self.server = LoopbackServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
