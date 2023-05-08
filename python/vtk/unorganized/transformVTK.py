# -*- coding: utf-8 -*-
# <nbformat>3.0</nbformat>

# <codecell>

file = open("strain.00000000.dat","r")

# <codecell>

lines = file.readlines()

# <codecell>

a=[]
b=[]
position=[]
data=[]
nx=48
ny=48
nz=48
nn=nx*ny*nz

# <codecell>

for line in lines[1:]:
    a.extend([map(float,line.rstrip().split())])
    position.extend([[a[-1][0],a[-1][1],a[-1][2]]])
    data.extend([a[-1][3]])

# <codecell>

file=open("strain.vtk","w")
file.write("# vtk DataFile Version 3.0\n")
file.write("Structured Grid Example\n")
file.write("ASCII\n")
file.write("\n")
file.write("DATASET STRUCTURED_POINTS\n")
dimension="DIMENSIONS "+str(nx)+" "+str(ny)+" "+str(nz)
file.write(dimension+"\n")
file.write("ORIGIN 1 1 1\n")
file.write("SPACING 1 1 1\n")
#file.write(("points "+str(nn)+" float\n"))
file.close()

# <codecell>

!type strain.vtk

# <codecell>

file=open("strain.vtk","a")
file.write("\n")
file.write(("POINT_DATA "+str(nn)+"\n"))
file.write(("SCALARS scalars float\n"))
file.write(("LOOKUP_TABLE default\n"))
file.close()

# <codecell>

file=open("strain.vtk","a")
for dat in data:
    file.write((str(dat)+"\n"))
file.close()

# <codecell>

%less strain.vtk

# <codecell>

file = open("elePlrz.00000000.dat","r")

# <codecell>

lines = file.readlines()

# <codecell>

a=[]
b=[]
position=[]
data=[]
nx=48
ny=48
nz=48
nn=nx*ny*nz

# <codecell>

for line in lines[1:]:
    a.extend([map(float,line.rstrip().split())])
    position.extend([[a[-1][0],a[-1][1],a[-1][2]]])
    data.extend([[a[-1][3],a[-1][4],a[-1][5]]])

# <codecell>

data[-1][-1]

# <codecell>

file=open("vector.vtk","w")
file.write("# vtk DataFile Version 3.0\n")
file.write("Structured Grid Example\n")
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

# <codecell>

file=open("vector.vtk","a")
for pos in data:
    #file.write((str(pos[0])+" "+str(pos[1])+" "+str(pos[2])+"\n"))
    file.write((str(pos[0])+" "+str(pos[1])+" "+str(pos[2])+"\n"))
file.close()

# <codecell>

%less vector.vtk

# <codecell>

 

