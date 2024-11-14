import nt_vtk

#%%
data = nt_vtk.Data("test/PELOOP.00001000.dat",nt_vtk.VECTOR)
np_array = data.get_np_array()
data.get_vtk_file('output/test_vec.vtk')
data.get_dat_file('output/test_vec.dat')

#%%