# project webpage is at https://nibiru-tech.gitlab.io/python-vtk/
# Data type macro
SCALAR=0
VECTOR=1
DOMAIN=2
piValue=3.141592653589

import os
import string
import numpy as np
from math import sqrt,acos

class MuproFormatter(string.Formatter): 
    def format_field(self, value, format_spec):
        #print(value)
        #print(format_spec)
        ss = string.Formatter.format_field(self,value,format_spec)
        a,b = format_spec.split('.');
        newA = str(int(a)-1)
        #print(a)
        #print(newA)
        newSpec = "{}.{}".format(newA,b)
        #print(newSpec)
        ssNew = string.Formatter.format_field(self,value,newSpec)
        #print(ssNew)
        if format_spec.endswith('E'):
            if ( 'E' in ss):
                mantissa, exp = ss.split('E')
                num=int(exp[1:])
                if num >= 0 and num < 100:
                    mantissa, exp = ssNew.split('E')
                    return mantissa + 'E' + exp[0] + '0' + exp[1:]
                elif num > 100:
                    return mantissa + 'E' + exp
                else :
                    print("the exponential out of range")
                    return mantissa + 'E' + exp
        return ss

class Data(object):
    """ The basis data IO class to convert file between different formats
    
    :param in_file: A string, the input file name
    :param data_type: An integer, the data type macro
    :param data_index: An integer, choose the component to plot, if there are multiple columns
    """

    def __init__(self,in_file="",data_type=SCALAR):
        self.in_file = in_file
        self.out_file = ""
        self.data_type = data_type
        self.data_index = 0
        self.domain_threshold = 0.05
        self.domain_angle_range = 180.0
        self.data = 0
        domainRGB=np.zeros((27,3))
        domainRGB[0][0]=0.752912;domainRGB[0][1]=0.752912;domainRGB[0][2]=0.752912 #sub
        domainRGB[1][0]=0;domainRGB[1][1]=0;domainRGB[1][2]=1 #R1+
        domainRGB[2][0]=0.46;domainRGB[2][1]=0.7175;domainRGB[2][2]=0.8135 #R1-
        domainRGB[3][0]=0;domainRGB[3][1]=0.1537870;domainRGB[3][2]=0.0 #R2+
        domainRGB[4][0]=0;domainRGB[4][1]=1;domainRGB[4][2]=0 #R2-
        domainRGB[5][0]=1;domainRGB[5][1]=0;domainRGB[5][2]=0 #R3+
        domainRGB[6][0]=1;domainRGB[6][1]=0.566921;domainRGB[6][2]=0.633741 #R3-
        domainRGB[7][0]=1;domainRGB[7][1]=0.418685;domainRGB[7][2]=0 #R4+
        domainRGB[8][0]=1;domainRGB[8][1]=1;domainRGB[8][2]=0 #R4-
        domainRGB[9][0]=1;domainRGB[9][1]=0;domainRGB[9][2]=1 #O1+
        domainRGB[10][0]=0.64629;domainRGB[10][1]=0.130165;domainRGB[10][2]=0.130165 #O1-
        domainRGB[11][0]=0.9;domainRGB[11][1]=0.566921;domainRGB[11][2]=0.633741 #O2+
        domainRGB[12][0]=0.751111;domainRGB[12][1]=0.393695;domainRGB[12][2]=0.751111 #O2-
        domainRGB[13][0]=0.418685;domainRGB[13][1]=0.027128;domainRGB[13][2]=0.027128 #O3+
        domainRGB[14][0]=0.678201;domainRGB[14][1]=0.498270;domainRGB[14][2]=0.301423 #O3-
        domainRGB[15][0]=0.476371;domainRGB[15][1]=0.035432;domainRGB[15][2]=0.14173 #O4+
        domainRGB[16][0]=0.961169;domainRGB[16][1]=0.251965;domainRGB[16][2]=0.199862 #O4-
        domainRGB[17][0]=0.355309;domainRGB[17][1]=0.968874;domainRGB[17][2]=0.355309 #O5+
        domainRGB[18][0]=0.038446;domainRGB[18][1]=0.646290;domainRGB[18][2]=0.038446 #O5-
        domainRGB[19][0]=0.766921;domainRGB[19][1]=0.766921;domainRGB[19][2]=0.766921 #O6+
        domainRGB[20][0]=0.169550;domainRGB[20][1]=0.169550;domainRGB[20][2]=0.169550 #O6-
        domainRGB[21][0]=0.566921;domainRGB[21][1]=0.566921;domainRGB[21][2]=0.566921 #a1+
        domainRGB[22][0]=0.393695;domainRGB[22][1]=0.015747;domainRGB[22][2]=0.885813 #a1-
        domainRGB[23][0]=0.0;domainRGB[23][1]=0.0;domainRGB[23][2]=0.0 #a2+
        domainRGB[24][0]=1.0;domainRGB[24][1]=0.710881;domainRGB[24][2]=0.0 #a2-
        domainRGB[25][0]=0.885813;domainRGB[25][1]=0.813533;domainRGB[25][2]=0.301423 #c+
        domainRGB[26][0]=0.8867188;domainRGB[26][1]=0.4335937;domainRGB[26][2]=0.0273438 #c-
        self.domain_rgb=domainRGB
        self.__get_array__()

    def __get_file_type__(self,file_name):
        file_path,extension = os.path.splitext(file_name)
        return extension

    def __read_dat_scalar__(self,file_name):
        file = open(file_name,"r")
        lines = file.readlines()
        a=[]
        firstLine=lines[0].rstrip().split()
        nx=int(firstLine[0])
        ny=int(firstLine[1])
        nz=int(firstLine[2])
        secondLine=lines[1].rstrip().split()
        indexs=len(secondLine)-3
        data=np.zeros((nx,ny,nz,indexs))
        for line in lines[1:]:
            a=list(map(float,line.rstrip().split()))
            x=int(a[0])
            y=int(a[1])
            z=int(a[2])
            for index in range(0,indexs):
                data[x-1,y-1,z-1,index]=a[2+index+1]
        return data

    def __read_dat_vector__(self,file_name):
        file = open(file_name,"r")
        lines = file.readlines()
        a=[]
        firstLine=lines[0].rstrip().split()
        nx=int(firstLine[0])
        ny=int(firstLine[1])
        nz=int(firstLine[2])
        secondLine=lines[1].rstrip().split()
        indexs=int(len(secondLine)/3-1)
        data=np.zeros((nx,ny,nz,indexs,3))
        for i in lines[1:]:
            a=list(map(float,i.rstrip().split()))
            x=int(a[0])
            y=int(a[1])
            z=int(a[2])
            for index in range(0,indexs):
                data[x-1,y-1,z-1,index,0]=a[2+index*3+1]
                data[x-1,y-1,z-1,index,1]=a[2+index*3+2]
                data[x-1,y-1,z-1,index,2]=a[2+index*3+3]
        return data;

    def __get_vector_rgb__(self,vector,style):
        pass

    def __get_domain_rgb__(self,domain_label):

        rgb = self.domain_rgb[int(domain_label)]
        return rgb

    def __get_domain_type__(self,px,py,pz,stdValue=0.1,stdAngle=180):
        length=sqrt(px*px+py*py+pz*pz)
        # domainRGB=np.zeros((27,3))
        domainOrth=np.zeros((27,3))
        # domainTypeLabel=['label']*27

        domainOrth[0][0] = 0;domainOrth[0][1]=0;domainOrth[0][2]=0
        domainOrth[1][0] = 1/sqrt(3);domainOrth[1][1]=1/sqrt(3);domainOrth[1][2]=1/sqrt(3)
        domainOrth[2][0] = -1/sqrt(3);domainOrth[2][1]=-1 / sqrt(3);domainOrth[2][2]=-1 / sqrt(3)
        domainOrth[3][0] = -1 / sqrt(3);domainOrth[3][1]=1/sqrt(3);domainOrth[3][2]=1/sqrt(3)
        domainOrth[4][0] = 1/sqrt(3);domainOrth[4][1]=-1 / sqrt(3);domainOrth[4][2]=-1 / sqrt(3)
        domainOrth[5][0] = -1 / sqrt(3);domainOrth[5][1]= -1 / sqrt(3);domainOrth[5][2]=1/sqrt(3)
        domainOrth[6][0] = 1/sqrt(3);domainOrth[6][1]=1/sqrt(3);domainOrth[6][2]=-1 / sqrt(3)
        domainOrth[7][0] = 1/sqrt(3);domainOrth[7][1]=-1 / sqrt(3);domainOrth[7][2]=1/sqrt(3)
        domainOrth[8][0] = -1 / sqrt(3);domainOrth[8][1]=1/sqrt(3);domainOrth[8][2]=-1 / sqrt(3)
        domainOrth[9][0] =  1/sqrt(2);domainOrth[9][1]=1/sqrt(2);domainOrth[9][2]=0
        domainOrth[10][0]= -1 / sqrt(2);domainOrth[10][1]=-1 / sqrt(2);domainOrth[10][2]=0
        domainOrth[11][0]= 1/sqrt(2);domainOrth[11][1]=-1 / sqrt(2);domainOrth[11][2]=0
        domainOrth[12][0]= -1 / sqrt(2);domainOrth[12][1]=1/sqrt(2);domainOrth[12][2]=0
        domainOrth[13][0]= 1/sqrt(2);domainOrth[13][1]=0;domainOrth[13][2]=1/sqrt(2)
        domainOrth[14][0]= -1 / sqrt(2);domainOrth[14][1]=0;domainOrth[14][2]=-1 / sqrt(2)
        domainOrth[15][0]= 1/sqrt(2);domainOrth[15][1]=0;domainOrth[15][2]=-1 / sqrt(2)
        domainOrth[16][0]= -1 / sqrt(2);domainOrth[16][1]=0;domainOrth[16][2]=1/sqrt(2)
        domainOrth[17][0]=0;domainOrth[17][1]=1/sqrt(2);domainOrth[17][2]=1/sqrt(2)
        domainOrth[18][0]=0;domainOrth[18][1]=-1 / sqrt(2);domainOrth[18][2]=-1 / sqrt(2)
        domainOrth[19][0]=0;domainOrth[19][1]=1/sqrt(2);domainOrth[19][2]=-1 / sqrt(2)
        domainOrth[20][0]=0;domainOrth[20][1]=-1 / sqrt(2);domainOrth[20][2]=1/sqrt(2)
        domainOrth[21][0]=1;domainOrth[21][1]=0;domainOrth[22][2]=0
        domainOrth[22][0]=-1;domainOrth[22][1]=0;domainOrth[22][2]=0
        domainOrth[23][0]=0;domainOrth[23][1]=1;domainOrth[23][2]=0
        domainOrth[24][0]=0;domainOrth[24][1]=-1;domainOrth[24][2]=0
        domainOrth[25][0]=0;domainOrth[25][1]=0;domainOrth[25][2]=1
        domainOrth[26][0]=0;domainOrth[26][1]=0;domainOrth[26][2]=-1

        domainValue=-1
        hold = piValue
        # print("%f,%f" % (length,stdValue))
        if length>stdValue:
            for i in range(0,27):
                cosValue = (px*domainOrth[i][0]+py*domainOrth[i][1]+pz*domainOrth[i][2])/length;
                if cosValue > 1:
                    angle=0
                elif cosValue < -1:
                    angle=piValue
                else:
                    angle=acos(cosValue)

                if angle < stdAngle and angle < hold:
                    hold=angle;
                    domainValue=i
            # print("%f,%f,%f" % (cosValue,domainValue,angle))
        return domainValue

    def __read_dat_domain__(self,file_name,stdValue,angleDegree):
        file = open(file_name,"r")
        lines = file.readlines()
        angleRad=angleDegree/180.0*piValue
        domainTypeCount = 27
        a=[]
        firstLine=lines[0].rstrip().split()
        nx=int(firstLine[0])
        ny=int(firstLine[1])
        nz=int(firstLine[2])
        data=self.__read_dat_vector__(file_name)
        vector=np.zeros((nx,ny,nz,3))
        domainIndex=np.zeros((nx,ny,nz))
        domainCount=np.zeros(domainTypeCount)
        domainPercent=np.zeros(domainTypeCount)
        domainCountTotal = 0
        if data.shape[3] == 1:
            vector = data[:,:,:,0,:]
        elif data.shape[3] == 2:
            vector = data[:,:,:,1,:]
        else:
            print("Something wrong with the domain file format, only 3 or 6 columns is acceptable")

        print(np.sum(data))
        for i in range(0,nx):
            for j in range(0,ny):
                for k in range(0,nz):
                    # print("data:%f,%f,%f" % (data[i,j,k,1,0],data[i,j,k,1,1],data[i,j,k,1,2]))
                    domainIndex[i][j][k]=self.__get_domain_type__(vector[i][j][k][0],
                                                    vector[i][j][k][1],
                                                    vector[i][j][k][2],stdValue,angleRad)
                    if domainIndex[i][j][k]!=-1:
                        domainCount[int(domainIndex[i][j][k])]=domainCount[int(domainIndex[i][j][k])]+1

        for i in range(1,domainTypeCount):
            domainCountTotal = domainCountTotal + domainCount[i]
        # print(domainCountTotal)
        for i in range(1,domainTypeCount):
            domainPercent[i] = domainCount[i]/domainCountTotal

        return domainIndex

    def __write_vtk_scalar__(self,file_name,data):
        nx,ny,nz,scalar_i=data.shape
        nn=nx*ny*nz
        file=open(file_name,"w")
        file.write("# vtk DataFile Version 3.0\n")
        file.write("Structured Points\n")
        file.write("ASCII\n")
        file.write("\n")
        file.write("DATASET STRUCTURED_POINTS\n")
        dimension="DIMENSIONS "+str(nx)+" "+str(ny)+" "+str(nz)
        file.write(dimension+"\n")
        file.write("ORIGIN 1 1 1\n")
        file.write("SPACING 1 1 1\n")
        file.write(("POINT_DATA "+str(nn)+"\n"))
        file.write("\n")
        file.close()

        for data_index in range(0,scalar_i):
            file=open(file_name,"a")
            file.write("SCALARS scalars%i float\n" % (data_index))
            file.write(("LOOKUP_TABLE default\n"))
            for k in range(0,nz):
                for j in range(0,ny):
                    for i in range(0,nx):
                        file.write((str(data[i][j][k][data_index])+"\n"))
            file.write("\n")
            file.close()

    def __write_vtk_vector__(self,file_name,data):
        nx,ny,nz,vector_i,vector_dim=data.shape
        nn=nx*ny*nz
        file=open(file_name,"w")
        file.write("# vtk DataFile Version 3.0\n")
        file.write("Structured Points Example\n")
        file.write("ASCII\n")
        file.write("\n")
        file.write("DATASET STRUCTURED_POINTS\n")
        dimension="DIMENSIONS "+str(nx)+" "+str(ny)+" "+str(nz)
        file.write(dimension+"\n")
        file.write("ORIGIN 0 0 0\n")
        file.write("SPACING 1 1 1\n")
        file.write(("POINT_DATA "+str(nn)+"\n"))
        #file.write(("points "+str(nn)+" float\n"))
        file.write("\n")
        # file.write(("LOOKUP_TABLE default\n"))
        file.close()

        for data_index in range(0,vector_i):
            file=open(file_name,"a")
            file.write("VECTORS vector%i float\n" % (data_index))
            for k in range(0,nz):
                for j in range(0,ny):
                    for i in range(0,nx):
                        dat = data[i][j][k][data_index]
                        file.write((str(dat[0])+" "+str(dat[1])+" "+str(dat[2])+"\n"))
            file.write("\n")
            file.close()

    def __write_vtk_domain__(self,file_name,data):
        nx,ny,nz=data.shape
        nn=nx*ny*nz
        file=open(file_name,"w")
        file.write("# vtk DataFile Version 3.0\n")
        file.write("Structured Points\n")
        file.write("ASCII\n")
        file.write("\n")
        file.write("DATASET STRUCTURED_POINTS\n")
        dimension="DIMENSIONS "+str(nx)+" "+str(ny)+" "+str(nz)
        file.write(dimension+"\n")
        file.write("ORIGIN 1 1 1\n")
        file.write("SPACING 1 1 1\n")
        file.write("\n")
        file.write(("POINT_DATA "+str(nn)+"\n"))
        file.write(("SCALARS scalars float\n"))
        file.write(("LOOKUP_TABLE mupro\n"))
        file.close()

        file=open(file_name,"a")
        for k in range(0,nz):
            for j in range(0,ny):
                for i in range(0,nx):
                    file.write((str(data[i][j][k])+"\n"))
        file.close()

        file=open(file_name,"a")
        file.write("\nLOOKUP_TABLE mupro 27\n")
        file.write(("1 1 1 0\n"))    
        for i in range(0,27):
            dat = self.domain_rgb[i]
            file.write((str(dat[0])+" "+str(dat[1])+" "+str(dat[2])+" 1\n"))    
        # for i in range(0,nx):
        #     for j in range(0,ny):
        #         for k in range(0,nz):
        #             dat = self.__get_domain_rgb__(data[i][j][k])
        #             file.write((str(dat[0])+" "+str(dat[1])+" "+str(dat[2])+"\n"))       
        file.close()

    def __write_dat_scalar__(self,file_name,data):
        xmin=1
        ymin=1
        zmin=1
        xmax=data.shape[0]+xmin-1
        ymax=data.shape[1]+ymin-1
        zmax=data.shape[2]+zmin-1
        file=open(file_name,"w")
        dimension="{:6d}{:6d}{:6d}".format(xmax-xmin+1,ymax-ymin+1,zmax-zmin+1)
        file.write(dimension+" \n")
        FORMAT='{0:16.7E}'
        if len(data.shape)==4:
            indexLength = data.shape[-1]
        else:
            print("The dimension of your data is not 4, pleaser double check")
            
        formatString='{:>16}'*indexLength
        for i in range(xmin-1,xmax):
            for j in range(ymin-1,ymax):
                for k in range(zmin-1,zmax):
                    position="{:6d}{:6d}{:6d}".format(i+2-xmin,j+2-ymin,k+2-zmin)
                    toFormatString=[]
                    for m in range(0,indexLength):
                        toFormatString.append(MuproFormatter().format(FORMAT,data[i,j,k,m]))
                    value=formatString.format(*toFormatString)
                    file.write('{}{} \n'.format(position,value))
        file.close()

    def __write_dat_vector__(self,file_name,data):
        nx,ny,nz,vector_index,vector_dimension=data.shape
        if vector_dimension != 3:
            print("The vector dimension must be 3, only support 3D vector.")
        data_vector = np.zeros((nx,ny,nz,vector_index*3))
        for i in range(0,vector_index):
            data_vector[:,:,:,i*3]=data[:,:,:,i,0]
            data_vector[:,:,:,i*3+1]=data[:,:,:,i,1]
            data_vector[:,:,:,i*3+2]=data[:,:,:,i,2]
        self.__write_dat_scalar__(file_name,data_vector)

    # def __write_dat_domain__(self,file_name,data):
    #     pass

    def __dat_2_array__(self,file_name):
        if self.data_type == SCALAR:
            data = self.__read_dat_scalar__(file_name)
        elif self.data_type == VECTOR:
            data = self.__read_dat_vector__(file_name)
        elif self.data_type == DOMAIN:
            data = self.__read_dat_domain__(file_name,self.domain_threshold,self.domain_angle_range)
        else:
            print("The data type is not Scalar, vector, neither domain. Please choose among these three.")
        return data;

    def __get_array__(self):
        if self.__get_file_type__(self.in_file) == ".dat":
            data = self.__dat_2_array__(self.in_file)
        else:
            print("Now only support input of dat file. Please set Data.in_file to be a .dat file")
            data = 0
        self.data = data
        return data

    def __array_2_vtk__(self,file_name,data):
        if self.data_type == SCALAR:
            self.__write_vtk_scalar__(file_name,data)
        elif self.data_type == VECTOR:
            self.__write_vtk_vector__(file_name,data)
        elif self.data_type == DOMAIN:
            self.__write_vtk_domain__(file_name,data)
        else:
            print("The data type is not Scalar, vector, neither domain. Please choose among these three.")

    def __array_2_dat__(self,file_name,data):
        if self.data_type == SCALAR:
            self.__write_dat_scalar__(file_name,data)
        elif self.data_type == VECTOR:
            self.__write_dat_vector__(file_name,data)
        elif self.data_type == DOMAIN:
            print("Cannot output domain data for dat file, please choose vector style instead.")
        else:
            print("The data type is not Scalar, vector, neither domain. Please choose among these three.")
        
    def get_np_array(self):
        return self.data

    def get_dat_file(self,out_file):
        self.__array_2_dat__(out_file,self.data)

    def get_vtk_file(self,out_file):
        self.__array_2_vtk__(out_file,self.data)





# domainTypeLabel[0]  = "    Substrate"
# domainTypeLabel[1]  = "R1+( 1, 1, 1)"
# domainTypeLabel[2]  = "R1-(-1,-1,-1)"
# domainTypeLabel[3]  = "R2+(-1, 1, 1)"
# domainTypeLabel[4]  = "R2-( 1,-1,-1)"
# domainTypeLabel[5]  = "R3+(-1,-1, 1)"
# domainTypeLabel[6]  = "R3-( 1, 1,-1)"
# domainTypeLabel[7]  = "R4+( 1,-1, 1)"
# domainTypeLabel[8]  = "R4-(-1, 1,-1)"
# domainTypeLabel[9]  = "O1+( 1, 1, 0)"
# domainTypeLabel[10] = "O1-(-1,-1, 0)"
# domainTypeLabel[11] = "O2+( 1,-1, 0)"
# domainTypeLabel[12] = "O2-(-1, 1, 0)"
# domainTypeLabel[13] = "O3+( 1, 0, 1)"
# domainTypeLabel[14] = "O3-(-1, 0,-1)"
# domainTypeLabel[15] = "O4+( 1, 0,-1)"
# domainTypeLabel[16] = "O4-(-1, 0, 1)"
# domainTypeLabel[17] = "O5+( 0, 1, 1)"
# domainTypeLabel[18] = "O5-( 0,-1,-1)"
# domainTypeLabel[19] = "O6+( 0, 1,-1)"
# domainTypeLabel[20] = "O6-( 0,-1, 1)"
# domainTypeLabel[21] = "a1+( 1, 0, 0)"
# domainTypeLabel[22] = "a1-(-1, 0, 0)"
# domainTypeLabel[23] = "a2+( 0, 1, 0)"
# domainTypeLabel[24] = "a2-( 0,-1, 0)"
# domainTypeLabel[25] = " C+( 0, 0, 1)"
# domainTypeLabel[26] = " C-( 0, 0,-1)"

# domainRGB[0][0]=0.752912;domainRGB[0][1]=0.752912;domainRGB[0][2]=0.752912 #sub
# domainRGB[1][0]=0;domainRGB[1][1]=0;domainRGB[1][2]=1 #R1+
# domainRGB[2][0]=0.46;domainRGB[2][1]=0.7175;domainRGB[2][2]=0.8135 #R1-
# domainRGB[3][0]=0;domainRGB[3][1]=0.1537870;domainRGB[3][2]=0.0 #R2+
# domainRGB[4][0]=0;domainRGB[4][1]=1;domainRGB[4][2]=0 #R2-
# domainRGB[5][0]=1;domainRGB[5][1]=0;domainRGB[5][2]=0 #R3+
# domainRGB[6][0]=1;domainRGB[6][1]=0.566921;domainRGB[6][2]=0.633741 #R3-
# domainRGB[7][0]=1;domainRGB[7][1]=0.418685;domainRGB[7][2]=0 #R4+
# domainRGB[8][0]=1;domainRGB[8][1]=1;domainRGB[8][2]=0 #R4-
# domainRGB[9][0]=1;domainRGB[9][1]=0;domainRGB[9][2]=1 #O1+
# domainRGB[10][0]=0.64629;domainRGB[10][1]=0.130165;domainRGB[10][2]=0.130165 #O1-
# domainRGB[11][0]=0.9;domainRGB[11][1]=0.566921;domainRGB[11][2]=0.633741 #O2+
# domainRGB[12][0]=0.751111;domainRGB[12][1]=0.393695;domainRGB[12][2]=0.751111 #O2-
# domainRGB[13][0]=0.418685;domainRGB[13][1]=0.027128;domainRGB[13][2]=0.027128 #O3+
# domainRGB[14][0]=0.678201;domainRGB[14][1]=0.498270;domainRGB[14][2]=0.301423 #O3-
# domainRGB[15][0]=0.476371;domainRGB[15][1]=0.035432;domainRGB[15][2]=0.14173 #O4+
# domainRGB[16][0]=0.961169;domainRGB[16][1]=0.251965;domainRGB[16][2]=0.199862 #O4-
# domainRGB[17][0]=0.355309;domainRGB[17][1]=0.968874;domainRGB[17][2]=0.355309 #O5+
# domainRGB[18][0]=0.038446;domainRGB[18][1]=0.646290;domainRGB[18][2]=0.038446 #O5-
# domainRGB[19][0]=0.766921;domainRGB[19][1]=0.766921;domainRGB[19][2]=0.766921 #O6+
# domainRGB[20][0]=0.169550;domainRGB[20][1]=0.169550;domainRGB[20][2]=0.169550 #O6-
# domainRGB[21][0]=0.566921;domainRGB[21][1]=0.566921;domainRGB[21][2]=0.566921 #a1+
# domainRGB[22][0]=0.393695;domainRGB[22][1]=0.015747;domainRGB[22][2]=0.885813 #a1-
# domainRGB[23][0]=0.0;domainRGB[23][1]=0.0;domainRGB[23][2]=0.0 #a2+
# domainRGB[24][0]=1.0;domainRGB[24][1]=0.710881;domainRGB[24][2]=0.0 #a2-
# domainRGB[25][0]=0.885813;domainRGB[25][1]=0.813533;domainRGB[25][2]=0.301423 #c+
# domainRGB[26][0]=0.8867188;domainRGB[26][1]=0.4335937;domainRGB[26][2]=0.0273438 #c-
