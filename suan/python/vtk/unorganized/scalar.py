file = open("conc.00000000.dat","r")

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
    data.extend([a[-1][3]])


file=open("stress.vtk","w")
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
file.write(("LOOKUP_TABLE default\n"))
file.close()

file=open("stress.vtk","a")
for dat in data:
    file.write((str(dat)+"\n"))
file.close()
