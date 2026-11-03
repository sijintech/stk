# Desktop peer owner surface (additive working contract)

The local desktop bridge exposes the following methods. They are all desktop-only,
including metadata and manual signaling. They are absent from script discovery and
agent tools. They extend the local bridge; they are not remote `stk.peer/1` RPCs.
The machine shapes are `$defs.peer*` and `$defs.methods` in
`suan/contracts/schemas/desktop-bridge-1.schema.json`.

| Methods | Parameters beyond `operation_id` for mutations |
|---|---|
| `peer.info` | none; public identity and current process connection observations |
| `peer.operations.get/list` | original operation UUID / optional offset,limit |
| `peer.identity.initialize` | display_name |
| `peer.identity.rotate/revoke` | expected_generation |
| `peer.identity.recover` | original_operation_id (new explicit recovery operation UUID) |
| `peer.pins.list/verify/revoke` | page / full card + expected_peer_id / peer_id |
| `peer.connections.open` | peer_id,helper_prefix,offerer,route |
| `peer.connections.list/signals` | none / connection_id |
| `peer.connections.push_signal` | connection_id,signal_text |
| `peer.connections.authenticate/close` | connection_id |
| `peer.sessions.list/host/revoke` | page / connection_id,lifetime,session_id(nullable) / session_id |
| `project.peer.files.prepare` | handle,expected_revision,snapshot_id,record_ids; optional names/media_types |
| `peer.files.list/get` | role(sender/receiver),page / role,transfer_id |
| `peer.files.offer` | connection_id,plan_id,database_generation,session_id,transfer_id(nullable) |
| `peer.files.accept` | connection_id,transfer_id,offer_operation_id,target(local absolute absent directory) |
| `peer.files.send` | connection_id,transfer_id,grant_id,resume(boolean),timeout(0..3600 seconds, exclusive zero) |
| `peer.files.query` | connection_id,transfer_id,original_operation_id(nullable) |
| `peer.files.recover` | connection_id,send_operation_id |
| `peer.files.cancel` | connection_id,transfer_id,grant_id(nullable while pending offer) |
| `peer.files.revoke` | role,transfer_id |

Every explicit mutation returns `{operation: observation}`. The observation is
closed: `operation_id`, `action`, `request_sha256`, `state`, nullable
`connection_id`, nullable `transfer_id`, nullable method-specific public `result`,
and nullable fixed `{code,message}` error. `action` is the suffix above, for example
`files.send`; the project preparation action is `files.prepare`.

The original hash is SHA256 of UTF-8 Python ordinary JSON of
`{"action": action, "params": params}`, with sorted keys, no ASCII escaping,
no nonfinite numbers, and separators `(',', ':')`. It includes the operation UUID
and every provided parameter; omitted fields differ from explicit null. Integers,
floats and `-0.0` retain ordinary JSON representations. For `connections.push_signal`
only, replace the raw `signal_text` with its UTF-8 SHA256 hex before hashing and
retaining the request. Raw signaling is never persisted in this journal.

`running` means an original intent was FULL-committed before the action could
begin. Only authentication and file sending use a bounded background executor
(at most two actions per service); admission returns without holding an NDJSON
pending request for the transfer lifetime. `completed` contains a confirmed
original method result. Any exception without a confirmed final receipt remains
`uncertain`; a general error never proves that no side effect occurred. Reusing
the same UUID and original request observes its record without another worker;
changing the request conflicts. The journal keeps at most 4096 operations and
64MiB; no automatic garbage collection releases old identities.

Executor creation/submission failure leaves the original operation uncertain and
releases its live admission slot, including when recording the failure fails. A
queued dispatcher cannot perform the action until submission has been confirmed;
an item queued before a submission exception remains inert. The original UUID is
still observation-only, and no rejected work is retried automatically.

Construction, identity info, local pages, and reopening never initialize a key or
Authority, launch a helper, connect, accept, resume, or send. A previously running
record from another process is observed as uncertain without rewriting it or
queueing work. Partial identity/Authority initialization is fail-closed: a pending
outer operation is not permission to regenerate a key or reset an Authority.
The underlying identity receipt remains in the dedicated identity store. Explicit
`identity.recover` adopts only that exact original initialize/rotate/revoke receipt
when its complete current public card, generation and active state still match.
It never generates a key or replays rotation/revocation. Initial Authority metadata
may be repaired only when missing and no non-bootstrap action might have used it;
known registry loss is not reset. Newer generations are rejected. Recovery closes
only older-generation connections and monotonically closes the original outer
operation; it does not revoke an unrelated newer-generation connection or regrant
any pin, project or file permission.

Core and peer bridge startup do not require NumPy. The optional materials service
is constructed only for an explicit materials action; missing scientific extras
produce `unsupported` and do not prevent peer metadata or passive shutdown.

Connections are process-local UUIDs, never durable authentication credentials.
An explicit installation prefix is loaded through the helper installation verifier;
there is no PATH/source/environment executable fallback, download or auto-install.
The owner must separately verify the complete remote card (owner UUID, peer
fingerprint and public key). `open` launches a real `NativeTransport` using that
pin; `authenticate` starts the production `PeerEndpoint` on that exact transport.
Only its exact current opaque `authenticated_context` can approve sessions/files.
An old connection ID or a history receipt cannot bind a new connection.

Manual `signal_text` is an ephemeral JSON encoding of `{kind,payload}` from
`TransportSignal`. `signals` removes at most one bounded pending signal and returns
it or null; `push_signal` submits one explicit signal. No signal body enters logs,
operation results, projects or workspaces. This provides an explicit local manual
exchange, not deployed rendezvous, STUN/TURN policy or a guarantee of reachability.

The first sender is Host. Host approval is explicit; receiving metadata does not
accept a session. Receiver detail returns `{transfer,manifest,offer}` where the
reviewed offer retains the exact `offer_operation_id`, full session offer and
immutable manifest. Only local `files.accept` binds the current authenticated Host,
accepts the session and grants that exact manifest at the locally selected target.
Project read/edit permissions and training consent grant no file permission.

`files.send` invokes the production `FileSender`: original controls and per-block
intents precede I/O, each short current lease precedes the accepted chunk, and
network/hash waits hold no Authority lease. Sender `active` is a local withdrawal
flag, not proof of current session permission. Close/revoke may leave an already
accepted chunk committed; the next chunk must revalidate. Closing the bridge
closes endpoints and never reconnects/retries. New authentication, Host approval,
recipient acceptance/new grant and a new explicit resume operation are required.

Local pages never contact a peer. Explicit `query` observes authenticated remote
status without adopting prefixes, accepting or resuming. `recover` can adopt only
the retained original `files.complete` and its exact validated completion receipt;
it sends no DATA or remote mutation, does not publish or reactivate withdrawn
approval. A visible directory, current prefix, null operation or unknown publication
intent is insufficient. Sender and receiver original journals retain their own
lower-level receipts; the bridge admission journal does not replace them.

This surface is a two-party file-sharing increment. Target-OS helper/key/rename
verification, deployed signaling, cross-site transport, desktop click acceptance
and full distribution remain separate deliverables.
