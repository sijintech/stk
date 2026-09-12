"""Run this check against an installed wheel as well as the editable checkout."""

from importlib import import_module
from importlib.resources import files
import subprocess
import sys


def test_public_packages_and_installed_entrypoints(tmp_path):
    for module in ('suan.runtime', 'toolkits.sjob.core', 'structure_generator', 'stk_data'):
        assert import_module(module) is not None
    assert files('suan.gui').joinpath('resources/styles.qss').is_file()
    assert files('suan.runtime').joinpath('worker.py').is_file()
    result = subprocess.run([sys.executable, '-m', 'suan.cli.main', '--help'], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for command in ('server', 'jobs', 'workspaces', 'connect', 'sjob', 'smesh', 'sviz'):
        assert command in result.stdout
