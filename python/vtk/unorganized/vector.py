file = open("concGrad.00000000.dat","r")

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
for line in lines[1:]:
    a.extend([map(float,line.rstrip().split())])
    position.extend([[a[-1][0],a[-1][1],a[-1][2]]])
    data.extend([[a[-1][3],a[-1][4],a[-1][5]]])


file=open("vector.vtk","w")
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
file.write(("VECTORS dispV float\n"))
file.close()

file=open("vector.vtk","a")
for dat in data:
    #file.write((str(pos[0])+" "+str(pos[1])+" "+str(pos[2])+"\n"))
    file.write((str(dat[0])+" "+str(dat[1])+" "+str(dat[2])+"\n"))
file.close()
