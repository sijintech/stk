"""Authenticated loopback HTTP API. Large transfers use bounded chunks."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
import hmac
import json
import signal
import threading

from .common import atomic_json, identity, instance_lock, load_config
from .service import CHUNK_SIZE, RuntimeService


class RuntimeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, config):
        self.service = RuntimeService(config)
        self.config = config
        # Binding a public address is intentionally not a configurable option.
        super().__init__(("127.0.0.1", config["port"]), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "STKRuntime/1"

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, *_):
        pass  # URLs may contain user paths; application logs are task-scoped.

    def respond(self, data, code=200):
        binary = isinstance(data, bytes)
        body = data if binary else json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/octet-stream" if binary else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def dispatch(self):
        try:
            token = self.headers.get("Authorization", "")
            if not hmac.compare_digest(token.encode(), ("Bearer " + self.server.config["token"]).encode()):
                self.respond({"error": "Unauthorized"}, 401)
                return
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Use Content-Length and bounded upload chunks")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= (CHUNK_SIZE if self.command == "PUT" else 4 * CHUNK_SIZE):
                self.respond({"error": "Request body is too large"}, 413)
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete request body")
            url = urlsplit(self.path)
            parts = [unquote(p) for p in url.path.strip("/").split("/")]
            if parts[:3] == ["v1", "federation", "owner"]:
                from suan.federation.owner import OwnerConflict, OwnerRequestRejected, decode_request
                try:
                    if (self.command != "POST" or len(parts) != 4 or url.query
                            or self.server.service.federation_owner is None):
                        self.respond({"error": "Route not found"}, 404)
                    else:
                        # This must precede generic json.loads: duplicate keys,
                        # nonfinite values and private errors cannot escape here.
                        result = self.server.service.federation_owner.call(parts[3], decode_request(raw))
                        self.respond(result)
                except OwnerRequestRejected as exc:
                    self.respond({"error": "Federation owner request rejected before reservation",
                                  "rejection": exc.rejection}, 409)
                except OwnerConflict:
                    self.respond({"error": "Federation owner identity or original request conflicts"}, 409)
                except (ValueError, TypeError):
                    self.respond({"error": "Invalid federation owner request or unavailable private evidence"}, 400)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception:
                    self.respond({"error": "Federation owner operation requires evidence review"}, 500)
                return
            data = json.loads(raw) if raw and self.command != "PUT" else {}
            if not isinstance(data, dict):
                raise ValueError("Request JSON must be an object")
            query = parse_qs(url.query)
            value = lambda name, default="": query.get(name, [default])[0]
            service = self.server.service
            method = self.command
            if parts == ["v1", "health"] and method == "GET":
                from .common import alive, read_json
                from .models import RESOURCES
                self.respond({"api_version": 1, "status": "ok", "backends": ["local", "pbs", "slurm"],
                              "resources": sorted(RESOURCES), "argv_tokens": ["{python}", "{ranks}", "{threads_per_rank}", "{nodes}"],
                              "features": ["events", "input_checksums"] + (["federation_owner"] if service.federation_owner is not None else []),
                              "supervisor_running": alive(read_json(Path(self.server.config["state_dir"]) / "supervisor.pid"))})
            elif parts == ["v1", "workspaces"] and method in {"GET", "POST"}:
                self.respond(service.store.workspaces() if method == "GET" else service.create_workspace(data["name"], data.get("idempotency_key")))
            elif parts == ["v1", "tasks"] and method in {"GET", "POST"}:
                if method == "POST":
                    self.respond(service.submit(data["spec"], data["idempotency_key"]), 202)
                else:
                    self.respond(service.store.tasks(value("workspace_id") or None))
            elif len(parts) >= 3 and parts[:2] == ["v1", "tasks"]:
                task_id = parts[2]
                action = parts[3] if len(parts) == 4 else ""
                if len(parts) == 3 and method == "GET":
                    self.respond(service.task(task_id))
                elif action == "cancel" and method == "POST":
                    self.respond(service.cancel(task_id))
                elif action == "logs" and method == "GET":
                    self.respond(service.logs(task_id, value("stream", "stdout"), int(value("offset", "0")), int(value("limit", str(CHUNK_SIZE)))))
                elif action == "events" and method == "GET":
                    self.respond(service.events(task_id, int(value("offset", "0")), int(value("limit", str(CHUNK_SIZE)))))
                elif action == "artifacts" and method == "GET":
                    self.respond(service.artifacts(task_id))
                elif action == "file" and method == "GET":
                    self.respond(service.file_chunk(service.task_dir(task_id) / "work", value("path"), int(value("offset", "0")), int(value("limit", str(CHUNK_SIZE)))))
                else:
                    self.respond({"error": "Route not found"}, 404)
            elif len(parts) >= 4 and parts[:2] == ["v1", "workspaces"]:
                workspace_id, action = parts[2:4]
                if len(parts) == 4 and action == "files" and method == "GET":
                    self.respond(service.list_files(workspace_id))
                elif len(parts) == 4 and action == "file" and method == "GET":
                    self.respond(service.file_chunk(service.workspace_dir(workspace_id) / "inputs", value("path"), int(value("offset", "0")), int(value("limit", str(CHUNK_SIZE)))))
                elif action == "uploads":
                    if len(parts) == 4 and method == "POST":
                        self.respond(service.begin_upload(workspace_id, data["path"], data["size"], data["sha256"]))
                    elif len(parts) == 5 and method == "GET":
                        self.respond(service.upload_status(workspace_id, parts[4]))
                    elif len(parts) == 5 and method == "PUT":
                        self.respond(service.upload_chunk(workspace_id, parts[4], int(value("offset", "0")), raw))
                    elif len(parts) == 5 and method == "DELETE":
                        self.respond(service.abort_upload(workspace_id, parts[4]))
                    elif len(parts) == 6 and parts[5] == "finish" and method == "POST":
                        self.respond(service.finish_upload(workspace_id, parts[4]))
                    else:
                        self.respond({"error": "Route not found"}, 404)
                else:
                    self.respond({"error": "Route not found"}, 404)
            else:
                self.respond({"error": "Route not found"}, 404)
        except KeyError as exc:
            self.respond({"error": str(exc)}, 404)
        except (ValueError, TypeError) as exc:
            self.respond({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            import logging
            logging.exception("Runtime API request failed")
            self.respond({"error": "Runtime operation failed; inspect api.log"}, 500)

    do_GET = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_DELETE = dispatch


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args()
    config = load_config(args.state_dir)
    state = Path(config["state_dir"])
    with instance_lock(state / "api.lock"), RuntimeHTTPServer(config) as server:
        atomic_json(state / "api.pid", {**identity(), "port": server.server_port})
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
        server.serve_forever(poll_interval=0.2)


if __name__ == "__main__":
    main()
