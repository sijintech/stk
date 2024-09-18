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


def write_structure_to_file(filename, nx, ny, nz, phip, phis, phim, phiv, structure_type):
  # 配置数据的格式化选项
  int_len = 5  # 整数长度
  entry_length = 15  # 每个数据条目的总长度
  per = 6  # 小数点后保留的精度

  with open(filename, 'w') as f:
    if structure_type == 1:
      # 第一种类型：直接写入四个相场变量
      f.write("x, y, z, phip, phis, phim, phiv\n")
      for ii in range(nx):
        for jj in range(ny):
          for kk in range(nz):
            data_index = [ii, jj, kk]
            data_array = [phip[ii, jj, kk], phis[ii, jj, kk], phim[ii, jj, kk], phiv[ii, jj, kk]]
            data_format = "{:1}" + "{:" + f"{entry_length - 1}.{per}" + "E}"
            data_string = "".join(str(" ") + str(num).rjust(int_len - 1) for num in data_index)
            for data_val in data_array:
              data_string += data_format.format(" ", data_val) + " \n"
            f.write(data_string)

    elif structure_type == 2:
      # 第二种类型：写入相位代码 (四位数字/字符串)
      f.write("x, y, z, phase_code\n")
      for ii in range(nx):
        for jj in range(ny):
          for kk in range(nz):
            # 生成四位相位代码
            phase_code = ['0', '0', '0', '0']
            if phip[ii, jj, kk] == 1.0:
              phase_code[0] = '1'
            if phis[ii, jj, kk] == 1.0:
              phase_code[1] = '2'
            if phiv[ii, jj, kk] == 1.0:
              phase_code[2] = '3'
            if phim[ii, jj, kk] == 1.0:
              phase_code[3] = '4'

            phase_code_str = ''.join(phase_code)

            # 写入数据
            data_index = [ii, jj, kk]
            data_format = "{:1}" + "{:" + f"{entry_length - 1}.{per}" + "E}"
            data_string = "".join(str(" ") + str(num).rjust(int_len - 1) for num in data_index)
            data_string += " " + phase_code_str + " \n"
            f.write(data_string)
