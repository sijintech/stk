"""The public muFerro connector (describe/open/verify) and its light half (inputs), on fake muFerro runs."""
import hashlib
import json
import math

import pytest

np = pytest.importorskip("numpy")

from mupro_fake import write_case, write_outputs  # noqa: E402
from suan.connectors.api import ConnectorError, DatasetHandle, InputConnector  # noqa: E402
from suan.connectors.files import LocalFiles, RuntimeFiles  # noqa: E402
from suan.connectors.mupro import MuFerroConnector, frame_rows, stem_field  # noqa: E402
from suan.connectors.mupro.inputs import MINIMAL_SCHEMA, MuFerroInputs, dump_toml  # noqa: E402
from suan.connectors.mupro.tables import ENERGY_COLUMNS, energy_columns, read_energy, read_progress  # noqa: E402
from suan.data.manifest import validate_result  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib


def run_dir(root, *, mode="ok", case_dir=None, grid=(4, 3, 2), steps=4, interval=2):
    folder = root / case_dir if case_dir else root
    write_case(folder, grid=grid, steps=steps, interval=interval)
    write_outputs(folder, grid=grid, steps=steps, interval=interval, mode=mode)
    return root


def test_describe_a_finished_run(tmp_path):
    connector = MuFerroConnector()
    source = LocalFiles(run_dir(tmp_path))
    assert connector.sniff(source).confidence == 0.95
    result = connector.describe(source)
    assert validate_result(result) == [] and json.dumps(result, allow_nan=False)
    assert result["complete"] and result["state"] == "succeeded"
    assert result["verification"]["status"] == "passed" and result["verification"]["verifier"] == "stk-mupro-1"
    datasets = {d["id"]: d for d in result["datasets"]}
    assert list(datasets)[0] == "Polar" and {"Strain", "Charges", "energy", "progress"} <= set(datasets)
    polar = datasets["Polar"]
    assert polar["geometry"]["dimensions"] == [4, 3, 2] and polar["geometry"]["length_unit"] == "grid_index"
    assert polar["fields"] == [stem_field("Polar")]
    assert polar["fields"][0]["tensor"] == "vector" and polar["fields"][0]["quantity"] == "polarization"
    assert [f["step"] for f in polar["frames"]] == [0, 2, 4]
    assert polar["frames"][1]["sources"]["Polar"] == {"path": "Polar.00000002.dat", "reader": "mupro.dat@1",
                                                      "size": (tmp_path / "Polar.00000002.dat").stat().st_size,
                                                      "sha256": None}
    strain = datasets["Strain"]["fields"][0]
    assert strain["tensor"] == "array" and "component_names" not in strain
    assert datasets["Charges"]["fields"][0]["tensor"] == "scalar"
    assert [c["name"] for c in datasets["energy"]["columns"]] == ["step", "Elastic Energy", "Electric Energy",
                                                                   "Landau Energy", "Gradient P Energy", "Total Energy"]
    assert result["qoi"][0]["value"] == -1.125 * 4 and result["qoi"][0]["step"] == 4
    assert result["extensions"]["mupro"]["case"]["grid"] == [4, 3, 2]
    roles = {f["path"]: f["role"] for f in result["files"]}
    assert roles["input.toml"] == "input" and roles["Polar.00000000.dat"] == "output"
    rows = frame_rows(result)
    assert rows[0]["dataset"] == "Charges" and {r["dataset"] for r in rows} >= {"Polar", "Strain"}
    live = connector.describe(source, live=True)
    assert not live["complete"] and live["state"] == "running" and live["verification"] is None


def test_describe_incomplete_and_recorded_runs(tmp_path):
    connector = MuFerroConnector()
    missing = run_dir(tmp_path / "missing", mode="missing_frame")
    result = connector.describe(LocalFiles(missing))
    assert not result["complete"] and result["state"] == "failed"
    assert result["extensions"]["mupro"]["missing_frames"] == ["Strain.00000001.dat"]
    failed = run_dir(tmp_path / "nan", mode="nan")
    result = connector.describe(LocalFiles(failed))
    assert not result["complete"] and result["verification"] is None and result["state"] == "unknown"
    assert result["qoi"][0]["value"] == "NaN" and validate_result(result) == []
    # The launcher's record (stk-mupro.json) supplies state, outcome, layout and verification.
    recorded = run_dir(tmp_path / "rec", case_dir="case16")
    record = {"schema_version": 1, "app": "muFerro", "state": "succeeded", "classification": None, "reason": "",
              "layout": {"ranks": 2, "threads_per_rank": 1, "launcher": "mpiexec"}, "command": ["muFerro"],
              "program": {"path": "/x/muFerro", "sha256": "ab" * 32}, "environment": {"OMP_NUM_THREADS": "1"},
              "exit_code": 0, "started_at": "2026-09-24T00:00:00+00:00", "finished_at": "2026-09-24T00:01:00+00:00",
              "verification": {"verifier": "stk-mupro-1", "status": "passed",
                               "checks": [{"id": "completion", "status": "pass", "message": "ok"}]},
              "qoi": {"total_energy": -4.5, "step": 4}, "case": {"grid": [4, 3, 2]}}
    (recorded / "stk-mupro.json").write_text(json.dumps(record))
    source = LocalFiles(recorded)
    assert connector.sniff(source).confidence == 1.0
    result = connector.describe(source, case_dir="case16")
    assert validate_result(result) == [] and result["complete"] and result["state"] == "succeeded"
    assert result["run"]["layout"] == {"ranks": 2, "threads_per_rank": 1, "launcher": "mpiexec"}
    assert result["run"]["app"]["executable_sha256"] == "ab" * 32 and result["native"][0]["path"] == "stk-mupro.json"
    polar = next(d for d in result["datasets"] if d["id"] == "Polar")
    assert polar["frames"][0]["sources"]["Polar"]["path"] == "case16/Polar.00000000.dat"
    assert connector.verify(source, case_dir="case16")["status"] == "passed"
    assert connector.describe(source)["datasets"] == []  # nothing directly in the binding root


def test_open_frames_and_tables(tmp_path):
    connector = MuFerroConnector()
    source = LocalFiles(run_dir(tmp_path))
    handle = connector.open(source, "Polar")
    assert isinstance(handle, DatasetHandle) and [f["step"] for f in handle.frames] == [0, 2, 4]
    image = handle.read(frame={"latest": True})
    assert image.id == "Polar" and image.time.step == 4 and image.dimensions == (4, 3, 2)
    field = image.field("Polar")
    assert field.tensor == "vector" and field.component_names == ("x", "y", "z") and field.unit == "unspecified"
    # Fake values: i + 10 j + 100 k + 1000 c + step (one-based indices), stored as (z, y, x, c).
    assert image.array("Polar")[1, 2, 3].tolist() == [4 + 30 + 200 + 1000 * c + 4 for c in (1, 2, 3)]
    digest = hashlib.sha256((tmp_path / "Polar.00000004.dat").read_bytes()).hexdigest()
    assert image.provenance.used[0]["sha256"] == digest
    assert handle.read(frame={"step": 3}).time.step == 2  # latest at or before
    assert handle.read(frame={"first": True}).time.step == 0 and handle.read(frame={"index": -2}).time.step == 2
    with pytest.raises(ConnectorError) as error:
        handle.read(frame={"step": 3, "policy": "exact"})
    assert error.value.code == "frame_not_found"
    part = handle.read(frame={"step": 2}, region=((1, 3), (0, 2), (1, 1)), stride=(2, 1, 1))
    assert part.dimensions == (2, 3, 1) and part.origin == (1.0, 0.0, 1.0) and part.spacing == (2.0, 1.0, 1.0)
    np.testing.assert_array_equal(part.array("Polar"), handle.read(frame={"step": 2}).array("Polar")[1:2, 0:3, 1:4:2])
    stats = handle.stats(frame={"step": 0}, field="Polar")
    assert stats["components"][0]["min"] == 1 + 10 + 100 + 1000 and stats["magnitude"]["count"] == 24
    energy = connector.open(source, "energy").read()
    assert energy.column("step").tolist() == [1, 2, 3, 4] and energy.index == "step"
    assert energy.field("Total Energy").unit == "normalized" and energy.field("Total Energy").quantity == "energy"
    np.testing.assert_allclose(energy.column("Landau Energy"), [-3.0, -6.0, -9.0, -12.0])
    progress = connector.open(source, "progress").read()
    assert progress.columns == ["step", "completed_steps", "total_steps"] and progress.column("total_steps")[0] == 4
    with pytest.raises(ConnectorError) as error:
        connector.open(source, "Nope")
    assert error.value.code == "not_found"


def test_tables_parse_live_and_headerless_traces():
    header = "      step         " + "".join(f"{h:>18}" for h in ("Elastic Energy", "Electric Energy", "Landau Energy",
                                                                 "Gradient P Energy", "Total Energy"))
    assert energy_columns(header)[3] == "Gradient P Energy"
    rows = ("kt:      1 energy:   0.1000000000E+01  0.2000000000D+01  0.3000000000E+01  0.4000000000E+01"
            "               NaN\n")
    table = read_energy(rows + "kt:      2 energy:   0.1")  # the unterminated last line is still being written
    # Without a header the columns keep muFerro's own names (graphs and presets name them before the header).
    assert table.columns == ["step", "Elastic Energy", "Electric Energy", "Landau Energy", "Gradient P Energy",
                             "Total Energy"]
    assert table.columns[1:] == list(ENERGY_COLUMNS)
    assert table.n_rows == 1 and table.column("Electric Energy")[0] == 2.0
    assert math.isnan(table.column("Total Energy")[0])
    with pytest.raises(ConnectorError):
        read_energy("kt: 1 energy: 1.0 2.0\n")
    with pytest.raises(ConnectorError) as error:  # an unreadable value is invalid data, not a ValueError
        read_energy("kt: 1 energy: 1.0 2.0 3.0 4.0 0.25x\n")
    assert error.value.code == "invalid_data"
    progress = read_progress('{"step":1,"completed_steps":1,"total_steps":3}\n{"step":2,"comp')
    assert progress.n_rows == 1 and progress.column("step").dtype == np.int64


def test_energy_rows_with_three_digit_exponents(tmp_path):
    # Fortran e18.10 writes exponents beyond +-99 without the letter (0.1500000000+102 = 1.5e101).
    row = ("kt:      5 energy:   0.1500000000+102 -0.2000000000-119 -0.1125000000E+01  0.3000000000+100"
           "  -0.4500000000+101\n")
    table = read_energy(row)
    assert table.column("Elastic Energy")[0] == 1.5e101 and table.column("Electric Energy")[0] == -2e-120
    assert table.column("Gradient P Energy")[0] == 3e99 and table.column("Total Energy")[0] == -4.5e100
    run_dir(tmp_path)
    with open(tmp_path / "energy_out.dat", "a") as stream:
        stream.write(row)
    connector = MuFerroConnector()
    source = LocalFiles(tmp_path)
    result = connector.describe(source, live=True)
    assert any(d["id"] == "energy" for d in result["datasets"])
    total = next(q for q in result["qoi"] if q["name"] == "total_energy")
    assert total["value"] == -4.5e100 and total["step"] == 5
    energy = connector.open(source, "energy", result=result).read(frame=None)
    assert energy.column("step")[-1] == 5 and energy.column("Elastic Energy")[-1] == 1.5e101
    # A value that is not a number at all: describe still lists the table, reading it is invalid_data.
    with open(tmp_path / "energy_out.dat", "a") as stream:
        stream.write(row.replace("kt:      5", "kt:      6").replace("0.3000000000+100", "0.30000000x0+100"))
    result = connector.describe(source, live=True)
    assert any(d["id"] == "energy" for d in result["datasets"])
    with pytest.raises(ConnectorError) as error:
        connector.open(source, "energy", result=result).read(frame=None)
    assert error.value.code == "invalid_data"


class FakeClient:
    def __init__(self, root):
        self.root = root
        self.downloads = []

    def artifacts(self, task_id):
        return [{"path": p.relative_to(self.root).as_posix(), "size": p.stat().st_size,
                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(self.root.rglob("*"))
                if p.is_file()]

    def download(self, task_id, path, destination):
        self.downloads.append(path)
        destination.write_bytes((self.root / path).read_bytes())
        return destination


def test_describe_and_read_through_the_runtime(tmp_path):
    root = run_dir(tmp_path / "work", case_dir="case16")
    (root / "case16" / "input.toml").write_text((root / "case16" / "input.toml").read_text(encoding="utf-8")
                                                .replace("material = 'material.toml'",
                                                         "material = 'material.toml'\ninclude = 'extra.toml'"))
    (root / "case16" / "extra.toml").write_text("[output]\ninterval = 99\n")  # the including file wins
    client = FakeClient(root)
    source = RuntimeFiles(client, "t" * 32, tmp_path / "cache")
    connector = MuFerroConnector(case_dir="case16")
    result = connector.describe(source)
    assert validate_result(result) == [] and result["extensions"]["mupro"]["case"]["output_interval"] == 2
    polar = next(d for d in result["datasets"] if d["id"] == "Polar")
    assert polar["frames"][0]["sources"]["Polar"]["sha256"] == hashlib.sha256(
        (root / "case16" / "Polar.00000000.dat").read_bytes()).hexdigest()
    assert result["verification"] is None and not any(p.endswith(".dat") and "Polar" in p for p in client.downloads)
    image = connector.open(source, "Polar").read(frame={"step": 4})
    assert image.time.step == 4 and client.downloads.count("case16/Polar.00000004.dat") == 1


def test_inputs_light_half(tmp_path):
    inputs = MuFerroInputs()
    assert isinstance(inputs, InputConnector)
    assert inputs.input_schema() == MINIMAL_SCHEMA and inputs.input_schema() is not MINIMAL_SCHEMA
    with pytest.raises(ConnectorError):
        inputs.input_schema("other.app")
    sdk = tmp_path / "sdk" / "share/mupro/schemas"
    sdk.mkdir(parents=True)
    (sdk / "muferro-input-1.schema.json").write_text('{"title": "full"}')
    assert inputs.input_schema(sdk_prefix=tmp_path / "sdk") == {"title": "full"}
    write_case(tmp_path / "case", grid=(8, 6, 4))
    case = inputs.read_case(LocalFiles(tmp_path / "case"))
    assert case["schema"] == "stk.case/1" and case["parameters"]["system"]["simulation_grid"] == [8, 6, 4]
    assert [f["path"] for f in case["native"]["files"]] == ["input.toml", "material.toml"]
    assert case["case_id"].startswith("sha256:") and case["resources"]["max_ranks"] == 6
    assert inputs.read_case(LocalFiles(tmp_path / "case"))["case_id"] == case["case_id"]
    (tmp_path / "case" / "material.toml").write_text("[landau]\na1 = 1\n")
    assert inputs.read_case(LocalFiles(tmp_path / "case"))["case_id"] != case["case_id"]
    written = inputs.write_case(case, tmp_path / "out")
    assert written[0]["path"] == "input.toml" and written[0]["generated"]
    assert tomllib.loads((tmp_path / "out" / "input.toml").read_text(encoding="utf-8")) == case["parameters"]
    checks = {c["id"]: c["status"] for c in inputs.validate_case(tmp_path / "case")}
    assert checks == {"input": "pass", "material": "pass", "clean": "pass"}
    write_outputs(tmp_path / "case", grid=(8, 6, 4), steps=3, interval=2)
    assert {c["id"]: c["status"] for c in inputs.validate_case(tmp_path / "case")}["clean"] == "warn"
    (tmp_path / "bad").mkdir()
    assert inputs.validate_case(tmp_path / "bad")[0]["status"] == "fail"
    spec = inputs.task_spec(case, {"ranks": 2, "threads_per_rank": 2}, workspace_id="w" * 32, case_dir="case")
    assert spec["resources"] == {"ranks": 2, "threads_per_rank": 2} and "--case-dir" in spec["argv"]
    with pytest.raises(ConnectorError):
        inputs.task_spec(case, {"ranks": 7}, workspace_id="w" * 32)
    with pytest.raises(ConnectorError):
        inputs.task_spec(case, {}, case_dir="case")


def test_monitor_adapter_replays_and_polls_a_run(tmp_path):
    from suan.monitor.events import make_event, validate_event
    connector = MuFerroConnector()
    assert connector.info()["capabilities"]["monitor_adapter"] is True
    root = run_dir(tmp_path / "run")
    adapter = connector.monitor_adapter(LocalFiles(root), None)
    events = adapter.replay()
    kinds = [e["type"] for e in events]
    assert kinds[0] == "run.started" and kinds[-2:] == ["verification", "run.completed"]
    assert {"progress", "metric.declare", "metrics", "frame", "message"} <= set(kinds)
    for index, event in enumerate(events):  # v1 data: the caller's emitter adds the envelope
        assert set(event) == {"type", "data"}
        validate_event(make_event(index, event["type"], event["data"], "adapter", 0.0))
    frames = sorted((e["data"]["dataset"], e["data"]["step"]) for e in events if e["type"] == "frame")
    assert ("Polar", 4) in frames and len(frames) == len(list(root.glob("*.0000000?.dat")))
    assert events[-1]["data"]["status"] == "succeeded" and events[-2]["data"]["status"] == "passed"
    metrics = [e["data"] for e in events if e["type"] == "metrics"]
    assert [m["step"] for m in metrics] == [1, 2, 3, 4] and metrics[-1]["values"]["total_energy"] == -4.5
    live = connector.monitor_adapter(LocalFiles(root), None)
    first = live.poll()
    assert [e["type"] for e in first if e["type"] == "progress"] == ["progress"]
    second = live.poll()  # only what is new: frames whose size stayed the same over two polls
    assert second and all(e["type"] == "frame" for e in second)
    final = live.poll(final=True, exit_code=0)
    published = [(e["data"]["dataset"], e["data"]["step"]) for e in first + second + final if e["type"] == "frame"]
    assert len(published) == len(set(published)) == len(frames)
    nested = run_dir(tmp_path / "work", case_dir="case16")
    adapter = MuFerroConnector(case_dir="case16").monitor_adapter(LocalFiles(nested), None)
    frames = [e["data"]["path"] for e in adapter.replay() if e["type"] == "frame"]
    assert frames and all(path.startswith("case16/") for path in frames)
    client = FakeClient(root)
    assert connector.monitor_adapter(RuntimeFiles(client, "t" * 32, tmp_path / "cache"), None) is None


def test_toml_writer_round_trip():
    document = {"material": "m.toml", "system": {"simulation_grid": [4, 3, 2], "dt": 0.01, "flag": True,
                                                 "name": 'a "quoted" é', "nested": {"x": [1.5, 2]}},
                "output": {"interval": 2}, "empty": {}}
    assert tomllib.loads(dump_toml(document)) == document
