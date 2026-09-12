import numpy as np
import pytest
pytest.importorskip("vtk")
from suan.visualization.scene import Grid, build_scene, load_grid, probe


def manufactured(vector=False):
    origin = (1e6, -3., 7.)
    spacing = (.25,.5,2.)
    x,y,z = np.meshgrid(*(origin[i]+np.arange(n)*spacing[i] for i,n in enumerate((9,8,7))), indexing="ij")
    return Grid(np.stack((x,y,z),axis=3) if vector else x+2*y-3*z, origin, spacing, "Pa", "analytic", "m")


def test_trilinear_physical_probe_and_boundaries():
    g=manufactured()
    for p in [(1e6+.12,-2.6,8.7),g.origin,(1e6+2,.5,19.)]:
        assert probe(g,p)["values"][0] == pytest.approx(p[0]+2*p[1]-3*p[2], rel=0, abs=1e-9)
    with pytest.raises(ValueError): probe(g,(0,0,0))
    with pytest.raises(ValueError): probe(g,(float("nan"),0,0))


@pytest.mark.parametrize("axis", [0,1,2])
def test_slice_positions_scalars_and_large_origin(axis):
    g=manufactured()
    scene=build_scene(g,dataset_id="analytic",axis=axis,index=2)
    points=np.array(scene["mesh"]["positions"])+g.origin
    np.testing.assert_allclose(points[:,axis],g.origin[axis]+2*g.spacing[axis],rtol=0,atol=1e-7)
    np.testing.assert_allclose(scene["mesh"]["values"],points[:,0]+2*points[:,1]-3*points[:,2],rtol=0,atol=1e-7)
    assert scene["manifest"]["coordinate_units"] == "m"


def test_iso_and_vector_filters():
    g=manufactured()
    level=float(g.values.mean())
    scene=build_scene(g,dataset_id="analytic",mode="iso",level=level)
    points=np.array(scene["mesh"]["positions"])+g.origin
    assert len(points)>0
    np.testing.assert_allclose(points[:,0]+2*points[:,1]-3*points[:,2],level,rtol=0,atol=1e-5)
    vectors=build_scene(manufactured(True),dataset_id="vectors",mode="vectors",component="magnitude")
    assert vectors["mesh"]["indices"]
    assert len(vectors["mesh"]["positions"])<=40000


def test_vtk_metadata_roundtrip(tmp_path):
    import vtk
    g=manufactured()
    writer=vtk.vtkXMLImageDataWriter()
    writer.SetInputData(g.image())
    writer.SetFileName(str(tmp_path / "field.vti"))
    assert writer.Write()
    restored=load_grid(tmp_path / "field.vti")
    assert restored.origin == g.origin
    assert restored.spacing == g.spacing
    np.testing.assert_array_equal(restored.values,g.values)
