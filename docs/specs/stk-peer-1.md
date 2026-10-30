# STK peer control protocol, version 1

This contract defines independent, bounded peer control messages and pure version/
capability negotiation. `suan/peer/protocol.py` supplies the pure codec;
`suan/peer/endpoint.py` connects an explicitly supplied native transport to mutual
authentication and the restricted authorized project adapter. This is a backend
prototype with local two-process acceptance, not completed cross-platform S4,
desktop pairing UI, signaling deployment, file transfer, remote desktop control or
federated training. Each additional capability needs its own implementation and
acceptance evidence before an endpoint advertises it.

The peer service is separate from the private desktop stdio bridge and the Linux
Runtime. It does not expose the bridge's method registry over a network, remove
the Runtime's Linux restriction or relax `RuntimeClient`'s loopback/SSH boundary.
It never calls `Bridge.hello`: that local handshake may resume transfers, start
previous local model services and return process-local paths and identifiers.

## Message envelope and encoding

Each control message is one UTF-8 JSON document, framed by the selected transport.
The codec does not append newline or stream delimiters. File bytes belong to a
separate bounded transfer channel, not base64 data inside these control messages.

```json
{
  "format": "stk.peer/1",
  "id": "11111111-1111-4111-8111-111111111111",
  "method": "peer.hello",
  "params": {"protocols": [1], "capabilities": {"peer.hello": 1}}
}
```

The request has exactly `format`, `id`, `method`, `params`. Its ID is a canonical,
lowercase, hyphenated UUID retained by the caller for matching the reply. This
transport ID is distinct from a durable project `operation_id`.

A success has exactly `{format, id, result}`. An error has exactly
`{format, id, error:{code,message}}`. An error may use `id:null` when no trustworthy
request identity can be recovered. Success requires a UUID. A message cannot
contain both result and error. Error text is 1–256 characters; protocol-generated
errors use fixed descriptions without the rejected body, its values or local paths.
Endpoint adapters must not insert raw exceptions or credentials into that text.

The complete control document is at most **16 MiB** in each direction, including
the envelope and all JSON whitespace. This retains room for the shared project
read service's existing 8 MiB page budget and the 512 KiB edit receipt. Nesting is
at most **64 containers**, including the envelope. Both limits are checked before
parsing untrusted bytes. The codec rejects invalid UTF-8, BOM, duplicate keys at
any level, trailing documents, NaN/Infinity, numeric overflow to nonfinite values,
unpaired Unicode surrogates and non-JSON Python objects. The byte limit counts
UTF-8 bytes rather than characters. Braces inside escaped strings are ordinary text.

Encoded output uses sorted object keys, compact separators and unescaped UTF-8.
Object-key order has no identity meaning. Arrays, integers versus floats, booleans,
negative zero, null versus omission and Unicode text retain their values. Decoding
and validation do not generate command UUIDs, normalize options or choose revisions.
The helpers return detached objects, so later caller mutation cannot change a
validated request.

## Pure hello and capability negotiation

`peer.hello` is used only within an already authenticated channel. It accepts
exactly `{protocols,capabilities}`:

- `protocols`: 1–16 distinct positive integer versions, each at most 65535;
- `capabilities`: at most 64 method/version pairs. Names are at most 128 ASCII
  characters in dotted lowercase method syntax, versions are positive integers
  at most 65535, and booleans are not integer versions.

Version 1 is selected only when offered; no common protocol returns `unsupported`.
The endpoint supplies its actual, currently authorized capability subset to
`negotiate_hello`. The default subset contains only `peer.hello:1`. The result is:

```json
{
  "protocol": 1,
  "capabilities": {"peer.hello": 1},
  "unavailable": ["project.catalog"],
  "limits": {
    "message_bytes": 16777216,
    "json_depth": 64,
    "commands": 1000,
    "request_bytes": 262144,
    "receipt_bytes": 524288
  }
}
```

`capabilities` is the exact compatible intersection. `unavailable` is the sorted,
unique list of requested methods absent from it, including version mismatches.
Only implemented version-1 methods from the following allowlist may be advertised.
Hello does not infer a grant from a method name, authenticate an asserted owner,
write state, open projects, resume transfers, start models, execute tasks or control
a desktop. Its closed result contains no PID, directory, local handle or claim of
successful authentication. The client must not use a missing capability.

## Explicit project method subset

Version 1 permits exactly five method names: pure `peer.hello` and the four project
methods below. There is no general call forwarding, `project.open(directory)`,
ordinary `project.apply`, script execution, model setup, task submission or UI method.

Every business request requires three canonical UUIDs:
`project_id`, `grant_id`, `database_generation`. These identify a requested target;
their syntactic validity is not authorization. The trusted endpoint must verify
them against the authenticated caller and current project registration/grant before
opening or using the target. An address or display name is not a machine identity.

| Method | Additional required parameters | Optional parameters | Result |
|---|---|---|---|
| `project.catalog` | none | `expected_revision`, `offset`, `limit` (1–200) | Shared structure/page result |
| `project.table.read` | `table_id`, `expected_revision` | `offset`, `limit` (1–500), `record_id` | Shared typed record page |
| `project.edit_operations.apply_once` | `operation_id`, `expected_revision`, `commands` | none | `{receipt,replayed}` |
| `project.edit_operations.get` | `operation_id` | none | `{receipt}` |

Unknown parameters are rejected. Requests cannot contain `handle`, `directory`,
`path`, `scope`, `owner` or `caller` instead of the explicit target/operation fields.
These restrictions apply to protocol metadata, not to ordinary authorized JSON
cell values whose keys happen to have those names. There is no implicit current
project or active desktop selection. A record-specific table read cannot also use
a nonzero offset. Read pages retain the shared revision and pagination bounds.

The command/read/receipt types reuse the published shared contracts from
`desktop-bridge-1`; the module loads only schema/type metadata and never constructs
or dispatches a local bridge. Local handles are not wire identities. Command lists
have 1–1000 entries; their canonical bytes cannot exceed 256 KiB. The core separately
checks the complete original request including its trusted scope and identity
overhead against the same 256 KiB request budget.

Success decoding must retain the original request method and supply it to
`validate_response`, `decode_message` or `encode_message`. Without that context a
generic codec validates only the envelope/JSON, not the method's result contract.
Endpoints and clients must validate the method result and match the response ID
to the retained request. Project, table, field and record metadata are closed DTOs;
accidentally forwarding a local session object with a directory/handle/PID is
rejected. Authorized cell JSON remains content rather than protocol metadata.

## Authority and permanent edit identity

The endpoint resolves `project_id` through its local owner-controlled registration,
not a caller-supplied path. A current project grant and exact database generation
are required for reads, new writes and old receipt lookups. The authorization lease
must remain valid while the shared store operation is accepted and committed.
The first version has one clear owning service for a project; two peers do not
open a shared network-disk SQLite database or automatically merge project copies.

For an edit, the original `operation_id`, `expected_revision` and `commands` pass
unchanged to the [format-15 edit API](project-edit-operations-1.md). The trusted
authority supplies an operation scope bound to authenticated owner and caller
identities and the registered database generation. It never accepts a scope or
caller assertion from this body. That stable scope survives reconnects and process
restarts; a transient session ID or PID cannot substitute for it. A changed
registration/generation cannot inherit an old namespace merely because it uses
the same path, project UUID or network address.

The format-15 request/receipt transaction, generated command UUIDs, original
revision, budgets and no-GC identity retention remain authoritative. A reply lost
after commit is resolved by an explicit `get` under a still-valid grant, or an
explicit repetition of the identical original operation. A changed base revision
or commands conflicts. Neither transport reconnect nor timeout automatically
replays a write, invents another operation ID, changes scope or raises the revision.
Receipts are not signatures or authorization and do not prove current table state.

Generation continuity needs owner-side lifecycle enforcement. A raw database copy
or rollback to an old backup does not by itself prove globally exactly-once
execution, even if it preserves the project UUID; see the format-15 contract.
The owner authority enforces the registered generation and current grant; explicit
owner rebind rotates the generation and invalidates affected contexts. It rejects
observed file replacement or revision rollback. An unobserved in-place restore or
loss of authoritative registry state cannot be proved safe from a SQLite snapshot
alone and remains outside any global exactly-once claim.

## Explicit native connection and mutual authentication

`PeerEndpoint(transport, authority, public_key=..., sign=...,
remote_peer_id=..., remote_owner_id=...)` is passive on construction. `transport`
is an explicitly prepared `NativeTransport`, with signaling and network policy
handled by the owner outside this endpoint. The raw 32-byte Ed25519 public key and
the remote peer fingerprint and owner UUID are trusted local pairing inputs.
The owner must verify these pins before using this constructor; neither hello nor
a received authentication body creates or updates a pin. The endpoint receives
only a `sign(bytes)->bytes64` callback, never serializes a private key, and exposes
no wire operation to approve peers, grant projects, bind paths or change policy.

Both endpoints call `start(timeout=30)` concurrently. Each uses its local
authority to issue a single-use challenge for the pinned remote peer and the
actual native channel binding. Before invoking its signer, the other endpoint
strictly validates the full challenge and checks that its peer ID equals its own
public identity, owner ID equals the pinned remote owner, and binding equals the
current local native binding. It signs only the domain-separated
`auth_message(challenge)` bytes. A caller-selected owner, peer, binding, arbitrary
message or noncanonical challenge never reaches the signer.

Authentication control documents have their own `stk.peer-auth-channel/1` format,
at most **4096 UTF-8 bytes** and **8 containers** deep. They reject invalid UTF-8,
BOM, duplicate keys, nonfinite constants, unknown fields and unexpected types.
The exact closed forms are:

```text
{format:"stk.peer-auth-channel/1",type:"challenge",challenge:{
  format:"stk.peer-auth/1",owner_id:UUID,peer_id:hex64,challenge_id:UUID,
  nonce:hex64,channel_binding:hex64,expires_in:60}}
{format:"stk.peer-auth-channel/1",type:"proof",challenge_id:UUID,signature:hex128}
{format:"stk.peer-auth-channel/1",type:"accepted",challenge_id:UUID}
```

The authority verifies the remote proof against its approved public key and
single-use, unexpired challenge before issuing an opaque process-local context.
Each side acknowledges the challenge whose proof it verified. Both proof and
acknowledgment exchanges must complete before any business document is accepted.
If A issues challenge CA and B issues CB, A verifies B's proof of CA and sends
`accepted(CA)`; B verifies A's proof of CB and sends `accepted(CB)`. A requires its
received acknowledgment to name CB, the challenge A signed; B requires CA.
A failed proof, mismatched challenge, identity or binding, timeout, or business
document sent during authentication closes this one-use connection. Authentication
does not approve an unknown peer or bypass a project grant.

After authentication, a single control reader accepts requests and matches replies
to retained UUID/method pairs. Each side automatically sends a pure hello requesting
all five supported methods. The requested set describes what that caller wishes to
invoke; the receiving endpoint filters its answer using the authenticated caller's
current authority permission kinds. These two directions are independent. A peer
with no reverse project grant can still call methods granted to it by the other
owner. `capabilities` returns a detached copy of the remote negotiated method map;
`request("peer.hello", params)` explicitly refreshes it. Negotiation never replaces
the exact per-request project/grant/generation lease.
Until this endpoint has validated the reply to its own startup hello, incoming
project requests return fixed `busy` without starting a worker or entering a
project lease. A remote side finishing its hello first cannot make this local
endpoint execute project edits before local `start` has completed negotiation.

`request(method, params, timeout=30)` performs one send attempt and validates the
response using its retained original method. Both peers can request concurrently.
Defaults are **8 pending outgoing requests**, **4 incoming workers** without an
unbounded work queue, and **4096 request identities in each direction** per
connection; local configuration can lower concurrency. Reused incoming request IDs
and unsolicited or duplicate replies terminate the connection. Exhausted worker
or outgoing slots return `busy`. Hello uses the same bounded worker pool so an
authority lease cannot block the sole response reader. At most one incoming hello
is in progress until its reply has been sent; a concurrent hello returns `busy`,
keeping the adopted method subset consistent with the successful reply. Each public timeout is finite, greater than zero
and at most 60 seconds. Native message, queue, fragment and assembly limits still
apply; this endpoint never owns an unrestricted listener or opens a network port.

Timeout, disconnect or invalid response closes the connection and releases all
pending waiters. It never restarts the helper, reconnects, reauthenticates or
replays requests. A shared-store operation already accepted under its authority
lease may commit after a waiter times out; closing a connection is not rollback.
`PeerCallUncertain` marks a lost or indeterminate write outcome and retains its
original `operation_id` and `expected_revision`. The caller must preserve the
original commands as well. A new explicitly connected endpoint can call `get`
with that ID under its current grant, or explicitly repeat the exact original
operation; the endpoint does neither automatically. Remote errors expose only
fixed public descriptions, never internal SQL, paths or raw exceptions.
An accepted edit whose post-operation authority metadata or identity check fails
returns fixed `unavailable`; a server result that fails its response schema or
encoding returns `internal_error`. Both can follow a committed project transaction
and therefore leave the write outcome uncertain. A valid request is not relabeled
as invalid caller parameters merely because the server's result DTO is broken.

## Errors, implementation entry points and acceptance boundary

Stable codes are `invalid_request`, `invalid_params`, `unsupported`, `unauthorized`,
`forbidden`, `not_found`, `conflict`, `busy`, `unavailable`, `limit_exceeded`,
`internal_error`. These describe observations; they do not grant permission to
automatically retry an edit. An endpoint maps internal failures to bounded fixed
errors and keeps raw paths, credentials and exception details out of wire replies.

Public pure helpers are `validate_request`, `validate_response`, `decode_message`,
`encode_message`, `negotiate_hello` and `PeerProtocolError`. Authenticated dispatch,
pairing, encrypted transport and authorization live outside the pure codec module.
`tests/test_peer_protocol.py` exercises real encode/decode positive and negative
cases, strict shared method types, a large page below the existing 8 MiB read
budget, UTF-8 byte/depth limits, closed metadata and a fresh interpreter where
hello is forbidden from opening files/databases, making sockets or spawning work.
`tests/test_peer_endpoint.py` additionally uses the actual optional native helper,
ephemeral Ed25519 keys, two authorities and real project databases to exercise
bidirectional RPC, UDP/TCP/IPv6 paths, independent single-direction grants, CAS,
generated UUID receipts, lost reply/reconnection with reopened persistent owner
authorities, revocation and database rebind,
concurrency/timeouts, and authentication identity/signature/binding failures.
Additional regressions hold a real project lease while a hello arrives and a
reverse RPC reply must be routed, interleave concurrent hello responses, and inject
post-commit authority metadata or result-schema failures before looking up the
original receipt. These checks preserve grants, generations and request identity.
Without an explicitly configured native helper those native acceptance tests skip;
such a skip is not evidence of an endpoint working on that platform. Explicitly
configuring a helper makes a missing helper or crypto dependency a failure.

Full S4 acceptance still requires actual Linux/macOS/Windows endpoint connections,
bidirectional Mac↔Windows operation/transfer/revision-conflict/recovery evidence,
WebRTC/ICE network self-tests and recorded direct-versus-relay paths, and independent
Flower multi-node training. The existing decisions remain: Flower in its own
environment, no flwr in the public Hub, outbound cooperation nodes, dataset opt-in
and withdrawal, per-round update audit, first deployment without SecAgg+ and with
telemetry/update checks disabled. Private sharing uses one-session/one-recipient
authorization, cross-institution content encryption and host-approved joining;
the first shared-session version does not record or remotely control desktops.
This protocol module does not count as evidence that any of those runtime goals
has already passed.
