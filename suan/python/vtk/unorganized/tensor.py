file = open("stress.00000000.dat","r")

lines = file.readlines()

a=[]
temp=[]
position=[]
data=[]

temp.extend(map(float,lines[0].rstrip().split()))
nx=int(temp[0])
ny=int(temp[1])
nz=int(temp[2])
nn=nx*ny*nz
#x, y, z, tensor11,12,13,21,22,23,31,32,33


for line in lines[1:]:
    a.extend([map(float,line.rstrip().split())])
    position.extend([[a[-1][0],a[-1][1],a[-1][2]]])
    data.extend([[a[-1][3],a[-1][4],a[-1][5],a[-1][6],a[-1][7],a[-1][8]]])

#structured_points
file=open("tensor.vtk","w")
file.write("# vtk DataFile Version 3.0\n")
file.write("Structured Points Example\n")
file.write("ASCII\n")
file.write("\n")
file.write("DATASET STRUCTURED_POINTS\n")
dimension="DIMENSIONS "+str(nz)+" "+str(ny)+" "+str(nx)
file.write(dimension+"\n")
file.write("ORIGIN 0 0 0\n")
file.write("SPACING 1 1 1\n")
#file.write(("points "+str(nn)+" float\n"))
file.write("\n")
file.write(("POINT_DATA "+str(nn)+"\n"))
#file.write(("LOOKUP_TABLE default\n"))
file.write(("TENSORS strain float\n"))
file.close()

file=open("tensor.vtk","a")
for dat in data:
    file.write((str(dat[0])+" "+str(dat[5])+" "+str(dat[4])+"\n"))
    file.write((str(dat[5])+" "+str(dat[1])+" "+str(dat[3])+"\n"))
    file.write((str(dat[4])+" "+str(dat[3])+" "+str(dat[2])+"\n"))
    file.write(("\n"))
file.close()
