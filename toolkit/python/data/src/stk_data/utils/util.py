import numpy as np
import h5py
import os
from math import floor
def reduceDensity(data,density):
	dimension=list(np.shape(data))
	nx=dimension[0]
	ny=dimension[1]
	nz=dimension[2]
	new_dimension=dimension
	new_dimension[0]=floor(nx/density)
	new_dimension[1]=floor(ny/density)
	new_dimension[2]=floor(nz/density)
	new_data = np.zeros(new_dimension)
	for i in range(0,new_dimension[0]):
		for j in range(0,new_dimension[1]):
			for k in range(0,new_dimension[2]):
				new_data[i,j,k] = data[i*density,j*density,k*density+1]
	return new_data

def slice1D(data,dimension,position):
	dim=np.shape(data)
	new_dimension=[0]*(len(dim)-1)
	for i in range(0,len(dim)):
		if i < dimension:
			new_dimension[i]=dim[i]
		elif i > dimension:
			# nothing to be done for i==dimension
			new_dimension[i-1]=dim[i]
	new_data=np.zeros(new_dimension)
	new_data=np.moveaxis(data,dimension,0)[position,...]
	return new_data


def crop3D(data,xmin,xmax,ymin,ymax,zmin,zmax):
	return data[xmin:xmax,ymin:ymax,zmin:zmax,...]

def writeDat2H5(filename,dataname,data_set):
    if not os.path.exists(filename):
        # print("Creating new file ",filename)
        with h5py.File(filename,'w') as hf:
            hf.create_dataset(dataname,data=data_set,compression='gzip', compression_opts=9)
    else:
        # print("Already exist ",filename)
        with h5py.File(filename,'r+') as hf:
            if dataname in hf:
                # print("Overwriting data ",dataname)
                del hf[dataname]
                hf.create_dataset(dataname,data=data_set,compression='gzip', compression_opts=9)
            else:
                # print("Appending data ", dataname)
                hf.create_dataset(dataname,data=data_set,compression='gzip', compression_opts=9)

def readDatFromH5(filename,dataname):
    outDat = np.empty(1)
    if not os.path.exists(filename):
        print("The h5 file does not exist. ",filename)
    else:
        # print("Already exist ",filename)
        with h5py.File(filename,'r') as hf:
            if dataname in hf:
                # print("Overwriting data ",dataname)
                outDat = np.array(hf[dataname])
            else:
                print("The data name does not exist. ", dataname)
    return outDat
                
def getH5List(filename,groupName='/'):
    outList=[]
    if not os.path.exists(filename):
         print("The h5 file does not exist. ",filename)
    else:
        # print("Already exist ",filename)
        with h5py.File(filename,'r') as hf:
            if groupName in hf:
                # print("Overwriting data ",dataname)
                outList = list(hf[groupName].keys())
            else:
                 print("The group name does not exist. ", groupName)  
    return outList

def getH5GroupList(filename,groupName='/'):
    outList=[]
    if not os.path.exists(filename):
         print("The h5 file does not exist. ",filename)
    else:
        # print("Already exist ",filename)
        with h5py.File(filename,'r') as hf:
            if groupName in hf:
                # print("Overwriting data ",dataname)
                for key in hf[groupName].keys():
                    getType = hf[groupName].get(key,getclass=True)
                    if getType == h5py.Group:
                        outList.append(key)
            else:
                 print("The group name does not exist. ", groupName)  
    return outList

def getH5DataList(filename,groupName='/'):
    outList=[]
    if not os.path.exists(filename):
         print("The h5 file does not exist. ",filename)
    else:
        # print("Already exist ",filename)
        with h5py.File(filename,'r') as hf:
            if groupName in hf:
                # print("Overwriting data ",dataname)
                for key in hf[groupName].keys():
                    getType = hf[groupName].get(key,getclass=True)
                    if getType == h5py.Dataset:
                        outList.append(key)
            else:
                 print("The group name does not exist. ", groupName)  
    return outList
             
def writeAttr(filename,dataname,attrName,attrValue):
    if not os.path.exists(filename):
        print("File does not exist: ",filename, ', you must create the hdf5 file first')

    else:
        # print("File exist ",filename)
        with h5py.File(filename,'r+') as hf:
            if dataname in hf:
                # print("Dataset/group exist ",dataname)
                if hf[dataname].attrs.__contains__(attrName):
                    hf[dataname].attrs.__delitem__(attrName)
                hf[dataname].attrs[attrName]=attrValue
            else:
                print("Dataset does not exist: ", dataname, ', you must create the dataset first to append attribute')

def readAttr(filename,dataname,attrName):
    output = ''
    if not os.path.exists(filename):
        print("File does not exist: ",filename, ', you must create the hdf5 file first')
    else:
        # print("File exist ",filename)
        with h5py.File(filename,'r+') as hf:
            if dataname in hf:
                # print("Dataset/group exist: ",dataname)
                if hf[dataname].attrs.__contains__(attrName):
                    # print('Attribute exist: ',attrName)
                    output = hf[dataname].attrs[attrName]
            else:
                print("Dataset does not exist: ", dataname, ', you must create the dataset first to append attribute')
    return output

def writeString2File(string,filename):
    with open(filename,'w') as file:
        return file.write(string)
    
def loadFile2String(filename):
    with open(filename,'r') as file:
        return file.read()
    
def fixSVGASCII(filename):
    with open(filename) as file:
        newText=file.read().replace('ASCII','utf-8')
    with open(filename,'w') as file:
        file.write(newText)
