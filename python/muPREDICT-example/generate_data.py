import numpy as np

class MyNumber:
    def __init__(self,val):
        self.val = val
    
    def __format__(self,format_spec):
        ss = ('{0:' + format_spec+'}').format(self.val)
        if('E' in ss):
            mantissa, exp = ss.split('E')
            return mantissa + 'E' + exp[0] + '0' + exp[1:]
        
        return ss

def generateDataIcase1(filename):
    nz = 60
    ny = 128
    nx = 128
    rr = 10
    nv = 3
    mst = 2
    vari = 1
    eta = np.zeros((nv + 1, mst + 1 , nz + 1,ny + 1,nx + 1))
    for i in range(1, nx+1):
        for j in range(1, ny+1):
            for k in range(1, nz+1):
                if(float((k-nz/2)**2 + (j-ny/2)**2 + (i-nx/2)**2) <= float(rr)**2):
                    eta[vari, 1, k, j, i] = 1.0
    
    writeMatrix2File(filename, eta)

def generateDataIcase2(filename):
    nz = 60
    ny = 128
    nx = 128
    rr = 10
    nv = 3
    mst = 2
    vari = 1
    eta = np.zeros((nv + 1, mst + 1 , nz + 1,ny + 1,nx + 1))
    for i in range(1, nx+1):
        for j in range(1, ny+1):
            for k in range(1, nz+1):
                distance = np.sqrt((k-nz/2)**2 + (j-ny/2)**2 + (i-nx/2)**2)
                eta[vari, 1, k, j, i] = (1.0 - np.tanh(1.0 * (distance - rr))) / 2.0
    
    writeMatrix2File(filename, eta)

def generateDataIcase3(filename):
    nz = 60
    ny = 128
    nx = 128
    rr = 10
    nv = 3
    mst = 2
    ptclnum = 10
    t1 = 2
    iseed = 10
    
    eta = np.zeros((nv + 1, mst + 1 , nz + 1,ny + 1,nx + 1))
    nv_list = np.ones(nv,dtype=np.int64)
    for pp in range(1, ptclnum+1):
        for t1 in range(1,mst+1):
            for s in range(1, nv_list[t1]+1):
                x_temp = int(float(nx)*r4_uniform_01(iseed))
                y_temp = int(float(ny)*r4_uniform_01(iseed)) 
                z_temp = int(float(nz)*r4_uniform_01(iseed))
                
                overlapp = 0
                for kk in range(1, nx+1):
                    for jj in range(1,ny+1):
                        for ii in range(1, nx+1):
                            if(float((ii-nz/2)**2 + (jj-ny/2)**2 + (kk-nx/2)**2) <= float(rr)**2):
                                for j in range(1, mst+1):
                                    for i in range(1, nv_list[j]+1):
                                        if(eta[i,j,ii,jj,kk] >= 0.8):
                                            overlapp = overlapp + 1
                                            
                if(overlapp == 0):
                    print(f"{pp}-th nucleus of {s}-th variant is at: {x_temp} {y_temp} {z_temp}")
                    for kk in range(1, nx+1):
                        for jj in range(1, ny+1):
                            for ii in range(1,nz+1):
                                if(float((ii-nz/2)**2 + (jj-ny/2)**2 + (kk-nx/2)**2) <= float(rr)**2):
                                    eta[s,t1,ii,jj,kk] = 1.0
    writeMatrix2File(filename, eta)
    
    
def writeMatrix2File(filename, eta):
    #  eta dimension: (nv, mst, nz, ny, nx)
    # file format
    # nx ny nz mst nv
    # 1  1  1  1   1   xxx
    # 1  1  1  1   2   xxx
    # 1  1  1  1   3   xxx
    # ...
    # nx ny nz mst nv  xxx
    
    nv, mst, nz, ny, nx = eta.shape
    eta_dim = (nx-1,ny-1,nz-1,mst-1,nv-1)
    
    entry_length = 16
    int_len = 6
    per = 7
    with open(filename,"w") as f:
        header_string =  "".join(str(" ")+(str(num)).rjust(int_len - 1) for num in eta_dim) + str(" ").rjust(entry_length) + " \n"
        f.write(header_string)
        for i in range(1,nx) :
            for j in range(1, ny):
                for k in range(1, nz):
                    for ii in range(1, mst):
                        for jj in range(1, nv):
                            data = (i, j, k, ii, jj)
                            data_format = "{:1}"+"{:"+f"{entry_length-1}.{per}"+ "E}"
                            data_string = "".join(str(" ")+str(num).rjust(int_len - 1) for num in data)  + data_format.format(" ", eta[jj,ii,k,j,i]) + " \n"
                            f.write(data_string)
    print(header_string)

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

if __name__ == '__main__':
    # nz = 60
    # ny = 128
    # nx = 128
    # rr = 10
    # nv = 3
    # mst = 2
    # vari = 10
    # eta = np.zeros((nv + 1, mst + 1 , nz + 1,ny + 1,nx + 1))
    # print(np.ndindex(eta.shape))
    # print(eta.reshape(-1))
    # writeMatrix2File("./test.dat", eta)
    # generateDataIcase1("icase1.dat")
    # generateDataIcase2("icase2.dat")
    generateDataIcase3("icase3.dat")