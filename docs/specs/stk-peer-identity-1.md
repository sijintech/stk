# STK device identity and two-party sharing approval, version 1

This additive local owner contract supplies persistent signing, verified public
pins and explicit two-party sharing approval for [peer control](stk-peer-1.md).
It does not grant project, file or training permissions, expose approval over
the network, or complete cross-platform S4 or multi-party collaboration.

## Persistent local identity

`LocalDeviceIdentity(directory)` is passive. `info()` and `operation(UUID)` open
existing state read-only, select public columns only, and neither generate keys
nor start helpers, models or network requests. The owner must explicitly call
`initialize(operation_id, display_name)`. A desktop service must also avoid
constructing an absent `PeerAuthority` during passive refresh: its existing
constructor initializes that separate registry.

The closed `stk.peer-device/1` public card contains exactly:

| Field | Meaning |
|---|---|
| `format` | `stk.peer-device/1` |
| `owner_id` | Canonical owner UUID, separate from Federation owner authority |
| `peer_id` | Lowercase SHA-256 fingerprint from existing `peer_id_for(public_key)` |
| `public_key` | Raw 32-byte Ed25519 public key encoded as 64 lowercase hex characters |
| `display_name` | Nonempty display text, at most 128 characters; never identity proof |

The restricted local `identity.sqlite3` asset commits binary signing material,
public identity and the retained operation receipt in one FULL SQLite transaction.
On POSIX its directory is owner-only 0700 and database owner-only 0600; linked
components, reparse points and nonordinary files are rejected. Windows stores
user-DPAPI ciphertext with UI forbidden, without machine-wide protection or a
plaintext fallback. Public JSON, project/workspace data, logs, callbacks and wire
messages never contain the private seed or ciphertext. This is a restricted file
signer, not a vault, hardware identity, secure-erasure or uncloneability promise.
DPAPI is [user protection with documented roaming exceptions](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).

`rotate(operation_id, expected_generation)` requires the existing key to remain
valid, generates a new peer fingerprint, preserves the local owner UUID and
advances generation. `revoke(operation_id, expected_generation)` invalidates the
generation without decoding the old key, so a corrupt key cannot prevent local
revocation. Key corruption/loss is never repaired by implicit generation. A new
machine or changed key needs fresh full-pin verification; copying a database does
not prove ownership continuity. There is no key import/export API.

Every successful lifecycle operation has a canonical caller-retained UUID and a
receipt containing its kind, complete original-request SHA-256 and public result.
The same UUID with the same request returns its historical receipt before current
generation checks; another request conflicts. Historical initialized/active results
do not reactivate current state. Retained identities are not garbage-collected;
capacity is 4096 successful operations, and existing receipts remain readable at
capacity. Loss/rollback of authoritative storage is outside a global exactly-once
claim.

`signer(remote_owner_id)` returns a callback, not key material. Each invocation
validates canonical `STK-PEER-AUTH/1` domain-separated challenge bytes, its own peer
fingerprint and pinned remote owner, then rechecks current active generation and
storage identity. It captures no usable old key. The endpoint independently checks
the exact actual channel binding and remote owner before calling the signer.
`current_identity()` holds a public read lease through one bounded accepted action;
rotation/revocation commits wait for that lease. Callers must never wait for network
input while holding it, and caller failures propagate unchanged.

## Full public pins and local owner operations

`PairingStore(authority.directory, identity, authority)` is passive. Its `pin`,
`pins`, `session`, `sessions` and `operation` reads use read-only projections and do
not create the additive `pairing_` tables. Lists have at most 100 items per page.

`verify_pin(operation_id, card, expected_peer_id)` is an explicit owner's assertion
that the complete fingerprint was separately verified. It checks the fingerprint
against the raw public key and stores owner UUID, public key and fingerprint
together. The same public key with a substituted owner UUID is rejected, including
after revocation. Hub metadata, addresses, invitation possession and display names
do not establish trust. Pin approval and the Authority peer approval, epoch and
original-operation receipt commit together. Reapproval cannot restore old contexts.

`revoke_pin(operation_id, peer_id)` atomically revokes the full pin and Authority
peer and its project grants. Replaying an earlier successful verification returns
history without reapproving it. Pin capacity is 1024, session capacity 4096 and
pairing-operation capacity 8192; capacity never evicts old identities or receipts.

`PeerAuthority.peer_access(context)` yields frozen primitive
`PeerLease(owner_id, registry_id, peer_id, peer_epoch)` under the existing Authority
transaction. It validates a current opaque context without opening a project or
inventing `project.read`. `PairingStore.peer_access(context)` additionally validates
the complete stored pin and local identity and yields `PairedPeerLease` metadata;
this remains insufficient for business/file access.

## Host approval and recipient acceptance

In this first two-party file slice the sender is Host. The Host explicitly calls
`host_session(operation_id, recipient_peer_id, lifetime, context=..., session_id=None)`
on the current authenticated recipient context. Lifetime is an explicit integer
from 1 to 3600 seconds. The result contains a closed offer:

```text
{format:"stk.peer-sharing-session/1", session_id:UUID, session_epoch:integer,
 host:full_public_card, recipient:full_public_card, expires_at:UTC_seconds}
```

`validate_offer(value)` is pure and returns detached closed metadata. It validates
canonical UUIDs, full cards, distinct peer fingerprints, exact positive integer
epoch at most 2^53-1 and finite expiry. It does not authenticate a Host, check the
current clock or authorize joining. A received file offer may retain this public
metadata for review, but must not accept it automatically.

The recipient explicitly calls `accept_session(operation_id, context, offer)`.
The actual authenticated context must match its separately verified Host card;
the intended recipient must equal its own current full card, with an unexpired
offer no more than 3600 seconds ahead. Acceptance alone is not an exact-manifest
file grant. The wire path for proposals is described in
[the file contract](stk-peer-files-1.md); no generic remote approval RPC exists.

`session_access(context, session_id)` yields frozen `SessionLease` fields:
`session_id`, `session_epoch`, local `owner_id`, `local_peer_id`, `remote_owner_id`,
`remote_peer_id`, `host_owner_id`, `host_peer_id`, `recipient_owner_id`,
`recipient_peer_id`, `registry_id`, `peer_epoch`, `identity_generation`, `expires_at`
and `role` (`host` or `recipient`). Both complete cards remain in local metadata.
Each lease checks current identity/pin/peer epochs, active session, wall expiry,
monotonic deadline and the exact process-local authenticated context object.

Lock order is **Authority → public identity read → Pairing → Files**. Revocation
waits for one already accepted bounded action; subsequent actions fail. A separate
file adapter must still validate its current exact-manifest grant for each block.
Project read/edit or a peer/session lease cannot substitute for that grant or for
Federation dataset consent. Already received bytes cannot be recalled.

The existing 600-second `PeerContext` expiry is independent of logical session
lifetime. Restart, new connection/context, expiry or key lifecycle change cannot
restore approval from history. `session`/`sessions` return historical metadata with
`context_bound:false`, never a usable credential. Replaying an old approval UUID
does not bind a new context. Explicit Host reapproval uses a new operation UUID and
the original `session_id`, increments its epoch and issues a new offer; recipient
acceptance requires that newer Host epoch. Both pins must remain identical. A
revoked session cannot be resurrected; a new session requires explicit approval.
`revoke_session(operation_id, session_id)` is a separate local owner action.

These owner actions remain desktop-only integration requirements: public reads,
workspace restore and reopening must not initialize, connect, approve, send, accept
or resume. UI and installed-helper/endpoint verification on macOS and Windows are
separate acceptance work. Linux unit/lease/signature evidence does not prove target
OS DPAPI/ACL behavior, actual network routes or completed sharing UI.
