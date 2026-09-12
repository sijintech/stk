import json
import os
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')
from click.testing import CliRunner
from suan.cli.main import cli
from toolkits.sviz.field import read_field, write_field, plot_field
from toolkits.sjob.core import schedule_batch, create_batch, execute_batch, condition


@pytest.mark.parametrize('components', [1, 3])
def test_field_roundtrip_and_axis_order(tmp_path, components):
    data = np.arange(2*3*4*components, dtype=float).reshape(2, 3, 4, components) / 7
    for extension in ['dat', 'npy', 'vtk']:
        file = tmp_path / ('field.' + extension)
        write_field(file, data)
        np.testing.assert_allclose(read_field(file), data, rtol=1e-14, atol=1e-14)
    png = plot_field(tmp_path / 'field.dat', tmp_path / 'preview.png', vector=components == 3, axis='y', index=1)
    assert png.read_bytes().startswith(b'\x89PNG')


def test_vtk_export_with_independent_vtk_reader(tmp_path):
    vtk = pytest.importorskip('vtk')
    data = np.arange(24).reshape(2, 3, 4, 1)
    path = write_field(tmp_path / 'scalar.vtk', data)
    reader = vtk.vtkStructuredPointsReader()
    reader.SetFileName(str(path))
    reader.Update()
    grid = reader.GetOutput()
    assert grid.GetDimensions() == (2, 3, 4)
    for i, j, k in np.ndindex(2, 3, 4):
        assert grid.GetScalarComponentAsDouble(i, j, k, 0) == data[i, j, k, 0]


def test_invalid_grid_rejected(tmp_path):
    file = tmp_path / 'bad.dat'
    file.write_text('2 1 1\n1 1 1 3\n1 1 1 4\n')
    with pytest.raises(ValueError, match='duplicate'):
        read_field(file)


def test_batch_paths_replacements_and_failure_exit(tmp_path):
    config = {'FreeFile': ['input.in'], 'FixFile': [], 'CopyFile': [], 'FreeVarName': ['TEMP'],
              'FixVarName': [], 'VarValue': {'TEMP': [100, 200]}, 'VarSequence': ['TEMP'],
              'Separator': '+', 'Format': '%s', 'Condition': '1>0', 'Command': 'exit 7'}
    (tmp_path / 'batch.json').write_text(json.dumps(config))
    (tmp_path / 'input.in').write_text('TEMP = 0\n')
    original = Path.cwd()
    batch = schedule_batch(tmp_path / 'batch.json', tmp_path)
    folders = create_batch('&input.in', tmp_path, batch)
    assert [p.joinpath('input.in').read_text().strip() for p in folders] == ['TEMP = 100', 'TEMP = 200']
    with pytest.raises(__import__('subprocess').CalledProcessError):
        execute_batch('exit 7', tmp_path, batch, end=1)
    assert Path.cwd() == original
    with pytest.raises(ValueError):
        condition('__import__("os").getcwd()')
    assert condition('1<2 && 4==4')


def test_installed_cli_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(cli, ['--help']).exit_code == 0
    data = np.arange(8).reshape(2, 2, 2)
    write_field('sample.dat', data)
    result = runner.invoke(cli, ['smesh', 'run', '-i', 'sample.dat', '-o', 'sample.vtk'])
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli, ['sviz', 'plot-scalar', '-i', 'sample.dat', '-o', 'sample.png'])
    assert result.exit_code == 0, result.output
    assert Path('sample.png').is_file()


def test_structure_generator_adapter(tmp_path):
    from toolkits.smesh.core import generate_structure
    config = tmp_path / 'input.toml'
    config.write_text('''target_program="muPRODICT"
[common_config]
nx=2
ny=3
nz=4
nc=1
[eta_config]
set_eta_case=-1
[comp_config]
set_comp_case=0
eta_case_config=[]
[[comp_case_config]]
case=0
filename="comp.in"
vari=1
c0=0.25
''')
    # The original schema requires both case arrays, even when eta is disabled.
    import toml
    data = toml.load(config)
    data['eta_case_config'] = []
    config.write_text(toml.dumps(data))
    root = generate_structure(config, tmp_path / 'out')
    output = read_field(root / 'comp.in')
    assert output.shape[:3] == (2, 3, 4)
    np.testing.assert_allclose(output, .25)
