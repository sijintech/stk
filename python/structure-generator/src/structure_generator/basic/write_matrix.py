import numpy


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