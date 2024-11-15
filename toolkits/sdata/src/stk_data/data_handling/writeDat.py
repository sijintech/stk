import pandas as pd
import numpy as np
import string
from operator import add
from math import floor
from ..utils.util import *

#%%
class MyFormatter(string.Formatter): 
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
      
      
def writeData(filename,data):
    xmin=1
    ymin=1
    zmin=1
    xmax=data.shape[0]+xmin-1
    ymax=data.shape[1]+ymin-1
    zmax=data.shape[2]+zmin-1
    file=open(filename,"w")
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
                    toFormatString.append(MyFormatter().format(FORMAT,data[i,j,k,m]))
                value=formatString.format(*toFormatString)
                file.write('{}{} \n'.format(position,value))
    file.close()

def writeDict2File(filename,dictionary):
    with open(filename,'a') as file:
        line = ""
        for key in dictionary.keys():
            line = line + " " + str(key) +" " + str(dictionary[key])
        line = line + '\n'
        file.write(line)
        
def writeList2File(filename,fullList):
    with open(filename,'a') as file:
        strList = [str(a) for a in fullList]
        line = " ".join(strList) + "\n"
        file.write(line)

def houWriteVolume(filename,data,nameList):
#    touch(filename)
    nx,ny,nz,nn = data.shape
    writeDict2File(filename,{'PGEOMETRY':'V5'})
    writeDict2File(filename,{'NPoints':nn,'NPrims':nn})
    writeDict2File(filename,{'NPointGroups':0,'NPrimGroups':0})
    writeDict2File(filename,{'NPointAttrib':0,'NVertexAttrib':0,'NPrimAttrib':0,'NAttrib':0})
    centerLocation = [0,0,0,1]
    primType = 'Volume'
    primTransform = [nx,0,0,0,ny,0,0,0,nz]
    primRes = [nx,ny,nz]
    primVolType = ['constant',0,0]
    primVolMode = 'smoke'
    primVolISO = 0
    primVolDensity = 1
    

    for i in range(0,nn):
        writeList2File(filename,centerLocation)

    writeList2File(filename,['PrimitiveAttrib'])
    writeList2File(filename,['name',1,'index',nn]+nameList)
    writeList2File(filename,['Run',nn,primType])
    
    for i in range(0,nn):
        writeList2File(filename,[i]+primTransform+[-2]+primRes+primVolType+[primVolMode,primVolISO,primVolDensity])
        writeList2File(filename,list(data[:,:,:,i].flatten(order='F'))+['['+str(i)+']'])
    writeList2File(filename,['beginExtra'])
    writeList2File(filename,['endExtra'])
    
    