"""Run this check against an installed wheel as well as the editable checkout."""

from importlib import import_module
from importlib.resources import files
from importlib.util import find_spec
from pathlib import Path
import os
import re
import subprocess
import sys

import toml


def test_public_packages_and_installed_entrypoints(tmp_path):
    for module in ('suan.runtime', 'toolkits.sjob.core', 'structure_generator', 'stk_data'):
        assert import_module(module) is not None
    assert files('suan.gui').joinpath('resources/styles.qss').is_file()
    assert files('suan.runtime').joinpath('worker.py').is_file()
    # Windows pipes default to cp1252, which cannot encode the Chinese toolkit help.
    result = subprocess.run([sys.executable, '-m', 'suan.cli.main', '--help'], cwd=tmp_path,
                            capture_output=True, env={**os.environ, 'PYTHONIOENCODING': 'cp1252'})
    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
    output = result.stdout.decode('utf-8')
    for command in ('server', 'jobs', 'workspaces', 'connect', 'mupro', 'sjob', 'smesh', 'sviz'):
        assert command in output
    assert '网格处理工具' in output and '可视化工具' in output
    # MuPRO help works on a client with no runtime configured.
    env = {key: value for key, value in os.environ.items() if not key.startswith('STK_RUNTIME_')}
    for args in (['mupro', '--help'], ['mupro', 'submit', '--help']):
        result = subprocess.run([sys.executable, '-m', 'suan.cli.main', *args], cwd=tmp_path, capture_output=True,
                                env={**env, 'STK_STATE_DIR': str(tmp_path / 'no-runtime')})
        assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
        assert b'Usage: suan ' + ' '.join(args[:-1]).encode() in result.stdout
    assert not (tmp_path / 'no-runtime').exists()


def test_base_install_never_requires_synorder(tmp_path):
    root = Path(__file__).resolve().parents[1]
    # A text scan: some legacy toolkit files do not parse, and many hold UTF-8 Chinese text.
    pattern = re.compile(r'^\s*(from|import)\s+(synorder|taskos)', re.MULTILINE)
    hits = {path.relative_to(root).as_posix()
            for folder in ('suan', 'toolkits') for path in (root / folder).rglob('*.py')
            if pattern.search(path.read_text(encoding='utf-8', errors='replace'))}
    assert hits == {'suan/workbench.py'}
    project = toml.load(root / 'pyproject.toml')['tool']['poetry']
    names = [*project['dependencies'], *project['extras'],
             *(name for extra in project['extras'].values() for name in extra)]
    assert not [name for name in names if re.search('synorder|taskos', name, re.IGNORECASE)]
    scripts = project['scripts']
    assert scripts['suan'] == 'suan.cli.main:main'
    for name, target in scripts.items():
        if name != 'suan-synorder-node':
            assert 'synorder' not in target and target != 'suan.workbench:main', name
    # stk-desktop starts this bridge; its help works without Synorder.
    result = subprocess.run([sys.executable, '-m', 'suan.desktop_bridge', '--help'],
                            cwd=tmp_path, capture_output=True)
    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
    output = result.stdout.decode('utf-8')
    assert '--stdio' in output and 'Synorder' not in output


def test_blender_workbench_is_archived():
    """D1 exit: the Blender workbench lives only under the tag archive/blender-workbench-2026-09."""
    root = Path(__file__).resolve().parents[1]
    project = toml.load(root / 'pyproject.toml')['tool']['poetry']
    scripts = project['scripts']
    assert 'suan-workbench' not in scripts and 'suan-blender' not in scripts
    assert not [target for target in scripts.values() if 'blender_client' in target]
    assert not [item for item in project.get('include', [])
                if (item['path'] if isinstance(item, dict) else item).split('/')[0] == 'blender']
    # Also true of an installed wheel: the package is gone, the scene v1 check moved to suan.render.v1.
    assert find_spec('suan.blender_client') is None
    assert callable(import_module('suan.render.v1').validate_scene)
