"""The fault injector of the D1 X7 socket-partition scenario (CL-D1-X7-SOCKET-PARTITION-64): a small loopback TCP
relay between this run's own NodeAgent and its Hub. Standard library only; loaded by ``disconnect.py`` by file path.

The relay listens on 127.0.0.1 only, on one port for its whole life, and forwards each accepted connection (a
"tunnel") to the Hub's loopback port. The NodeAgent is paired with the relay's address, so from the pairing onward
its HTTP calls and its WebSocket control link pass through here; the harness's own Hub and Runtime clients never do.

* ``cut()`` closes every active tunnel at once (both sockets are shut down) and rejects every new one: an accepted
  connection is closed at once, before anything is forwarded. No process is signalled.
* ``reopen()`` lets the same listening socket, on the same address, forward new tunnels again.

Only counts, ages and booleans are reported; no address, header or payload is ever kept or exported.
"""
import select
import socket
import socketserver
import threading
import time

LOOPBACK = "127.0.0.1"
CONNECT_TIMEOUT = 2  # seconds to reach the Hub's loopback port for one new tunnel
DRAIN_WAIT = 5  # seconds cut() waits for the closed tunnels' forwarding threads to end


class Relay(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, upstream_port):
        self.upstream = (LOOPBACK, int(upstream_port))
        self.lock = threading.Lock()
        self.forwarding = True
        self.generation = 0
        self.requests = {}  # node socket -> generation, including pending upstream connects
        self.lanes = {}  # serial -> {"sockets", "opened", "last_from_node", "from_node", "to_node", "cut"}
        self.counts = {"accepted": 0, "rejected": 0, "closed_by_cut": 0}
        self._serial = 0
        super().__init__((LOOPBACK, 0), _Tunnel)
        self.port = self.server_address[1]
        self.thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True,
                                       name="x7-socket-relay")
        self.thread.start()

    @property
    def url(self):
        return f"http://{LOOPBACK}:{self.port}"

    def handle_error(self, request, client_address):
        """A tunnel's own failure is the expected end of a cut; nothing (no exception text) is printed."""

    def process_request(self, request, client_address):
        with self.lock:
            forward = self.forwarding
            if forward:
                self.requests[request] = self.generation
            else:
                self.counts["rejected"] += 1
        if not forward:
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            with self.lock:
                self.requests.pop(request, None)
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.lock:
                self.requests.pop(request, None)

    def stats(self):
        with self.lock:
            return {**self.counts, "active": len(self.lanes), "forwarding": self.forwarding,
                    "listening": self.thread.is_alive(), "port": self.port}

    def cut(self, submitted_at=None):
        """Stop forwarding and close every active tunnel. ``submitted_at`` (monotonic) is when the scenario
        submitted its task: a closed tunnel opened before it that still carried bytes from the node after it, and
        bytes to the node, was the live control link of that task."""
        with self.lock:
            now = time.monotonic()
            self.forwarding = False
            self.generation += 1
            prior_requests = set(self.requests)
            active = list(self.lanes.values())
            traffic = [(lane["opened"], lane["last_from_node"], lane["to_node"]) for lane in active]
            for lane in active:
                lane["cut"] = True
            accepted = self.counts["accepted"]
            rejected = self.counts["rejected"]
            self.counts["closed_by_cut"] += len(active)
        peers = prior_requests | {lane["sockets"][1] for lane in active}
        for peer in peers:
            try:
                peer.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        deadline = time.monotonic() + DRAIN_WAIT
        while time.monotonic() < deadline:
            with self.lock:
                if not prior_requests.intersection(self.requests):
                    break
            time.sleep(0.05)
        with self.lock:
            drained = not prior_requests.intersection(self.requests)
        mark = now if submitted_at is None else submitted_at
        older = [sample for sample in traffic if sample[0] < mark]
        return {"closed": len(active), "closed_opened_before_submission": len(older),
                "oldest_closed_age_seconds": round(max((now - opened for opened, _, _ in traffic), default=0.0), 1),
                "live_link_closed": any(last_from_node is not None and last_from_node > mark and to_node > 0
                                        for _, last_from_node, to_node in older),
                "accepted_before_cut": accepted, "rejected_before_cut": rejected, "drained": drained}

    def reopen(self):
        """Forward new tunnels again, from the same listening socket and port."""
        with self.lock:
            self.forwarding = True
            return {"same_port": self.server_address[1] == self.port, "listening": self.thread.is_alive()}

    def close(self):
        """Close every tunnel and the listening socket within the cleanup budget."""
        drained = self.cut()["drained"]
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=DRAIN_WAIT)
        return drained and not self.thread.is_alive()


class _Tunnel(socketserver.BaseRequestHandler):
    def handle(self):
        relay, node = self.server, self.request
        with relay.lock:
            generation = relay.requests[node]
            if generation != relay.generation:
                return
        try:
            hub = socket.create_connection(relay.upstream, timeout=CONNECT_TIMEOUT)
        except OSError:
            return
        with relay.lock:
            if generation != relay.generation:  # cut while connecting, even if already reopened
                hub.close()
                return
            relay._serial += 1
            serial = relay._serial
            lane = {"sockets": (node, hub), "opened": time.monotonic(), "last_from_node": None, "from_node": 0,
                    "to_node": 0, "cut": False}
            relay.lanes[serial] = lane
            relay.counts["accepted"] += 1
        try:
            node.setblocking(True)
            hub.settimeout(None)
            peers = {node: hub, hub: node}
            while not lane["cut"]:
                readable, _, _ = select.select(list(peers), [], [], 0.25)
                for source in readable:
                    data = source.recv(64 * 1024)
                    if not data or lane["cut"]:
                        return
                    peers[source].sendall(data)
                    with relay.lock:
                        if source is node:
                            lane["from_node"] += len(data)
                            lane["last_from_node"] = time.monotonic()
                        else:
                            lane["to_node"] += len(data)
        except (OSError, ValueError):
            return  # the tunnel was cut or a peer went away
        finally:
            hub.close()
            with relay.lock:
                relay.lanes.pop(serial, None)
