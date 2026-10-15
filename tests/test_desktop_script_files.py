"""Explicit Python-document IO and compare-before-save, with harmless temporary sources only."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os

import pytest

from suan.desktop_bridge import script_files
from suan.desktop_bridge.protocol import BridgeError
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_desktop_bridge import bridge_env  # noqa: F401


def test_bridge_read_save_and_saved_execution_are_distinct_explicit_actions(scripts, tmp_path):
    path = tmp_path / 'program.py'
    marker = tmp_path / 'explicit-only'
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('disk')\nprint('disk version')\n"
    path.write_bytes(source.encode('utf-8'))
    session = scripts.call('script.open')['session']
    loaded = scripts.call('script.file.read', {'path': str(path)})
    assert loaded == {'path': str(path), 'source': source,
                      'version': sha256(source.encode()).hexdigest(), 'size': len(source.encode())}
    assert scripts.call('script.status', {'session': session})['run'] is None
    assert not marker.exists()
    newer = source.replace('disk version', 'saved version')
    saved = scripts.call('script.file.write', {'path': str(path), 'source': newer,
                         'expected_version': loaded['version']})
    assert saved['version'] == sha256(newer.encode()).hexdigest()
    assert not marker.exists()
    execute(scripts, session, "print('buffer version')")
    assert not marker.exists() and path.read_text() == newer
    assert scripts.error('script.execute', {'session': session, 'path': str(path),
                         'expected_version': loaded['version']})['code'] == 'conflict'
    assert not marker.exists()
    assert execute(scripts, session, path=str(path), expected_version=saved['version'])['run']['state'] == 'succeeded'
    assert marker.read_text() == 'disk'
    assert scripts.error('script.execute', {'session': session, 'source': 'pass',
                         'expected_version': saved['version']})['code'] == 'invalid_params'


def test_new_save_is_create_only_and_existing_save_rejects_external_edit_or_removal(scripts, tmp_path):
    path = tmp_path / 'new.py'
    first = scripts.call('script.file.write', {'path': str(path), 'source': "print('中文')\n", 'expected_version': None})
    assert path.read_bytes() == "print('中文')\n".encode()
    assert scripts.error('script.file.write', {'path': str(path), 'source': 'new', 'expected_version': None})['code'] == 'conflict'
    path.write_text('external\n')
    assert scripts.error('script.file.write', {'path': str(path), 'source': 'new', 'expected_version': first['version']})['code'] == 'conflict'
    assert path.read_text() == 'external\n'
    path.unlink()
    assert scripts.error('script.file.write', {'path': str(path), 'source': 'new', 'expected_version': first['version']})['code'] == 'conflict'
    assert not path.exists()
    assert list(tmp_path.glob('.stk-python-*')) == []


def test_read_bom_and_exact_byte_bound_without_decoding_or_truncation_errors(tmp_path):
    path = tmp_path / 'bounded.py'
    raw = b'\xef\xbb\xbf' + "print('中文')\r\n".encode()
    path.write_bytes(raw)
    loaded = script_files.read_file({'path': str(path)})
    assert loaded['source'] == "print('中文')\r\n"
    assert loaded['version'] == sha256(raw).hexdigest()
    path.write_bytes(b'x' * script_files.FILE_LIMIT)
    assert len(script_files.read_file({'path': str(path)})['source']) == script_files.FILE_LIMIT
    for raw in (b'x' * (script_files.FILE_LIMIT + 1), b'\xff', b'pass\x00'):
        path.write_bytes(raw)
        with pytest.raises(BridgeError, match='UTF-8|256 KiB|NUL'):
            script_files.read_file({'path': str(path)})
    with pytest.raises(BridgeError, match='256 KiB'):
        script_files.write_file({'path': str(path), 'source': '中' * (script_files.FILE_LIMIT // 3 + 1), 'expected_version': None})


@pytest.mark.parametrize('name', ['config.env', 'program.txt', 'program.py/child.py', 'relative.py'])
def test_path_type_directory_and_missing_parent_are_refused(tmp_path, name):
    path = name if name == 'relative.py' else str(tmp_path / name)
    with pytest.raises(BridgeError):
        script_files.read_file({'path': path})
    with pytest.raises(BridgeError):
        script_files.write_file({'path': path, 'source': 'pass', 'expected_version': None})
    directory = tmp_path / 'directory.py'
    directory.mkdir(exist_ok=True)
    with pytest.raises(BridgeError):
        script_files.read_file({'path': str(directory)})


def test_symlink_file_and_parent_never_read_or_overwrite_target(tmp_path):
    target = tmp_path / 'target.py'
    target.write_text('original')
    link = tmp_path / 'alias.py'
    parent = tmp_path / 'linked'
    try:
        link.symlink_to(target)
        parent.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip('OS does not allow creating symbolic links for this test user')
    for path in (link, parent / 'target.py'):
        with pytest.raises(BridgeError, match='symbolic'):
            script_files.read_file({'path': str(path)})
        with pytest.raises(BridgeError, match='symbolic'):
            script_files.write_file({'path': str(path), 'source': 'overwrite', 'expected_version': None})
    assert target.read_text() == 'original'


def test_final_content_recheck_preserves_external_edit_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / 'race.py'
    path.write_text('first')
    version = script_files.read_file({'path': str(path)})['version']
    original_read = script_files._read
    count = 0
    def raced_read(path):
        nonlocal count
        count += 1
        if count == 2:
            path.write_text('external during save')
        return original_read(path)
    monkeypatch.setattr(script_files, '_read', raced_read)
    with pytest.raises(BridgeError, match='changed externally'):
        script_files.write_file({'path': str(path), 'source': 'draft', 'expected_version': version})
    assert path.read_text() == 'external during save'
    assert not list(tmp_path.glob('.stk-python-*'))


def test_concurrent_save_has_one_winner_and_preserves_file_permissions(tmp_path):
    path = tmp_path / 'concurrent.py'
    path.write_text('first')
    if os.name != 'nt':
        path.chmod(0o640)
    version = script_files.read_file({'path': str(path)})['version']
    def save(source):
        try:
            return script_files.write_file({'path': str(path), 'source': source, 'expected_version': version})
        except BridgeError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ['second', 'third']))
    assert sum(isinstance(item, dict) for item in results) == 1
    assert results.count('conflict') == 1
    assert path.read_text() in ('second', 'third')
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o640
