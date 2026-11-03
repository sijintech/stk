# STK optional peer file transfer, version 1

This additive extension to [stk.peer/1](stk-peer-1.md) defines immutable file
manifests, six closed control methods and separate binary DATA/RECEIPT frames.
The pure codecs do not approve a session, select a destination, create a file,
start a helper or prove durability. An endpoint advertises an optional method
only when its real adapter implements it and current authority permits it.
Knowing this codec does not enable file transfer on the base endpoint.

The extension does not expose desktop bridge methods, arbitrary file reads,
project synchronization, remote execution, training or desktop control. Local
two-process acceptance does not establish cross-platform, NAT/TURN, site-policy
or helper distribution acceptance.

## Identity, session and local acceptance

A verified persistent public pin, an authenticated transport context, a current
host-approved sharing session and an exact file grant are separate requirements.
A project read/edit grant supplies none of the file permissions. The local
authority, pairing store and file adapter recheck their leases in that order for
each bounded accepted control or block commit. No network wait occurs inside
these leases. A public name or network address is not a trusted device identity.

`files.offer` carries the complete closed sharing-session offer:

```text
{format: "stk.peer-sharing-session/1", session_id, session_epoch,
 host: public_card, recipient: public_card, expires_at}
public_card = {format: "stk.peer-device/1", owner_id, peer_id,
               public_key, display_name}
```

Session/owner IDs are canonical lowercase hyphenated UUIDs. `session_epoch` is an
exact integer from 1 through 2^53-1. `expires_at` is a finite UTC Unix timestamp.
`public_key` is 64 lowercase hex characters; `peer_id` is
`SHA256(b"stk.peer.identity/1\0" + raw_public_key)`, also 64 lowercase hex
characters. The two peer fingerprints
must differ. The pure validator checks syntax and card consistency. The adapter
also verifies the authenticated sender's current complete Host pin, its own exact
recipient card, current epoch/expiry and equality with the outer `session_id`.
There is no approval RPC. See [identity and pairing](stk-peer-identity-1.md) for
the local identity/session lifecycle.

An incoming offer may reserve bounded pending metadata under a current paired
peer lease. It creates no destination, partial file or session approval. Explicit
local **Accept** approves the offered recipient session and separately grants
the exact sender, session, transfer and manifest. Accept chooses an absent local
destination directory; its path never enters the peer protocol. Accept does not
implicitly send data. The sender must explicitly start the transfer.

After reconnect/reopen, saved approval is audit evidence, not current authority.
The Host explicitly reapproves a session and conveys its new epoch in a new
`files.offer` operation for the same original transfer, content and both pins.
This may append pending reapproval but must preserve original intents, target,
committed prefix and receipts. Recipient Accept creates a fresh current grant;
`files.resume` then uses a new operation ID. Neither endpoint automatically
reconnects, accepts, starts, resumes, cancels or changes a destination.

## Immutable content manifest

The root has exactly six fields; each file has exactly five:

```text
{format: "stk.peer-files-manifest/1", project_id, source_revision,
 snapshot_id, snapshot_sha256,
 files: [{file_id, name, bytes, sha256, media_type}]}
```

`project_id`, `snapshot_id` and every distinct `file_id` are canonical UUIDs.
`source_revision` is an exact integer from 0 through 2^63-1. All SHA-256 values
are 64 lowercase hex characters. `files` has 1–64 entries in frozen order.
`bytes` is an exact integer from zero through 1 GiB; total declared bytes are at
most 4 GiB. `media_type` is an explicit lowercase type/subtype with no parameters,
at most 127 characters; it is metadata, not permission to execute or render.

`name` is a relative POSIX path in NFC, at most 1024 UTF-8 bytes and 16 components.
Components are at most 255 UTF-8 bytes and 255 UTF-16 code units. Empty/dot/parent
components, nonprintable text, backslashes, absolute/drive paths, Windows device
names, forbidden filename characters and trailing spaces/dots are rejected.
Encoded slash, backslash and NUL spellings are rejected. Names may not collide
under NFC/case folding, turn a file into a parent directory or use the reserved
top-level `.stk-peer-receipt.json`. The validator rejects ambiguous names instead
of silently renaming them.

The validated canonical UTF-8 JSON is at most 1 MiB. Canonical encoding uses
sorted object keys, compact separators, unescaped UTF-8 and no nonfinite numbers;
array order is retained. `manifest_sha256` hashes those exact canonical bytes.
Session IDs, peer pins, grants, local paths and transfer attempts are excluded
from content identity. Preparing from a project verifies only the explicitly
selected frozen snapshot objects, without following their former source paths,
changing labels or authorizing a transfer. A manifest digest alone is not proof
of current authority or of received file bytes.

## Closed controls and durable operation identity

All methods use the existing control envelope and 16 MiB/depth-64 bounds.
Capabilities are method/version pairs, never a group flag such as `peer.files`.
The five base methods and pure hello/default limits remain unchanged. A client
must negotiate each optional method before use, and every call is authorized
again at acceptance; the intersection itself grants nothing.

Let `T` mean the three required fields
`{session_id, transfer_id, manifest_sha256}`. All parameter objects are closed:

| Method, version 1 | Complete parameters |
|---|---|
| `files.offer` | T, `operation_id`, `manifest`, `session_offer` |
| `files.status` | T, `operation_id` (UUID or null) |
| `files.start` | T, `operation_id`, `grant_id` |
| `files.cancel` | T, `operation_id`, `grant_id` (UUID or null) |
| `files.complete` | T, `operation_id`, `grant_id` |
| `files.resume` | T, `operation_id`, `grant_id` |

`transfer_id`, nonnull `operation_id` and nonnull `grant_id` are canonical UUIDs.
The manifest and sharing-session offer must bind the exact outer digest/session.
Only cancelling an unaccepted pending offer may use a null grant. There are no
wire `accept`, root, directory, path, owner override or caller-asserted scope
parameters. Streaming blocks are not RPC calls and do not consume the connection's
4096 control request identities.

The outer transport request ID is distinct from a durable mutation's
`operation_id`. Retain the complete original method and parameters before sending.
The request hash is SHA-256 of the complete validated canonical parameter object,
including `operation_id`, current session/grant and, for offer, `session_offer`;
the method is bound separately. Reuse of an operation ID with different original
parameters conflicts. Resume creates a new operation and never overwrites the
original start intent. Stable transfer/content/pins survive a newer session.

The common success result has exactly these fields:

```text
{session_id, transfer_id, manifest_sha256,
 state: offered|accepted|receiving|interrupted|complete|cancelled|failed,
 grant_id: UUID|null,
 files: [{file_id, bytes, committed_bytes, next_sequence, verified_sha256}],
 operation: null|{operation_id, method, request_sha256,
                  state: completed|uncertain},
 completion: null|{format: "stk.peer-files-receipt/1", transfer_id,
                   manifest_sha256, files: [{file_id, bytes, sha256}]}}
```

Progress has the same order, IDs and declared sizes as the frozen manifest.
`committed_bytes` is a durable contiguous prefix from zero through file size.
An incomplete prefix is a multiple of 61440; `next_sequence` is
`ceil(committed_bytes / 61440)`. Offered/accepted states have zero committed bytes.
Whole-file `verified_sha256` is null until completion, including for empty files.
Results contain no local paths, credentials, PIDs or raw exceptions.

A successful mutation requires its own nonnull **completed** operation receipt,
matching the original ID, method and full parameter hash. The result target and
supplied grant must also match the retained request. `files.status` with a null
operation requests progress only and returns a null operation; a nonnull ID may
return its original receipt or null. Null is never proof of no effect and never
unlocks a replacement write. A returned operation receipt is checked against its
retained original mutation, not against the status request's parameters. A fixed
generic error or lost response likewise does not prove a mutation was rejected
before durable reservation.

The endpoint retains request parameters and the frozen manifest for validation.
Pass them to `validate_file_result`, or as `request_params` and `file_manifest`
to the control codec; old optional-keyword-free calls remain compatible. A
method-only codec check proves structural validity, not the original intent or
content binding. A complete bound response requires the retained manifest and
exact ordered whole-file receipt; `files.complete` must return it. Completion
verifies actual complete bytes against all frozen sizes/hashes, fsyncs and records
the result, then atomically publishes without replacing an existing destination.
An empty file sends no DATA block and is verified by explicit completion only.

## Optional endpoint adapter

`PeerEndpoint(..., file_adapter=None)` retains its existing defaults. An installed
adapter supplies three methods, none of which waits for network I/O:

```text
capabilities(context) -> {implemented_currently_authorized_method: 1}
call(context, method, validated_params) -> (result_dict, frozen_manifest_dict)
receive_frame(context, DATA_FileFrame) -> RECEIPT_FileFrame | encoded_receipt_bytes
```

Each adapter operation rechecks its own current identity/session/file leases.
The local read-only `endpoint.authenticated_context` property returns the exact
opaque authenticated context only while ready and open. A sender compares it by
object identity with its current session context before controls and each DATA
block; a same-peer connection cannot inherit another connection's approval.
This property adds no wire method or permission.
The endpoint validates both the returned control DTO and its frozen manifest.
An invalid result after an accepted effect yields a generic error, which cannot
prove that effect did not occur. No adapter means no optional advertisement or
blob reader; supplying just a codec never enables an adapter.

For every outgoing file control, use
`request(method, params, file_manifest=retained_manifest, ...)`. Offer may derive
that manifest from its own parameters. A nonnull operation lookup additionally
requires `file_operation=(original_method, original_params)`; the endpoint detaches
and binds that original intent before sending and validates any returned receipt
against it. This permits historical lookup after reconnect while preserving its
old session in the original request hash. Null-progress status needs no original
operation and supplies no nonexecution proof. All new keywords are optional for
existing base-method callers.

`send_file_data(DATA_FileFrame, timeout=30)` makes one bounded send attempt and
returns only a matching application RECEIPT. The trusted sender records each
chunk intent under current authority before calling, then releases all service
leases for the network wait. There are at most two outgoing blocks overall and
one per transfer. A separate single blob reader routes receipts and submits DATA
to at most two independent disk workers; a blocked disk commit does not stop the
control reader from routing replies. Only after a durable adapter receipt returns
does the endpoint send it, outside the service lease. Missing, mismatched,
unsolicited or duplicate receipts close the connection and release all waiters.

`PeerFileCallUncertain` preserves operation/transfer/manifest identities after an
unknown mutation outcome. `PeerFileDataUncertain` preserves transfer/file/chunk
identity and digest after unknown DATA outcome; it does not copy the body. The
caller retains its original journal. Neither exception authorizes a retry, new
operation, cancellation or automatic reconnect. One already accepted block may
finish after revocation; the next block requires a fresh current lease.

## Binary application frames

One application frame occupies one bounded transport blob message. The header is
exactly **92 bytes**, network byte order, no implicit padding:

```text
struct !4sBBH16s16sQQI32s
```

| Offset | Bytes | Meaning |
|---|---|---|
| 0 | 4 | ASCII `STKF` |
| 4 | 1 | Version 1 |
| 5 | 1 | Type: DATA=1, RECEIPT=2 |
| 6 | 2 | Reserved, exactly zero |
| 8 | 16 | Transfer UUID, RFC byte order |
| 24 | 16 | File UUID, RFC byte order |
| 40 | 8 | Per-file sequence, unsigned 64-bit |
| 48 | 8 | File offset, unsigned 64-bit |
| 56 | 4 | Logical DATA length, unsigned 32-bit |
| 60 | 32 | SHA-256 of the original DATA body |
| 92 | variable | DATA bytes; absent for RECEIPT |

DATA length is 1–61440 bytes and equals its actual body length; the codec verifies
the actual body SHA. The complete frame is at most 64 KiB. Unknown versions/types,
nonzero reserved bits, short headers, extra body bytes, length/digest mismatches
and unsigned offset-plus-length overflow are rejected. Python booleans/floats
cannot stand in for integer fields.

The leased journal enforces current transfer/file/grant, exact file bounds,
fixed chunk alignment and per-file `sequence = offset / 61440`. Every chunk is
61440 bytes except the exact final remainder. A duplicate is acknowledged only
if it matches already committed original bytes/sequence/digest. Gaps, reordered
prefixes and conflicting replays cannot extend the journal. Codec validity alone
does not establish these storage or authorization properties.

A RECEIPT is exactly 92 bytes with an empty body. It echoes the original DATA
transfer/file IDs, sequence, offset, nonzero logical length and SHA. Emit it only
after data fsync and durable journal commit under a current lease; validate every
echoed field against the retained DATA before advancing sender progress. This is
an application durability receipt, distinct from the helper's delivery ACK to
the remote IPC pipe. Neither transport ACK nor application block receipt proves
whole-file verification or final publication. Lost receipts are reconciled with
durable status under renewed authority, never by guessing that no bytes committed.

The codecs themselves perform no I/O. Pure golden-vector and malformed-frame
tests establish byte layout and validation only. Storage, interruption/reopen,
no-overwrite publication, real authenticated transport and platform/site
acceptance each require their own evidence before delivery claims.

## Local sender and receiver implementation

The Python local-owner service is `FileSender`; `ReceiverAdapter(FileStore)`
connects the production receiver to the endpoint's optional adapter seam. These
are local APIs, not additional remotely callable approvals or bridge methods.

`prepare` selects explicit immutable project snapshot records and returns a
content plan. `offer` binds that plan to the current Host-approved connection,
recipient, registered source database generation and original transfer UUID.
Neither starts DATA. `send` explicitly starts, or explicitly resumes with a new
operation UUID, sends one block at a time, and requests whole-file completion.
`cancel` withdraws local sending permission before its one remote cancellation
attempt; `revoke` withdraws locally without claiming the peer recalled bytes.

The sender stores each original control and DATA intent with FULL SQLite
synchronization before network I/O. The original operation/transfer/content and
both pins remain retained after exceptions, reopening or quota exhaustion. A
repeated uncertain send never silently continues its loop. `status` is a passive
local observation; an explicit `query` may observe authenticated remote progress
or an original operation, but cannot resume or advance local committed offsets.
Only an explicit resume reconciles the one outstanding block against the
receiver's verified prefix. Prefix rollback or progress beyond that retained
outstanding block fails closed. Previously accepted work may complete after
withdrawal; a later block rechecks current authority, source database generation,
actual endpoint context and the exact original sending approval epoch. A new
Host approval cannot implicitly renew an earlier running send.

Before disclosing any bytes from a file, the sender hashes the entire selected
snapshot object through the same ordinary opened descriptor. Its device/inode,
size, mtime and ctime signature must remain unchanged before and after every
bounded read. Full hashing and network waits occur outside Authority, identity,
pairing and journal transactions. The receiver likewise verifies long resumed
prefixes outside those authorization locks, then rechecks the current grant,
operation phase, directory/file identities, byte stamps and chunk-journal
checkpoint before applying bounded repairs or accepting subsequent DATA.

An explicit local `recover` may close a lost final-reply or source-journal outcome
only using its retained original `files.complete` request and a matching completed
operation proof plus the full immutable completion receipt. If a valid original
receipt is already local, recovery sends nothing; otherwise it makes only an
explicit original-operation status query. It never repeats completion, DATA,
publication or authorization. A revoked sending flag stays revoked. Visible
destination files, null operations, uncertain operation proofs or incomplete
prefixes cannot substitute for the original completed proof; unknown publication
therefore remains unknown.

Local sender bounds are 128 plans, 128 transfers, 8 GiB total declared transfer
bytes, 4096 controls and 4096 explicit send records, 250000 retained block
attempts, and a 128 MiB SQLite page budget. The journal contains private source
locations and bounded metadata, never file bodies, identity seeds, credentials
or signaling. It has no identity-reusing garbage collector. These limits are
independent of the 4096 control-request identities on a live connection.

The implementation's tests distinguish application-service filesystem checks
from actual two-helper mutual-authenticated UDP/TCP execution, interruption and
explicit reapproval/resume. Linux loopback evidence, including a 4098-block file,
does not establish other operating systems, installed helper distribution, WAN
throughput, desktop UI or cross-site acceptance.
