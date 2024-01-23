import numpy as np
from .utils import r4_uniform_01

class MyNumber:
  def __init__(self,val):
    self.val = val
  
  def __format__(self,format_spec):
    ss = ('{0:' + format_spec+'}').format(self.val)
    if('E' in ss):
      mantissa, exp = ss.split('E')
      return mantissa + 'E' + exp[0] + '0' + exp[1:]
    
    return ss

def generate_3d_uniform_data(nx, ny, nz, c0):
  '''
  Generate three-dimensional uniform data,
  store it in the 'generated_3d_data' array.
  '''
  generated_3d_data = np.zeros((nz+1,ny+1,nx+1))
  generated_3d_data[:,:,:] = c0
  
  return generated_3d_data

def generate_3d_sphere_data(nx, ny, nz, rr):
  '''
  Generate three-dimensional data for a sphere with radius of rr, 
  store it in the 'generated_3d_data' array, 
  and return it.
  '''
  generated_3d_data = np.zeros((nz+1,ny+1,nx+1))
  for i in range(1, nx+1):
    for j in range(1, ny+1):
      for k in range(1, nz+1):
        if(float((k-nz/2)**2 + (j-ny/2)**2 + (i-nx/2)**2) <= float(rr)**2):
          generated_3d_data[k, j, i] = 1.0

  return generated_3d_data

# Icase = 2
def generate_3d_tanh_data(nx ,ny ,nz ,rr):
  generated_3d_data = np.zeros((nz+1,ny+1,nx+1))
  for i in range(1, nx+1):
    for j in range(1, ny+1):
      for k in range(1, nz+1):
        distance = np.sqrt((k-nz/2)**2 + (j-ny/2)**2 + (i-nx/2)**2)
        generated_3d_data[k, j, i] = (1.0 - np.tanh(1.0 * (distance - rr))) / 2.0

  return generated_3d_data

# Icase = 3
def generate_multiple_spheres_data(nx, ny, nz, rr, ptclnum, iseed):
  '''
  Generate multiple non-overlapping spheres with radius of rr.
  ptclnum is the number of sphere.
  '''
  generated_3d_data = np.zeros((nz+1, ny+1, nx+1))
  for pp in range(1, ptclnum+1):
    iseed, x_rand = r4_uniform_01(iseed)
    x_temp = int(float(nx)*x_rand)
    iseed, y_rand = r4_uniform_01(iseed)
    y_temp = int(float(ny)*y_rand)
    iseed, z_rand = r4_uniform_01(iseed)
    z_temp = int(float(nz)*z_rand)
    while(check_sphere_overlapp(nx, ny, nz, rr, generated_3d_data, x_temp, y_temp, z_temp)):
      iseed, x_rand = r4_uniform_01(iseed)
      x_temp = int(float(nx)*x_rand)
      iseed, y_rand = r4_uniform_01(iseed)
      y_temp = int(float(ny)*y_rand)
      iseed, z_rand = r4_uniform_01(iseed)
      z_temp = int(float(nz)*z_rand)
    print(f"{pp}-th nucleus of variant is at: {x_temp} {y_temp} {z_temp}")
    for kk in range(1, nx+1):
      for jj in range(1, ny+1):
        for ii in range(1, nz+1):
          if(float((ii-z_temp)**2 + (jj-y_temp)**2 + (kk-x_temp)**2) <= float(rr)**2):
            generated_3d_data[ii,jj,kk] = 1.0
    
  return generated_3d_data

def check_sphere_overlapp(nx, ny, nz, rr, generated_3d_data, x_temp, y_temp, z_temp):
  '''
  Check whether two spheres overlap.
  '''
  for kk in range(1, nx+1):
    for jj in range(1,ny+1):
      for ii in range(1, nz+1):
        if(float((ii-z_temp)**2 + (jj-y_temp)**2 + (kk-x_temp)**2) <= float(rr)**2):
          if(generated_3d_data[ii,jj,kk] >= 0.8):
            return True # sphere overlapp
  
  return False