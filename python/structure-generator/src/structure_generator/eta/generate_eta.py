import numpy as np
from ..basic.distribution_generator import generate_3d_sphere_data
from ..basic.distribution_generator import generate_3d_tanh_data
from ..basic.distribution_generator import generate_multiple_spheres_data
from ..basic.distribution_generator import generate_3d_uniform_data
from ..basic.write_matrix import writeMatrix2File

def generate_eta_Icase0(common_config, eta_config):
  nz = common_config["nz"]
  ny = common_config["ny"]
  nx = common_config["nx"]
  nv = common_config["nv"]
  mst = common_config["mst"]
  
  filename = eta_config["filename"]
  c0 = eta_config["c0"]
  vari = eta_config["vari"]
  
  eta = np.zeros((nv+1,mst+1,nz+1,ny+1,nx+1))
  uniform_data = generate_3d_uniform_data(nx,ny,nz,c0)
  eta[vari, 1, :, :, :] = uniform_data[:,:,:]
  
  writeMatrix2File(filename, eta)
  return eta

def generate_eta_Icase1(common_config, eta_config):

    nz = common_config["nz"]
    ny = common_config["ny"]
    nx = common_config["nx"]
    nv = common_config["nv"]
    mst = common_config["mst"]
    
    filename = eta_config["filename"]
    rr = eta_config["rr"]
    vari = eta_config["vari"]
    
    eta = np.zeros((nv+1,mst+1,nz+1,ny+1,nx+1))
    
    generated_sphere_data = generate_3d_sphere_data(nx,ny,nz,rr)
    eta[vari, 1, :, :, :] = generated_sphere_data[:,:,:]
    
    writeMatrix2File(filename, eta)
    return eta

def generate_eta_Icase2(common_config, eta_config):
    nz = common_config["nz"]
    ny = common_config["ny"]
    nx = common_config["nx"]
    nv = common_config["nv"]
    mst = common_config["mst"]
    filename = eta_config["filename"]
    rr = eta_config["rr"]
    vari = eta_config["vari"]
    eta = np.zeros((nv+1, mst+1, nz+1, ny+1, nx+1))
    
    generated_tanh_data = generate_3d_tanh_data(nx,ny,nz,rr)
    
    eta[vari, 1, :, :, :] = generated_tanh_data[:,:,:]
    
    writeMatrix2File(filename, eta)
    return eta

def generate_eta_Icase3(common_config, eta_config):
    nz = common_config["nz"]
    ny = common_config["ny"]
    nx = common_config["nx"]
    nv = common_config["nv"]
    mst = common_config["mst"]
    
    filename = eta_config["filename"]
    rr = eta_config["rr"]
    ptclnum = eta_config["ptclnum"]
    iseed = eta_config["iseed"]
    nv_list = eta_config["nv_list"]
    
    eta = np.zeros((nv+1,mst+1,nz+1,ny+1,nx+1))
    generated_mutiple_spheres_data = generate_multiple_spheres_data(nx,ny,nz,rr,ptclnum,iseed)
    for t1 in range(1, mst+1):
      for s in range(1, nv_list[t1]+1):
        eta[s,t1,:,:,:] = generated_mutiple_spheres_data[:,:,:]
    
    writeMatrix2File(filename,eta)
    return eta