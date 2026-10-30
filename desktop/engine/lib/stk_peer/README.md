# Optional STK peer transport helper

This directory is an explicit **MIT-licensed exception** to `desktop/`'s default
GPL license; see [LICENSE](LICENSE). It contains a standalone CPU executable,
`stk-peer-transport`. It neither imports the desktop bridge nor links Blender or
GPU/window libraries. Python ships only the adapter `suan.peer.transport` and
requires the caller to supply the executable explicitly. There is no automatic
helper discovery, installation, network dependency fetch or install rule here.

The tested upstream stack is **libdatachannel 0.24.6 built with `USE_NICE=ON`,
`NO_MEDIA=ON`, `NO_WEBSOCKET=ON`**, libnice 0.1.23, OpenSSL 3.5.5 and the release's
pinned usrsctp. The default libjuice backend does not establish ICE-TCP support.
Provision those dependencies separately, then configure this directory with
`CMAKE_PREFIX_PATH` pointing to their installed CMake packages. The repository's
MIT nlohmann/json header is the only directly reused source. `LibDataChannel`
0.24.6 and OpenSSL 3 Crypto are required; SCTP is provided by libdatachannel.
`NO_MEDIA` avoids libsrtp. No external STUN/TURN server is configured by default.

Libdatachannel is MPL-2.0, usrsctp BSD and OpenSSL Apache-2.0; libnice/GLib have
their own LGPL/MPL notices. This directory's MIT exception does not relicense
those libraries. Any later binary package must explicitly include the runtime
libraries, their full applicable licenses/notices and required source provisions.
No helper binary or upstream source is hidden inside the Python wheel.

## Private IPC and application boundary

The parent process owns anonymous stdin/stdout pipes. Records contain a four-byte
unsigned big-endian length (including a one-byte type), followed by that type and
its body. Length is rejected before allocation above 16 MiB + 1. Windows pipes
use binary mode. Upstream logging is disabled. Errors expose fixed codes only;
the Python adapter discards stderr. **SDP and ICE credentials are ephemeral
signaling, and must never be written to projects or logs.**

| Type | Direction | Body |
|---|---|---|
| `C` | parent → helper, first only | JSON `offerer`, `route`, explicit `ice_servers`, `relay_only`, `assembly_timeout_ms` |
| `S`, `I` | both | SDP `{type,sdp}` or candidate `{candidate,mid}` JSON |
| `D` | both | raw control bytes, at most 16 MiB |
| `B` | both | raw blob chunk, at most 64 KiB |
| `R` | helper → parent | verified transport binding, nonces, selected pair and negotiated limit JSON |
| `A` | helper → parent | remote SHA-256 acknowledgment JSON for one completed send |
| `T`, `E` | helper → parent | bounded state/fixed error JSON |
| `Q` | parent → helper | empty, close after outstanding work |

The reliable ordered DataChannel is named `stk.peer/1`. A 32-byte CSPRNG nonce is
exchanged first inside DTLS. The binding is exactly:

```python
sha256(b"stk.peer.channel/1\0" + b"".join(sorted([
    local_fingerprint_32 + local_nonce_32,
    remote_fingerprint_32 + remote_nonce_32,
]))).hexdigest()
```

The two pairs must differ. The local fingerprint comes from this helper's own
certificate, and the remote fingerprint comes from libdatachannel's completed
DTLS verifier (`remoteFingerprint()`), rather than peer-asserted JSON. Only SHA-256
fingerprints are accepted; fingerprint verification remains enabled. SDP
renegotiation is rejected so a binding cannot be reused with a replacement DTLS
identity. This proves a particular encrypted transport, **not a paired device**.
Both peers must sign the authority challenge bound to this value before the
endpoint routes `peer.hello` or project messages. Before that, raw control bytes
are solely the upper layer's authentication exchange. Import/start/ready never
grants project access.

Data frames have kind, message ID, total length and offset, with at most 32 KiB of
fragment data. Reassembly accepts one ordered message at a time, caps control at
16 MiB and blob chunks at 64 KiB, and rejects wrong IDs/offsets, kind changes,
extra fragments and oversize declarations. Reassembly has an independent absolute
30-second deadline from the first fragment: progress never extends it. A watchdog
releases partial assembly and closes on expiry while holding no receive/state
mutex during close. Its thread is stopped and joined before callback teardown.
An explicit local `assembly_timeout` between 0.2 and 30 seconds supports bounded
diagnostics/tests; it defaults to 30 seconds. No sender assumes a 16 MiB SCTP
message: local SCTP max is 64 KiB. Sender pauses at a 256 KiB buffered high water,
resumes below a 128 KiB low threshold and has a 30-second send/ACK deadline.
Remote SHA ACK follows delivery to the parent pipe. It confirms transport bytes;
project commit confirmation still requires the authenticated operation receipt.
The adapter bounds receive queues to 32 MiB/1024 messages and signaling to
1 MiB/256 records. Send failures close the channel and never replay work.

`route=all` permits UDP and ICE-TCP; `udp`, `tcp` and `ipv6` are diagnostic route
constraints. `ipv6` means UDP/IPv6. Filters apply to trickled/embedded candidates
and to the actual selected pair. Route information records actual address,
family, transport and candidate type. `ice_servers` and `relay_only` support
explicit STUN/TURN configuration; TURN TCP/TLS describes the connection to a
relay and does not prove direct ICE-TCP. No port-prediction algorithm is added.

## Validation boundary

An explicit `STK_PEER_TEST_HELPER=/absolute/path/stk-peer-transport` enables
`tests/test_peer_transport.py`'s actual two-process tests. These exchange 16 MiB
control JSON and 64 KiB binary chunks in both directions, compare SHA ACKs,
exercise empty/oversize chunks, verify actual UDP/ICE-TCP/IPv6 selected pairs and
reject a changed DTLS fingerprint before channel-ready. Opt in to
`STK_PEER_BUILD_TEST_PEER=ON` and set `STK_PEER_TEST_ATTACKER` to the resulting
`stk-peer-partial-test` executable to additionally test actual stalled/slow-drip
partial frames against a 0.6-second absolute deadline. This adversarial target is
uninstalled and disabled by default. Missing explicit helper
paths fail; ordinary Python-only runs skip these optional native cases.

Linux same-machine evidence is stored outside the repository under
`/home/mnemora/.local/state/stk-validation/s4-peer-20261030/transport/`.
It establishes the three local routes, bounded transfer and fingerprint checks.
It does not establish macOS/Windows binaries, public IPv6, cross-machine NAT
traversal, STUN/TURN/TLS-443 relay operation, symmetric NAT port prediction,
owner-approved identity, or the complete S4 product. Those need separate real
platform/network/endpoint evidence.
