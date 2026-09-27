import nt_vtk

data = nt_vtk.Data("microstructure_check.vti",nt_vtk.SCALAR)
data.data = data.data+1
data.get_dat_file('struct.in')