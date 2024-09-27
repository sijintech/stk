import numpy as np
from math import sqrt,acos

piValue=3.141592653589

def getBox(filename):
	file = open(filename,"r")
	lines = file.readline()
	firstLine=lines.rstrip().split()
	nx=int(firstLine[0])
	ny=int(firstLine[1])
	nz=int(firstLine[2])
	return [nx,ny,nz]



def readDatScalar(filename):
	file = open(filename,"r")
	lines = file.readlines()
	a=[]
	firstLine=lines[0].rstrip().split()
	nx=int(firstLine[0])
	ny=int(firstLine[1])
	nz=int(firstLine[2])
	secondLine=lines[1].rstrip().split()
	indexs=len(secondLine)-3
	data=np.zeros((nx,ny,nz,indexs))
	n=1;
	for line in lines[1:]:
		a=list(map(float,line.rstrip().split()))
		x=int(a[0])
		y=int(a[1])
		z=int(a[2])
		for index in range(0,indexs):
			data[x-1,y-1,z-1,index]=a[2+index+1]
	return data;


def readDatDisp(filename,scale):
	file = open(filename,"r")
	lines = file.readlines()
	a=[]
	firstLine=lines[0].rstrip().split()
	nx=int(firstLine[0])
	ny=int(firstLine[1])
	nz=int(firstLine[2])
	secondLine=lines[1].rstrip().split()
	indexs=len(secondLine)-3
	data=np.zeros((nx,ny,nz,indexs))
	n=1;
	if indexs != 3:
		print("The file does not have 6 columns")
		exit()

	for line in lines[1:]:
		a=list(map(float,line.rstrip().split()))
		x=int(a[0])
		y=int(a[1])
		z=int(a[2])
		for index in range(0,indexs):
			data[x-1,y-1,z-1,index]=a[2+index+1]*scale[index]+a[index]
	return data;


def readDatVector(filename):
	file = open(filename,"r")
	lines = file.readlines()
	a=[]
	a=getBox(filename)
	nx=a[0]
	ny=a[1]
	nz=a[2]
	secondLine=lines[1].rstrip().split()
	indexs=int(len(secondLine)/3-1)
	data=np.zeros((nx,ny,nz,indexs,3))
	n=1;
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

def getDomainType(px,py,pz,stdValue=0.1,stdAngle=180):
	length=sqrt(px*px+py*py+pz*pz)
	domainRGB=np.zeros((27,3))
	domainOrth=np.zeros((27,3))
	domainTypeLabel=['label']*27

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


	domainTypeLabel[0]  = "    Substrate"
	domainTypeLabel[1]  = "R1+( 1, 1, 1)"
	domainTypeLabel[2]  = "R1-(-1,-1,-1)"
	domainTypeLabel[3]  = "R2+(-1, 1, 1)"
	domainTypeLabel[4]  = "R2-( 1,-1,-1)"
	domainTypeLabel[5]  = "R3+(-1,-1, 1)"
	domainTypeLabel[6]  = "R3-( 1, 1,-1)"
	domainTypeLabel[7]  = "R4+( 1,-1, 1)"
	domainTypeLabel[8]  = "R4-(-1, 1,-1)"
	domainTypeLabel[9]  = "O1+( 1, 1, 0)"
	domainTypeLabel[10] = "O1-(-1,-1, 0)"
	domainTypeLabel[11] = "O2+( 1,-1, 0)"
	domainTypeLabel[12] = "O2-(-1, 1, 0)"
	domainTypeLabel[13] = "O3+( 1, 0, 1)"
	domainTypeLabel[14] = "O3-(-1, 0,-1)"
	domainTypeLabel[15] = "O4+( 1, 0,-1)"
	domainTypeLabel[16] = "O4-(-1, 0, 1)"
	domainTypeLabel[17] = "O5+( 0, 1, 1)"
	domainTypeLabel[18] = "O5-( 0,-1,-1)"
	domainTypeLabel[19] = "O6+( 0, 1,-1)"
	domainTypeLabel[20] = "O6-( 0,-1, 1)"
	domainTypeLabel[21] = "a1+( 1, 0, 0)"
	domainTypeLabel[22] = "a1-(-1, 0, 0)"
	domainTypeLabel[23] = "a2+( 0, 1, 0)"
	domainTypeLabel[24] = "a2-( 0,-1, 0)"
	domainTypeLabel[25] = " C+( 0, 0, 1)"
	domainTypeLabel[26] = " C-( 0, 0,-1)"

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

def readDatFerroDomain(filename,stdValue,angleDegree):
	angleRad=angleDegree/180.0*piValue
	domainTypeCount = 27
	a=[]
	a=getBox(filename)
	nx=a[0]
	ny=a[1]
	nz=a[2]
	data=readDatVector(filename)
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
				domainIndex[i][j][k]=getDomainType(vector[i][j][k][0],vector[i][j][k][1],vector[i][j][k][2],stdValue,angleRad)
				if domainIndex[i][j][k]!=-1:
					domainCount[int(domainIndex[i][j][k])]=domainCount[int(domainIndex[i][j][k])]+1

	for i in range(1,domainTypeCount):
		domainCountTotal = domainCountTotal + domainCount[i]
	print(domainCountTotal)
	for i in range(1,domainTypeCount):
		domainPercent[i] = domainCount[i]/domainCountTotal

	return domainIndex
