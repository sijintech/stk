import numpy as np
import toml
import argparse

class MyNumber:
    def __init__(self,val):
        self.val = val
    
    def __format__(self,format_spec):
        ss = ('{0:' + format_spec+'}').format(self.val)
        if('E' in ss):
            mantissa, exp = ss.split('E')
            return mantissa + 'E' + exp[0] + '0' + exp[1:]
        
        return ss

# Icase = 1
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
  generated_3d_data = np.zeros(nz+1,ny+1,nx+1)
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
  generated_3d_data = np.zeros(nz+1, ny+1, nx+1)
  for pp in range(1, ptclnum+1):
    x_temp = int(float(nx)*r4_uniform_01(iseed))
    y_temp = int(float(ny)*r4_uniform_01(iseed)) 
    z_temp = int(float(nz)*r4_uniform_01(iseed))
    while(check_sphere_overlapp(nx, ny, nz, rr, generated_3d_data, x_temp, y_temp, z_temp)):
      x_temp = int(float(nx)*r4_uniform_01(iseed))
      y_temp = int(float(ny)*r4_uniform_01(iseed)) 
      z_temp = int(float(nz)*r4_uniform_01(iseed))
    print(f"{pp}-th nucleus of variant is at: {x_temp} {y_temp} {z_temp}")
    for kk in range(1, nx+1):
      for jj in range(1, ny+1):
        for ii in range(1, nz+1):
          if(float((ii-z_temp)**2 + (jj-z_temp)**2 + (kk-z_temp)**2) <= float(rr)**2):
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
  generated_data = np.zeros((nz+1,ny+1,nx+1))
  generated_data[:,:,:] = c0
  
  eta[vari, 1, :, :, :] = generated_data[:,:,:]
  
  writeMatrix2File(filename, eta)

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

def generate_comp_Icase0(common_config, comp_config):
  nz = common_config["nz"]
  ny = common_config["ny"]
  nx = common_config["nx"]
  nc = common_config["nc"]
  
  filename = comp_config["filename"]
  vari = comp_config["vari"]
  
  comp = np.zeros((nc+1, nz+1, ny+1, nx+1))
  generated_data = np.zeros((nc+1,nz+1,ny+1,nx+1))
  
  if(isinstance(vari, int)):
    comp[vari,:,:,:] = generated_data[:,:,:]
  elif(isinstance(vari, list)):
    for i in vari:
      comp[i,:,:,:] = generated_data[:,:,:]
    
    writeMatrix2File(filename,comp)

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

def generate_comp_Icase2(common_config, comp_config):
    nz = common_config["nz"]
    ny = common_config["ny"]
    nx = common_config["nx"]
    nc = common_config["nc"]
    
    filename = comp_config["filename"]
    rr = comp_config["rr"]
    vari = comp_config["vari"]
    
    comp = np.zeros((nc+1, nz+1, ny+1, nx+1))
    generated_tanh_data = generated_tanh_data(nx,ny,nz,rr)
    if(isinstance(vari, int)):
      comp[vari,:,:,:] = generated_tanh_data[:,:,:]
    elif(isinstance(vari, list)):
      for i in vari:
        comp[i,:,:,:] = generated_tanh_data[:,:,:]
    
    writeMatrix2File(filename,comp)

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
    
    
def writeMatrix2File(filename, data_array):
    #  eta dimension: (nv, mst, nz, ny, nx)
    # file format
    # nx ny nz mst nv
    # 1  1  1  1   1   xxx
    # 1  1  1  1   2   xxx
    # 1  1  1  1   3   xxx
    # ...
    # nx ny nz mst nv  xxx
    
    # comp dimension: (nc, nz, ny, nx)
    # file format
    # nx ny nz nc
    # 1  1  1  1  xxx
    # 1  1  1  1  xxx
    # 1  1  1  1  xxx
    # ...
    # nx ny nz nc xxx

    if(len(data_array.shape) == 5):
      nv_, mst_, nz_, ny_, nx_ = data_array.shape
      eta_dim = (nx_-1,ny_-1,nz_-1,mst_-1,nv_-1)
      
      entry_length = 16
      int_len = 6
      per = 7
      with open(filename,"w") as f:
          header_string =  "".join(str(" ")+(str(num)).rjust(int_len - 1) for num in eta_dim) + str(" ").rjust(entry_length) + " \n"
          f.write(header_string)
          for i in range(1,nx_) :
            for j in range(1, ny_):
              for k in range(1, nz_):
                for ii in range(1, mst_):
                  for jj in range(1, nv_):
                    data_index = (i, j, k, ii, jj)
                    data_format = "{:1}"+"{:"+f"{entry_length-1}.{per}"+ "E}"
                    data_string = "".join(str(" ")+str(num).rjust(int_len - 1) for num in data_index)  + data_format.format(" ", data_array[jj,ii,k,j,i]) + " \n"
                    f.write(data_string)
    
    elif(len(data_array.shape) == 4):
      nc_, nz_, ny_, nx_ = data_array.shape
      comp_dim =  (nx_-1,ny_-1,nz_-1,nc_-1)
      
      entry_length = 16
      int_len = 6
      per = 7
      with open(filename,"w") as f:
          header_string =  "".join(str(" ")+(str(num)).rjust(int_len - 1) for num in comp_dim) + str(" ").rjust(entry_length) + " \n"
          f.write(header_string)
          for i in range(1,nx_) :
              for j in range(1, ny_):
                  for k in range(1, nz_):
                      for ii in range(1, nc_):
                        data_index = (i, j, k, ii)
                        data_format = "{:1}"+"{:"+f"{entry_length-1}.{per}"+ "E}"
                        data_string = "".join(str(" ")+str(num).rjust(int_len - 1) for num in data_index)  + data_format.format(" ", data_array[ii,k,j,i]) + " \n"
                        f.write(data_string)

def r4_uniform_01(seed):
    i4_huge = 2147483647
    if(seed == 0):
        print(" ")
        print('R4_UNIFORM_01 - Fatal error!')
        print("  Input value of SEED = 0.")
        return
    k = seed / 127773
    seed = 16807 * (seed - k * 127773) - k * 2836
    if (seed < 0):
            seed = seed + i4_huge
    return float(seed) * 4.656612875E-10

def read_toml(file_name):
    with open(file_name) as f:
        data = toml.load(f)
        return data

def generateEtaFileWithConfig(common_config, eta_case_config, case):
    eta_selected_config = {}
    for config in eta_case_config:
      if(config["case"] == case):
        eta_selected_config = config
    if(len(eta_selected_config) == 0):
      raise AttributeError("The eta configuration was not successfully read")

    generated_function = globals()["generate_eta_Icase{}".format(case)]
    generated_function(common_config, eta_selected_config)

def generateCompFileWithConfig(common_config, comp_case_config,case):
    comp_selected_config = {}
    for config in comp_case_config:
      if(config["case"] == case):
        comp_selected_config = config
    if(len(comp_selected_config) == 0):
      raise AttributeError("The comp configuration was not successfully read")
    
    generated_function = globals()["generate_comp_Icase{}".format(case)]
    generated_function(common_config, comp_selected_config)


def main(toml_file="input.toml"):
    # Read input.toml, return a config dict
    total_config = read_toml(toml_file)
    # Get specific file config
    common_config = total_config["common_config"]
    eta_config    = total_config["eta_config"]
    comp_config   = total_config["comp_config"]
    eta_case_config = total_config["eta_case_config"]
    comp_case_config = total_config["comp_case_config"]
    eta_case = eta_config["set_eta_case"]
    comp_case = comp_config["set_comp_case"]
    print("eta case: {}, comp case: {}".format(eta_case, comp_case))

    if(eta_case != -1):
      print("Start to generate eta file")
      generateEtaFileWithConfig(common_config, eta_case_config,eta_case)
      print("Finish to generate eta file")
    if(comp_case != -1):
      print("Start to generate comp file")
      generateCompFileWithConfig(common_config, comp_case_config,comp_case)
      print("Finish to generate eta file")
    
if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('-f','--filename',default="input.toml", help='Path of configuration file for generating eta/comp data.')
  args = parser.parse_args()
  main(args.filename)
    
    