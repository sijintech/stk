import numpy as np
from ..basic.distribution_generator import generate_3d_sphere_data
from ..basic.distribution_generator import generate_3d_tanh_data
from ..basic.distribution_generator import generate_multiple_spheres_data
from ..basic.distribution_generator import generate_3d_uniform_data
from ..basic.write_matrix import writeMatrix2File

def generate_comp_Icase0(common_config, comp_config):
  nz = common_config["nz"]
  ny = common_config["ny"]
  nx = common_config["nx"]
  nc = common_config["nc"]
  
  filename = comp_config["filename"]
  vari = comp_config["vari"]
  c0 = comp_config["c0"]
  
  comp = np.zeros((nc+1, nz+1, ny+1, nx+1))
  uniform_data = generate_3d_uniform_data(nx,ny,nz,c0)
  
  if(isinstance(vari, int)):
    comp[vari,:,:,:] = uniform_data[:,:,:]
  elif(isinstance(vari, list)):
    for i in vari:
      comp[i,:,:,:] = uniform_data[:,:,:]
    
  writeMatrix2File(filename,comp)
  return comp
  

def generate_comp_Icase1(common_config, comp_config):
    nz = common_config["nz"]
    ny = common_config["ny"]
    nx = common_config["nx"]
    nc = common_config["nc"]
    
    filename = comp_config["filename"]
    rr = comp_config["rr"]
    vari = comp_config["vari"]
    
    comp = np.zeros((nc+1, nz+1, ny+1, nx+1))
    generated_sphere_data = generate_3d_sphere_data(nx,ny,nz,rr)
    if(isinstance(vari, int)):
      comp[vari,:,:,:] = generated_sphere_data[:,:,:]
    elif(isinstance(vari, list)):
      for i in vari:
        comp[i,:,:,:] = generated_sphere_data[:,:,:]

    writeMatrix2File(filename,comp)
    return comp

def generate_comp_Icase2(common_config, comp_config):
  nz = common_config["nz"]
  ny = common_config["ny"]
  nx = common_config["nx"]
  nc = common_config["nc"]
  
  filename = comp_config["filename"]
  rr = comp_config["rr"]
  vari = comp_config["vari"]
  
  comp = np.zeros((nc+1, nz+1, ny+1, nx+1))
  generated_tanh_data = generate_3d_tanh_data(nx,ny,nz,rr)
  if(isinstance(vari, int)):
    comp[vari,:,:,:] = generated_tanh_data[:,:,:]
  elif(isinstance(vari, list)):
    for i in vari:
      comp[i,:,:,:] = generated_tanh_data[:,:,:]
  
  writeMatrix2File(filename,comp)
  return comp
  
def generate_comp_Icase3(common_config, comp_config):
  nz = common_config["nz"]
  ny = common_config["ny"]
  nx = common_config["nx"]
  nc = common_config["nc"]
  
  filename = comp_config["filename"]
  rr = comp_config["rr"]
  vari = comp_config["vari"]
  ptclnum = comp_config["ptclnum"]
  iseed = comp_config["iseed"]
  
  comp = np.zeros((nc+1, nz+1, ny+1, nx+1))
  generated_mutiple_spheres_data = generate_multiple_spheres_data(nx,ny,nz,rr,ptclnum,iseed)
  if(isinstance(vari, int)):
    comp[vari,:,:,:] = generated_mutiple_spheres_data[:,:,:]
  elif(isinstance(vari, list)):
    for i in vari:
      comp[i,:,:,:] = generated_mutiple_spheres_data[:,:,:]
  
  writeMatrix2File(filename,comp)
  return comp