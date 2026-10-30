"""Bounded IPC invariants and opt-in actual two-process WebRTC interoperability."""
import hashlib
import json
import os
from pathlib import Path
import threading

import pytest

from suan.peer.transport import (MAX_BLOB_CHUNK_BYTES, MAX_CONTROL_BYTES, NativeTransport,
    TransportClosed, TransportError, TransportLimitError, TransportSignal, _ready)


def binding_info():
    local_fp, remote_fp = '11' * 32, '22' * 32
    local_nonce, remote_nonce = '33' * 32, '44' * 32
    pairs = [bytes.fromhex(local_fp + local_nonce), bytes.fromhex(remote_fp + remote_nonce)]
    binding = hashlib.sha256(b'stk.peer.channel/1\0' + b''.join(sorted(pairs))).hexdigest()
    route = {'family': 'ipv4', 'type': 'host', 'transport': 'UDP', 'address': '127.0.0.1', 'port': 12345}
    return {'channel_binding': binding, 'local_fingerprint': local_fp, 'remote_fingerprint': remote_fp,
            'local_nonce': local_nonce, 'remote_nonce': remote_nonce,
            'selected_pair': [route.copy(), route.copy()], 'max_message_size': 65536}


def test_transport_import_and_construction_do_not_start_a_listener_or_helper(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('construction must remain passive')
    monkeypatch.setattr('subprocess.Popen', forbidden)
    transport = NativeTransport('/missing/explicit-helper', offerer=True)
    assert transport._config['ice_servers'] == []
    assert not transport._config['relay_only']
    assert 'sdp' not in repr(TransportSignal('S', {'sdp': 'private signaling'}))
    with pytest.raises(TransportClosed):
        _ = transport.channel_binding
    with pytest.raises(TransportLimitError):
        transport.send_control(b'a' * (MAX_CONTROL_BYTES + 1))
    with pytest.raises(TransportLimitError):
        transport.send_blob_chunk(b'a' * (MAX_BLOB_CHUNK_BYTES + 1))


def test_binding_is_symmetric_domain_separated_and_rejects_reflection_or_tampering():
    value = binding_info()
    assert _ready(value) == value
    reverse = value.copy()
    for a, b in [('local_fingerprint', 'remote_fingerprint'), ('local_nonce', 'remote_nonce')]:
        reverse[a], reverse[b] = reverse[b], reverse[a]
    assert _ready(reverse)['channel_binding'] == value['channel_binding']
    bad = value.copy(); bad['channel_binding'] = '00' * 32
    with pytest.raises(TransportClosed):
        _ready(bad)
    bad = value.copy(); bad['remote_fingerprint'] = bad['local_fingerprint']; bad['remote_nonce'] = bad['local_nonce']
    with pytest.raises(TransportClosed):
        _ready(bad)


def test_missing_helper_is_explicit_and_cannot_be_restarted(tmp_path):
    transport = NativeTransport(tmp_path / 'unavailable', offerer=True)
    with pytest.raises(TransportClosed, match='unavailable'):
        transport.start()
    with pytest.raises(TransportClosed, match='restarted'):
        transport.start()
    transport.close()


@pytest.fixture
def native_helper():
    # A normal Python-only installation has no native stack and must stay usable.
    value = os.environ.get('STK_PEER_TEST_HELPER')
    if not value:
        pytest.skip('explicit optional native helper not provided')
    path = Path(value)
    assert path.is_file(), 'explicit native test helper must exist; never silently skip it'
    return path


def connect(native_helper, route, *, corrupt_fingerprint=False):
    a = NativeTransport(native_helper, offerer=True, route=route).start()
    b = NativeTransport(native_helper, offerer=False, route=route).start()
    stop = threading.Event(); errors = []
    def forward(source, target):
        while not stop.is_set():
            try:
                signal = source.next_signal(timeout=.2)
                if corrupt_fingerprint and source is a and signal.kind == 'S':
                    value = signal.payload.copy(); lines = []
                    for line in value['sdp'].splitlines():
                        if line.startswith('a=fingerprint:'):
                            key, fingerprint = line.split(' ', 1)
                            line = key + ' ' + ('00' if fingerprint[:2] != '00' else '01') + fingerprint[2:]
                        lines.append(line)
                    value['sdp'] = '\r\n'.join(lines) + '\r\n'
                    signal = TransportSignal('S', value)
                target.accept_signal(signal)
            except TimeoutError:
                continue
            except TransportError:
                if not stop.is_set() and not corrupt_fingerprint:
                    errors.append('signaling failed')
                return
    threads = [threading.Thread(target=forward, args=(a, b), daemon=True),
               threading.Thread(target=forward, args=(b, a), daemon=True)]
    for thread in threads:
        thread.start()
    def close():
        stop.set(); a.close(); b.close()
        for thread in threads:
            thread.join(timeout=2)
    return a, b, errors, close


@pytest.mark.parametrize('route', ['udp', 'tcp', 'ipv6'])
def test_real_helper_two_processes_control_fragmentation_blob_sha_and_actual_route(native_helper, route):
    a, b, errors, close = connect(native_helper, route)
    try:
        ia, ib = a.wait_ready(timeout=15), b.wait_ready(timeout=15)
        assert ia['channel_binding'] == ib['channel_binding']
        assert ia['local_fingerprint'] == ib['remote_fingerprint']
        assert ia['local_nonce'] == ib['remote_nonce']
        for info in (ia, ib):
            assert info['max_message_size'] == 65536
            for candidate in info['selected_pair']:
                if route == 'tcp':
                    assert candidate['transport'].startswith('TCP')
                else:
                    assert candidate['transport'] == 'UDP'
                if route == 'ipv6':
                    assert candidate['family'] == 'ipv6'
        payloads = [b'{"padding":"' + b'a' * (MAX_CONTROL_BYTES - 14) + b'"}',
                    b'{"padding":"' + b'b' * (MAX_CONTROL_BYTES - 14) + b'"}']
        assert all(len(body) == MAX_CONTROL_BYTES for body in payloads)
        blob = bytes(range(256)) * 256
        failures = []
        def send(source, body):
            try:
                assert source.send_control(body)['sha256'] == hashlib.sha256(body).hexdigest()
                assert source.send_blob_chunk(blob)['sha256'] == hashlib.sha256(blob).hexdigest()
                # Empty chunks have a valid digest and must not hang the framing loop.
                assert source.send_blob_chunk(b'')['sha256'] == hashlib.sha256(b'').hexdigest()
            except Exception as exc:
                failures.append(type(exc).__name__)
        threads = [threading.Thread(target=send, args=(a, payloads[0])),
                   threading.Thread(target=send, args=(b, payloads[1]))]
        for thread in threads: thread.start()
        assert a.recv_control() == payloads[1]
        assert b.recv_control() == payloads[0]
        for target in (a, b):
            assert target.recv_blob_chunk() == blob
            assert target.recv_blob_chunk() == b''
        for thread in threads:
            thread.join(timeout=45)
            assert not thread.is_alive()
        assert failures == [] and errors == []
        print(json.dumps({"native_route": route, "selected_pair": ia["selected_pair"],
                          "binding_equal": ia["channel_binding"] == ib["channel_binding"],
                          "control_bytes": MAX_CONTROL_BYTES,
                          "control_sha256": [hashlib.sha256(body).hexdigest() for body in payloads],
                          "blob_bytes": len(blob), "blob_sha256": hashlib.sha256(blob).hexdigest()}))
        # Bounds are rejected before any IPC write; the same connection remains usable.
        with pytest.raises(TransportLimitError): a.send_blob_chunk(blob + b'x')
        a.send_control(b'after rejected oversize')
        assert b.recv_control() == b'after rejected oversize'
    finally:
        close()


def test_real_helper_rejects_dtls_fingerprint_mismatch_before_channel_ready(native_helper):
    a, b, _, close = connect(native_helper, 'udp', corrupt_fingerprint=True)
    try:
        for peer in (a, b):
            with pytest.raises((TransportClosed, TimeoutError)):
                peer.wait_ready(timeout=2)
        assert a._info is None and b._info is None
    finally:
        close()


@pytest.mark.parametrize('record', [b'\x01\x00\x00\x02', b'\x00\x00', b'\x00\x00\x00\x03C{}'])
def test_real_helper_rejects_oversize_partial_or_invalid_first_ipc_record(native_helper, record):
    import struct
    import subprocess
    completed = subprocess.run([str(native_helper)], input=record, capture_output=True, timeout=5)
    assert completed.returncode == 2
    size, = struct.unpack('!I', completed.stdout[:4])
    assert size < 128 and completed.stdout[4:5] == b'E'
    assert json.loads(completed.stdout[5:4 + size]) == {'code': 'transport_closed'}
    assert completed.stderr == b''


@pytest.mark.parametrize('mode', ['idle', 'drip'])
def test_real_partial_assembly_has_an_absolute_deadline_despite_slow_fragments(native_helper, mode):
    import base64
    import subprocess
    import time
    attacker = os.environ.get('STK_PEER_TEST_ATTACKER')
    if not attacker:
        pytest.skip('explicit optional adversarial native test peer not provided')
    assert Path(attacker).is_file()
    peer = NativeTransport(native_helper, offerer=False, route='udp', assembly_timeout=.6).start()
    process = subprocess.Popen([attacker, mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    stop = threading.Event(); fragments = []; errors = []
    write_lock = threading.Lock()
    def to_attack():
        while not stop.is_set():
            try:
                signal = peer.next_signal(timeout=.1)
                value = signal.payload
                if signal.kind == 'S':
                    line = 'S ' + value['type'] + ' ' + base64.b64encode(value['sdp'].encode()).decode()
                else:
                    line = 'I ' + base64.b64encode(value['mid'].encode()).decode() + ' ' + base64.b64encode(value['candidate'].encode()).decode()
                with write_lock:
                    process.stdin.write(line + '\n'); process.stdin.flush()
            except TimeoutError:
                continue
            except (TransportError, BrokenPipeError, OSError):
                return
    def from_attack():
        try:
            for line in process.stdout:
                parts = line.rstrip('\n').split(' ', 2)
                if parts[0] == 'S':
                    peer.accept_signal(TransportSignal('S', {'type': parts[1], 'sdp': base64.b64decode(parts[2]).decode()}))
                elif parts[0] == 'I':
                    peer.accept_signal(TransportSignal('I', {'mid': base64.b64decode(parts[1]).decode(), 'candidate': base64.b64decode(parts[2]).decode()}))
                elif parts[:2] == ['E', 'fragment']:
                    fragments.append((int(parts[2]), time.monotonic()))
        except (TransportError, OSError):
            if not stop.is_set(): errors.append('transport closed during signaling')
    threads = [threading.Thread(target=to_attack, daemon=True), threading.Thread(target=from_attack, daemon=True)]
    for thread in threads: thread.start()
    try:
        peer.wait_ready(timeout=10)
        start = time.monotonic()
        with pytest.raises(TransportClosed, match='fragment assembly timed out'):
            peer.recv_control(timeout=4)
        elapsed = time.monotonic() - start
        assert .25 < elapsed < 2
        assert len(fragments) >= (3 if mode == 'drip' else 1)
        # Slow valid progress never extends the absolute first-fragment deadline.
        assert fragments[-1][1] - fragments[0][1] < 1.5
        assert not peer._messages['D']
        print(json.dumps({"partial_mode": mode, "absolute_deadline_seconds": .6,
                          "observed_close_seconds_after_ready": elapsed,
                          "fragments_sent": len(fragments),
                          "last_progress_seconds": fragments[-1][1] - fragments[0][1]}))
    finally:
        stop.set(); peer.close()
        with write_lock:
            try: process.stdin.write('Q\n'); process.stdin.flush(); process.stdin.close()
            except (BrokenPipeError, OSError): pass
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
        for thread in threads: thread.join(timeout=2)
        assert process.stderr.read() == ''
        process.stdout.close(); process.stderr.close()
